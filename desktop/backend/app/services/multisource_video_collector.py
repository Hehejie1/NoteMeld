from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

from app.models.multisource_summary import (
    FrameContextResult,
    MultiSourceSummaryBundle,
    TranscriptContextResult,
    WebSearchResult,
)
from app.services.transcript_collector import TranscriptCollector
from app.services.video_frame_collector import VideoFrameCollector
from app.services.web_search import WebSearchCollector, get_web_search_provider


logger = logging.getLogger(__name__)


class _CollectorStatusReporter:
    def running(self, task_id: str, collector: str, message: str) -> None:
        from app.services.collector_status import mark_collector_running

        mark_collector_running(task_id, collector, message=message)

    def done(self, task_id: str, collector: str, duration_ms: int) -> None:
        from app.services.collector_status import mark_collector_done

        mark_collector_done(task_id, collector, duration_ms=duration_ms)

    def failed(self, task_id: str, collector: str, error: str) -> None:
        from app.services.collector_status import mark_collector_failed

        mark_collector_failed(task_id, collector, error=error)

    def skipped(self, task_id: str, collector: str, reason: str) -> None:
        from app.services.collector_status import mark_collector_skipped

        mark_collector_skipped(task_id, collector, reason=reason)


class MultiSourceVideoCollector:
    def __init__(
        self,
        *,
        web_search_collector=None,
        transcript_collector=None,
        frame_collector=None,
        max_workers: int = 3,
        status_reporter: Any = _CollectorStatusReporter(),
    ):
        self.web_search_collector = web_search_collector or WebSearchCollector(provider=get_web_search_provider())
        self.transcript_collector = transcript_collector or TranscriptCollector()
        self.frame_collector = frame_collector or VideoFrameCollector()
        self.max_workers = max(1, int(max_workers))
        self.status_reporter = status_reporter

    def collect(
        self,
        *,
        task_id: str,
        video_url: str,
        platform: str,
        downloader,
        gpt,
        transcriber=None,
        quality,
        output_path: str | None,
        screenshot: bool,
        grid_size: list[int],
        frame_timestamps: list[float] | None,
        title: str = "",
        description: str | None = None,
        allow_vision: bool = True,
    ) -> MultiSourceSummaryBundle:
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            web_future = executor.submit(
                self._collect_web_search,
                task_id=task_id,
                video_url=video_url,
                platform=platform,
                title=title,
                description=description,
            )
            transcript_future = executor.submit(
                self._collect_transcript,
                task_id=task_id,
                video_url=video_url,
                downloader=downloader,
                transcriber=transcriber,
                quality=quality,
                output_path=output_path,
            )
            frame_future = executor.submit(
                self._collect_frames,
                task_id=task_id,
                video_url=video_url,
                downloader=downloader,
                gpt=gpt,
                screenshot=screenshot,
                grid_size=grid_size,
                frame_timestamps=frame_timestamps,
                allow_vision=allow_vision,
            )

            web_search = web_future.result()
            transcript_result = transcript_future.result()
            frame_context = frame_future.result()

        audio_meta = transcript_result.audio_meta
        transcript = transcript_result.transcript
        resolved_title = title or getattr(audio_meta, "title", None) or ""
        return MultiSourceSummaryBundle(
            task_id=task_id,
            source_url=video_url,
            platform=platform,
            title=resolved_title,
            audio_meta=audio_meta,
            transcript=transcript,
            web_search=web_search,
            frame_context=frame_context,
        )

    def _collect_web_search(
        self,
        *,
        task_id: str,
        video_url: str,
        platform: str,
        title: str,
        description: str | None,
    ) -> WebSearchResult:
        return self._run_collector(
            task_id=task_id,
            collector_name="web_search",
            message="网页搜索中",
            call=lambda: self.web_search_collector.collect(
                task_id=task_id,
                source_url=video_url,
                title=title,
                platform=platform,
                description=description,
            ),
            fallback=lambda error: WebSearchResult(source="web_search", status="failed", error=error),
        )

    def _collect_transcript(
        self,
        *,
        task_id: str,
        video_url: str,
        downloader,
        transcriber,
        quality,
        output_path: str | None,
    ) -> TranscriptContextResult:
        return self._run_collector(
            task_id=task_id,
            collector_name="transcript",
            message="音频转文字中",
            call=lambda: self.transcript_collector.collect(
                task_id=task_id,
                video_url=video_url,
                downloader=downloader,
                transcriber=transcriber,
                quality=quality,
                output_path=output_path,
            ),
            fallback=lambda error: TranscriptContextResult(source="transcript", status="failed", mode="audio", error=error),
        )

    def _collect_frames(
        self,
        *,
        task_id: str,
        video_url: str,
        downloader,
        gpt,
        screenshot: bool,
        grid_size: list[int],
        frame_timestamps: list[float] | None,
        allow_vision: bool,
    ) -> FrameContextResult:
        return self._run_collector(
            task_id=task_id,
            collector_name="frames",
            message="视频分帧中",
            call=lambda: self.frame_collector.collect(
                task_id=task_id,
                video_url=video_url,
                downloader=downloader,
                gpt=gpt,
                screenshot=screenshot,
                grid_size=grid_size,
                frame_timestamps=frame_timestamps,
                allow_vision=allow_vision,
            ),
            fallback=lambda error: FrameContextResult(source="frames", status="failed", mode="disabled", error=error),
        )

    def _run_collector(
        self,
        *,
        task_id: str,
        collector_name: str,
        message: str,
        call: Callable[[], Any],
        fallback: Callable[[str], Any],
    ):
        started = datetime.now(timezone.utc)
        self._mark_running(task_id, collector_name, message)
        try:
            result = call()
        except Exception as exc:
            error = str(exc)
            self._mark_failed(task_id, collector_name, error)
            return fallback(error)
        self._mark_result(task_id, collector_name, result, started)
        return result

    def _mark_running(self, task_id: str, collector_name: str, message: str) -> None:
        if self.status_reporter is not None:
            self._safe_report_status(
                task_id,
                collector_name,
                lambda: self.status_reporter.running(task_id, collector_name, message),
            )

    def _mark_result(self, task_id: str, collector_name: str, result, started: datetime) -> None:
        if self.status_reporter is None:
            return
        status = getattr(result, "status", "")
        if status == "done":
            self._safe_report_status(
                task_id,
                collector_name,
                lambda: self.status_reporter.done(task_id, collector_name, self._elapsed_ms(started)),
            )
        elif status == "skipped":
            self._safe_report_status(
                task_id,
                collector_name,
                lambda: self.status_reporter.skipped(
                    task_id,
                    collector_name,
                    getattr(result, "error", None) or "skipped",
                ),
            )
        elif status == "failed":
            self._safe_report_status(
                task_id,
                collector_name,
                lambda: self.status_reporter.failed(
                    task_id,
                    collector_name,
                    getattr(result, "error", None) or "failed",
                ),
            )

    def _mark_failed(self, task_id: str, collector_name: str, error: str) -> None:
        if self.status_reporter is not None:
            self._safe_report_status(
                task_id,
                collector_name,
                lambda: self.status_reporter.failed(task_id, collector_name, error),
            )

    def _safe_report_status(self, task_id: str, collector_name: str, report: Callable[[], None]) -> None:
        try:
            report()
        except Exception as exc:
            logger.warning(
                "collector status update failed task_id=%s collector=%s error=%s",
                task_id,
                collector_name,
                exc,
            )

    def _elapsed_ms(self, started: datetime) -> int:
        return max(0, int((datetime.now(timezone.utc) - started).total_seconds() * 1000))
