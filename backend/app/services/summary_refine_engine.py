import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from app.models.gpt_model import GPTSource
from app.models.summary_input import WeightedContextPack
from app.models.summary_plan import SummaryPlan
from app.models.transcriber_model import TranscriptSegment
from app.renderers.note_renderer import NoteRenderer

logger = logging.getLogger(__name__)


@dataclass
class RefineChunkTrace:
    index: int
    start_time: float
    end_time: float
    segment_count: int
    summary: str


@dataclass
class RefineResult:
    task_id: str
    strategy: str
    markdown: str
    map_summaries: list[str] = field(default_factory=list)
    chunks: list[RefineChunkTrace] = field(default_factory=list)


class SummaryRefineEngine:
    DEFAULT_MAX_SEGMENTS = 80
    # final 阶段图片阶梯降级：初始 → 4 → 2 → 0（纯文本兜底）
    FINAL_IMAGE_FALLBACK_CAPS = (4, 2, 0)
    GATEWAY_TIMEOUT_STATUS_CODES = {502, 503, 504, 524}
    PAYLOAD_TOO_LARGE_STATUS_CODES = {413}
    GATEWAY_TIMEOUT_TOKENS = (
        "504", "502", "503", "524",
        "gateway", "timeout", "timed out", "service unavailable",
    )
    PAYLOAD_TOO_LARGE_TOKENS = (
        "413", "request body exceeds", "request_too_large", "payload too large",
        "exceeds your tier limit", "limit_bytes",
    )

    def run(
        self,
        task_id: str,
        title: str,
        segments: list[TranscriptSegment],
        gpt,
        plan: SummaryPlan,
        pack: Optional[WeightedContextPack] = None,
        style: Optional[str] = None,
        extras: Optional[str] = None,
        tags: Optional[list[str]] = None,
        video_img_urls: Optional[list[str]] = None,
    ) -> RefineResult:
        chunks = self._chunk_segments(segments, plan.chunk_policy.get("max_segments_per_chunk"))
        chunk_traces = []
        map_summaries = []
        for index, chunk in enumerate(chunks, start=1):
            summary = gpt.summarize(
                GPTSource(
                    title=title,
                    segment=chunk,
                    tags=tags or [],
                    screenshot=False,
                    link=False,
                    _format=[],
                    style=style,
                    extras=self._map_extras(index, len(chunks), extras),
                    video_img_urls=[],
                    checkpoint_key=f"{task_id}:map:{index}",
                )
            )
            map_summaries.append(summary)
            chunk_traces.append(
                RefineChunkTrace(
                    index=index,
                    start_time=float(chunk[0].start) if chunk else 0.0,
                    end_time=float(chunk[-1].end) if chunk else 0.0,
                    segment_count=len(chunk),
                    summary=summary,
                )
            )

        final_markdown = self._summarize_final_with_image_fallback(
            gpt=gpt,
            task_id=task_id,
            title=title,
            tags=tags,
            style=style,
            extras=self._final_extras(map_summaries, pack, plan, extras),
            video_img_urls=list(video_img_urls or []),
        )
        return RefineResult(
            task_id=task_id,
            strategy=plan.strategy,
            markdown=final_markdown,
            map_summaries=map_summaries,
            chunks=chunk_traces,
        )

    def write_trace(self, output_dir: Path, task_id: str, result: RefineResult) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        trace_path = output_dir / f"{task_id}_refine_trace.json"
        payload = asdict(result)
        payload["final_chars"] = len(result.markdown or "")
        trace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return trace_path

    def _chunk_segments(self, segments: list[TranscriptSegment], max_segments: Optional[int]) -> list[list[TranscriptSegment]]:
        try:
            size = int(max_segments or self.DEFAULT_MAX_SEGMENTS)
        except (TypeError, ValueError):
            size = self.DEFAULT_MAX_SEGMENTS
        size = max(1, size)
        return [segments[index:index + size] for index in range(0, len(segments), size)] or [[]]

    def _map_extras(self, index: int, total: int, extras: Optional[str]) -> str:
        prompt = (
            f"这是长内容分块摘要阶段，请总结第 {index}/{total} 个字幕块。"
            "保留关键事实、时间线、术语、行动项和可引用证据。"
        )
        if extras:
            return extras + "\n\n" + prompt
        return prompt

    def _final_extras(
        self,
        map_summaries: list[str],
        pack: Optional[WeightedContextPack],
        plan: SummaryPlan,
        extras: Optional[str],
    ) -> str:
        sections = []
        if extras:
            sections.append(extras)
        sections.append("## 分块摘要\n" + "\n\n".join(f"### Chunk {index}\n{summary}" for index, summary in enumerate(map_summaries, start=1)))
        if pack:
            final_context = NoteRenderer().build_final_context(pack, plan)
            if final_context:
                sections.append(final_context)
        sections.append("请基于分块摘要进行全局去重、合并同义点，并输出完整 Markdown 笔记。")
        return "\n\n".join(section for section in sections if section)

    def _summarize_final_with_image_fallback(
        self,
        *,
        gpt,
        task_id: str,
        title: str,
        tags: Optional[list[str]],
        style: Optional[str],
        extras: str,
        video_img_urls: list[str],
    ) -> str:
        """final 阶段请求过大/超时阶梯降级：初始 → 4 → 2 → 0。

        非可降级错误立即抛出；最后一档（纯文本）若仍失败也直接抛出。
        """
        steps = self._build_image_fallback_steps(len(video_img_urls))
        last_exc: Optional[BaseException] = None
        for attempt_index, target_count in enumerate(steps):
            current_images = list(video_img_urls[:target_count])
            checkpoint_key = (
                f"{task_id}:final"
                if attempt_index == 0
                else f"{task_id}:final-fallback-{target_count}"
            )
            try:
                return gpt.summarize(
                    GPTSource(
                        title=title,
                        segment=[],
                        tags=tags or [],
                        screenshot=False,
                        link=False,
                        _format=[],
                        style=style,
                        extras=extras,
                        video_img_urls=current_images,
                        checkpoint_key=checkpoint_key,
                    )
                )
            except Exception as exc:
                if not self._is_final_retryable_error(exc):
                    raise
                if attempt_index == len(steps) - 1:
                    logger.warning(
                        "Final 阶段纯文本仍失败，压缩上下文后重试 task_id=%s error=%s",
                        task_id,
                        exc,
                    )
                    return gpt.summarize(
                        GPTSource(
                            title=title,
                            segment=[],
                            tags=tags or [],
                            screenshot=False,
                            link=False,
                            _format=[],
                            style=style,
                            extras=self._compress_final_extras(extras),
                            video_img_urls=[],
                            checkpoint_key=f"{task_id}:final-compressed",
                        )
                    )
                last_exc = exc
                next_count = steps[attempt_index + 1]
                logger.warning(
                    "Final 阶段请求过大或网关超时，降级图片数 task_id=%s images=%d -> %d error=%s",
                    task_id, target_count, next_count, exc,
                )
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("final summarize exited fallback loop without result")

    @staticmethod
    def _compress_final_extras(extras: str, max_chars: int = 480) -> str:
        text = (extras or "").strip()
        if len(text) <= max_chars:
            return text

        chunk_markers = [part.strip() for part in text.split("### Chunk ") if part.strip()]
        summaries = []
        for raw_chunk in chunk_markers[:8]:
            lines = raw_chunk.splitlines()
            chunk_title = lines[0].strip() if lines else ""
            chunk_body = " ".join(line.strip() for line in lines[1:] if line.strip())
            snippet = chunk_body[:80].strip()
            if chunk_title or snippet:
                summaries.append(f"- Chunk {chunk_title}: {snippet}")

        compressed = "## 压缩后的分块摘要\n" + "\n".join(summaries)
        compressed += "\n\n请基于压缩摘要输出完整 Markdown 笔记，保留核心结论、行动项和关键证据。"

        if len(compressed) > max_chars:
            return compressed[: max_chars - 20].rstrip() + "\n\n请输出完整笔记。"
        return compressed

    @classmethod
    def _build_image_fallback_steps(cls, initial: int) -> list[int]:
        initial = max(0, int(initial))
        steps = [initial]
        for cap in cls.FINAL_IMAGE_FALLBACK_CAPS:
            if cap < steps[-1]:
                steps.append(cap)
        return steps

    @classmethod
    def _is_gateway_timeout_error(cls, exc: BaseException) -> bool:
        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if status in cls.GATEWAY_TIMEOUT_STATUS_CODES:
            return True
        raw = str(exc).lower()
        return any(token in raw for token in cls.GATEWAY_TIMEOUT_TOKENS)

    @classmethod
    def _is_payload_too_large_error(cls, exc: BaseException) -> bool:
        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if status in cls.PAYLOAD_TOO_LARGE_STATUS_CODES:
            return True
        raw = str(exc).lower()
        return any(token in raw for token in cls.PAYLOAD_TOO_LARGE_TOKENS)

    @classmethod
    def _is_final_retryable_error(cls, exc: BaseException) -> bool:
        return cls._is_gateway_timeout_error(exc) or cls._is_payload_too_large_error(exc)
