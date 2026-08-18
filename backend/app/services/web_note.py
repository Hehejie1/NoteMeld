from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Optional

import httpx

from app.db import note_style_dao
from app.enmus.task_status_enums import TaskStatus
from app.gpt.provider_runtime import normalize_model_error
from app.models.audio_model import AudioDownloadResult
from app.models.gpt_model import GPTSource
from app.models.notes_model import NoteResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.renderers.export_outline_renderer import ExportOutlineRenderer
from app.renderers.note_renderer import NoteRenderer
from app.services.note_output_normalizer import normalize_note_output
from app.services.ingestion.web_adapter import WebIngestionAdapter
from app.services.context_normalizer import ContextNormalizer
from app.services.note_document_store import update_note_document_wiki_status
from app.services.summary_planner import SummaryPlanner
from app.services.task_status_writer import emit_note_progress
from app.services.wiki_job_store import WikiJobStore
from app.services.wiki_enhancement_queue import schedule_partial_wiki_enhancement
from app.services.wiki_pipeline import WikiPipeline
from app.services.wiki_rebuild_service import request_wiki_rebuild
from app.services.web_source_layer import WebSourceLayer
from app.utils.markdown_assets import localize_remote_markdown_images, write_markdown_assets_sidecar
from app.utils.note_helper import prepend_source_link
from app.utils.storage_paths import note_output_dir


NOTE_OUTPUT_DIR = note_output_dir()
logger = logging.getLogger(__name__)
DYNAMIC_WEB_PAGE_MESSAGE = "该页面为动态渲染/反爬页面，无法直接提取正文"
NON_HTML_PAGE_MESSAGE = "当前无法获取该页面内容，请稍后重试或更换链接。"


def _apply_style_output_formats(content: str, style: Optional[str]) -> str:
    if not style:
        return content
    template = note_style_dao.get_style_template(style)
    if not template:
        return content
    output_formats = template.get("output_formats") or ["markdown"]
    return normalize_note_output(content, output_formats)


def _page_context_to_ingestion_dict(summary_input, fallback_url: str) -> dict:
    page = getattr(summary_input, "page_context", None)
    if not page:
        return {
            "url": fallback_url,
            "title": getattr(summary_input, "title", None) or fallback_url,
            "main_text": getattr(summary_input, "title", "") or "",
            "headings": [],
        }
    return {
        "url": getattr(summary_input, "source_url", None) or fallback_url,
        "title": getattr(page, "title", None) or getattr(summary_input, "title", None) or fallback_url,
        "main_text": getattr(page, "main_text_summary", None) or getattr(page, "description", None) or "",
        "headings": getattr(page, "headings", None) or [],
    }


def _run_web_ingestion_best_effort(task_id: str, page_context: dict) -> None:
    try:
        WebIngestionAdapter().ingest(task_id=task_id, page_context=page_context)
    except Exception as exc:
        logger.warning("网页摄取产物生成失败（不影响笔记）: %s", exc)


class _WebVideoCollection:
    def __init__(
        self,
        *,
        summary_input: object,
        main_text: str,
        transcript: TranscriptResult,
        audio_meta: AudioDownloadResult,
        web_error: Optional[Exception] = None,
        video_error: Optional[Exception] = None,
        video_url: Optional[str] = None,
    ):
        self.summary_input = summary_input
        self.main_text = main_text
        self.transcript = transcript
        self.audio_meta = audio_meta
        self.web_error = web_error
        self.video_error = video_error
        self.video_url = video_url


class WebNoteGenerator:
    def __init__(
        self,
        fetch_html: Optional[Callable[[str], str]] = None,
        gpt_factory: Optional[Callable[[str, str], object]] = None,
    ):
        self._fetch_html = fetch_html or self.fetch_html
        self._gpt_factory = gpt_factory or self._get_gpt

    @staticmethod
    def fetch_html(url: str, client_cls=httpx.Client, max_retries: int = 1) -> str:
        headers = {"User-Agent": "NoteMeld-WebNote/1.0"}
        last_error = None
        for _ in range(max(1, max_retries)):
            try:
                with client_cls(timeout=15.0, follow_redirects=True) as client:
                    response = client.get(url, headers=headers)
                    response.raise_for_status()
                    content_type = getattr(response, "headers", {}).get("content-type", "").lower()
                    if content_type and "html" not in content_type:
                        logger.warning("Non-HTML response for %s: %s", url, content_type)
                        raise ValueError(NON_HTML_PAGE_MESSAGE)
                    return response.text
            except ValueError:
                raise
            except Exception as exc:
                last_error = exc
        raise last_error

    def generate(
        self,
        web_url: str,
        task_id: str,
        model_name: str,
        provider_id: str,
        _format: Optional[list] = None,
        style: Optional[str] = None,
        extras: Optional[str] = None,
        output_type: str = "note_markdown",
    ) -> NoteResult | None:
        output_dir = self._output_dir()
        try:
            self._update_status(task_id, TaskStatus.PARSING)
            user_options = {
                "output_type": output_type,
                "style": style,
                "format": _format or [],
                "extras": extras,
                "model_name": model_name,
                "provider_id": provider_id,
                "enable_wiki": True,
            }
            collection = self._collect_web_and_video(
                task_id=task_id,
                web_url=str(web_url),
                output_dir=output_dir,
                user_options=user_options,
            )
            summary_input = collection.summary_input
            main_text = collection.main_text
            transcript = collection.transcript
            audio_meta = collection.audio_meta

            normalizer = ContextNormalizer()
            pack = normalizer.build_weighted_pack(summary_input)
            plan = SummaryPlanner().plan(summary_input, pack)
            enriched_extras = NoteRenderer().build_extras_with_context(extras, pack, plan)

            gpt = self._gpt_factory(model_name, provider_id)
            if hasattr(gpt, "set_usage_context"):
                gpt.set_usage_context(
                    {
                        "task_id": task_id,
                        "provider_id": provider_id,
                        "provider_name": self._provider_name(provider_id),
                        "phase": "summarize",
                        "platform": "web_link",
                        "video_id": task_id,
                        "video_title": audio_meta.title,
                        "request_meta": {
                            "source_type": "web_link",
                            "style": style,
                            "format": _format or [],
                            "extras_present": bool(extras),
                        },
                    }
                )

            self._update_status(task_id, TaskStatus.SUMMARIZING)
            source = GPTSource(
                title=audio_meta.title,
                segment=transcript.segments,
                tags=[],
                screenshot=False,
                link=False,
                _format=_format or [],
                style=style,
                extras=enriched_extras,
                video_img_urls=[],
                checkpoint_key=task_id,
            )
            markdown = _apply_style_output_formats(gpt.summarize(source), style)
            markdown = prepend_source_link(markdown, str(web_url))
            asset_result = localize_remote_markdown_images(
                task_id=task_id,
                markdown=markdown,
                source_url=str(web_url),
            )
            markdown = asset_result.markdown or markdown
            (output_dir / f"{task_id}_markdown.md").write_text(markdown, encoding="utf-8")
            write_markdown_assets_sidecar(output_dir, task_id, asset_result.assets)

            self._update_status(task_id, TaskStatus.SAVING)
            self._write_sidecars(output_dir, task_id, summary_input, pack, plan, markdown, gpt)
            _run_web_ingestion_best_effort(
                task_id=task_id,
                page_context=_page_context_to_ingestion_dict(summary_input, str(web_url)),
            )
            self._update_status(task_id, TaskStatus.SUCCESS)
            return NoteResult(markdown=markdown, transcript=transcript, audio_meta=audio_meta)
        except Exception as exc:
            logger.error(f"网页笔记生成失败 (task_id={task_id}): {exc}", exc_info=True)
            self._update_status(task_id, TaskStatus.FAILED, message=normalize_model_error(exc))
            return None

    def _collect_web_and_video(
        self,
        *,
        task_id: str,
        web_url: str,
        output_dir: Path,
        user_options: dict,
    ) -> _WebVideoCollection:
        summary_input = None
        main_text = ""
        web_error: Optional[Exception] = None
        video_error: Optional[Exception] = None

        try:
            html = self._fetch_html(web_url)
            (output_dir / f"{task_id}_raw.html").write_text(html, encoding="utf-8")
            summary_input = WebSourceLayer().from_html(task_id, web_url, html, user_options)
            main_text = self._main_text(summary_input)
            if self._extracted_main_text(summary_input):
                raw_text_path = output_dir / f"{task_id}_raw_text.txt"
                raw_text_path.write_text(main_text, encoding="utf-8")
                if summary_input.page_context:
                    summary_input.page_context.raw_text_path = str(raw_text_path)
            else:
                web_error = ValueError(DYNAMIC_WEB_PAGE_MESSAGE)
        except Exception as exc:
            logger.warning("网页内容采集失败，继续尝试视频采集 (task_id=%s): %s", task_id, exc)
            web_error = exc

        video_url = self._detect_video_url(summary_input, web_url)
        audio_meta = None
        video_transcript = None
        if video_url:
            try:
                audio_meta, video_transcript = self._collect_video_context(
                    video_url,
                    task_id=task_id,
                    user_options=user_options,
                    output_dir=output_dir,
                )
            except Exception as exc:
                logger.warning("视频内容采集失败，继续尝试网页总结 (task_id=%s): %s", task_id, exc)
                video_error = exc

        if video_transcript and video_transcript.segments:
            fused_input = self._build_video_summary_input(
                task_id=task_id,
                web_url=web_url,
                video_url=video_url or web_url,
                audio_meta=audio_meta,
                transcript=video_transcript,
                user_options=user_options,
                web_summary_input=summary_input,
            )
            return _WebVideoCollection(
                summary_input=fused_input,
                main_text=video_transcript.full_text,
                transcript=video_transcript,
                audio_meta=audio_meta,
                web_error=web_error,
                video_error=video_error,
                video_url=video_url,
            )

        if summary_input and self._extracted_main_text(summary_input):
            transcript = TranscriptResult(
                language="zh",
                full_text=main_text,
                segments=[TranscriptSegment(start=0, end=0, text=main_text)] if main_text else [],
            )
            audio_meta = AudioDownloadResult(
                file_path="",
                title=summary_input.title or web_url,
                duration=0,
                cover_url=None,
                platform="web_link",
                video_id=task_id,
                raw_info={
                    "webpage_url": web_url,
                    "description": summary_input.page_context.description if summary_input.page_context else None,
                    "video_collect_error": str(video_error) if video_error else "",
                },
            )
            return _WebVideoCollection(
                summary_input=summary_input,
                main_text=main_text,
                transcript=transcript,
                audio_meta=audio_meta,
                web_error=web_error,
                video_error=video_error,
                video_url=video_url,
            )

        if web_error and video_error:
            raise RuntimeError(f"网页和视频内容均采集失败：网页={web_error}; 视频={video_error}")
        if web_error:
            raise web_error
        if video_error:
            raise video_error
        raise ValueError(DYNAMIC_WEB_PAGE_MESSAGE)

    def _detect_video_url(self, summary_input, web_url: str) -> Optional[str]:
        page = getattr(summary_input, "page_context", None) if summary_input else None
        for item in getattr(page, "detected_media", []) or []:
            if item.get("type") == "video" and item.get("url"):
                return item["url"]
        try:
            from app.services.source_inspector import SourceInspector

            inspection = SourceInspector().inspect(web_url)
            if inspection.input_type == "video_link" and inspection.source_url:
                return inspection.source_url
        except Exception:
            return None
        return None

    def _collect_video_context(
        self,
        video_url: str,
        *,
        task_id: str,
        user_options: dict,
        output_dir: Path,
    ) -> tuple[AudioDownloadResult, TranscriptResult]:
        from app.enmus.note_enums import DownloadQuality
        from app.services.note import NoteGenerator

        note_generator = NoteGenerator()
        platform = self._video_platform(video_url)
        downloader = note_generator._get_downloader(platform)
        transcript_cache_file = output_dir / f"{task_id}_transcript.json"
        audio_cache_file = output_dir / f"{task_id}_audio.json"

        transcript = None
        try:
            transcript = downloader.download_subtitles(video_url)
            if transcript and transcript.segments:
                transcript_cache_file.write_text(
                    json.dumps(asdict(transcript), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception as exc:
            logger.warning("视频字幕获取失败，准备下载音频转写 (task_id=%s): %s", task_id, exc)
            transcript = None

        audio_meta = note_generator._download_media(
            downloader=downloader,
            video_url=video_url,
            quality=DownloadQuality.medium,
            audio_cache_file=audio_cache_file,
            status_phase=TaskStatus.DOWNLOADING,
            platform=platform,
            output_path=str(output_dir),
            screenshot=False,
            video_understanding=False,
            video_interval=0,
            grid_size=[],
            skip_download=bool(transcript and transcript.segments),
        )
        if transcript is None or not transcript.segments:
            transcript = note_generator._get_transcript(
                downloader=downloader,
                video_url=video_url,
                audio_file=audio_meta.file_path,
                transcript_cache_file=transcript_cache_file,
                status_phase=TaskStatus.TRANSCRIBING,
                task_id=task_id,
            )
        if not transcript or not transcript.segments:
            raise RuntimeError("视频转写结果为空")
        raw_info = audio_meta.raw_info or {}
        raw_info.setdefault("webpage_url", video_url)
        raw_info.setdefault("source_web_url", user_options.get("source_web_url", ""))
        audio_meta.raw_info = raw_info
        return audio_meta, transcript

    def _build_video_summary_input(
        self,
        *,
        task_id: str,
        web_url: str,
        video_url: str,
        audio_meta: AudioDownloadResult,
        transcript: TranscriptResult,
        user_options: dict,
        web_summary_input,
    ):
        from app.services.context_normalizer import ContextNormalizer
        from app.services.source_inspector import SourceInspector

        normalizer = ContextNormalizer()
        inspection = SourceInspector().inspect(video_url)
        summary_input = normalizer.from_video_task(
            task_id=task_id,
            video_url=video_url,
            platform=audio_meta.platform,
            audio_meta=audio_meta,
            transcript=transcript,
            user_options=user_options,
            inspection=inspection,
        )
        summary_input.source_url = web_url
        summary_input.input_type = "web_video_link"
        if web_summary_input and getattr(web_summary_input, "page_context", None):
            summary_input.page_context = web_summary_input.page_context
        summary_input.title = (
            audio_meta.title
            or getattr(web_summary_input, "title", None)
            or web_url
        )
        summary_input.meta_context.resource_type = "web_video_link"
        summary_input.meta_context.raw["source_web_url"] = web_url
        summary_input.meta_context.raw["video_url"] = video_url
        return summary_input

    def _video_platform(self, video_url: str) -> str:
        lowered = video_url.lower()
        if "bilibili.com" in lowered or "b23.tv" in lowered:
            return "bilibili"
        if "youtube.com" in lowered or "youtu.be" in lowered:
            return "youtube"
        if "douyin.com" in lowered:
            return "douyin"
        if "kuaishou.com" in lowered:
            return "kuaishou"
        if "channels.weixin.qq.com" in lowered:
            return "wechat_channels"
        raise ValueError(f"不支持的视频链接: {video_url}")

    def _write_sidecars(self, output_dir: Path, task_id: str, summary_input, pack, plan, markdown: str, gpt) -> None:
        (output_dir / f"{task_id}_summary_input.json").write_text(
            json.dumps(asdict(summary_input), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / f"{task_id}_summary_plan.json").write_text(
            json.dumps(asdict(plan), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / f"{task_id}_weighted_context_pack.json").write_text(
            json.dumps(asdict(pack), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / f"{task_id}_vision_policy.json").write_text(
            json.dumps(plan.vision_policy, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if summary_input.user_options.get("enable_wiki", True):
            self._write_wiki_sidecars(output_dir, task_id, summary_input, markdown, gpt)

    def _write_wiki_sidecars(self, output_dir: Path, task_id: str, summary_input, markdown: str, gpt) -> None:
        try:
            job_store = WikiJobStore(output_dir=output_dir)
            pipeline = WikiPipeline(output_dir=output_dir)
            job_store.write(task_id, "running", stage="analysis", detail="正在提取 Wiki 知识", recoverable=True)
            wiki_payload = pipeline.extract_contribution(
                summary_input,
                markdown,
                gpt=gpt,
            )
            if job_store.read(task_id).get("status") == "canceled":
                update_note_document_wiki_status(task_id, "canceled")
                return
            wiki_status = wiki_payload.get("status", "success")
            job_store.write(
                task_id,
                wiki_status,
                stage="analysis",
                error=wiki_payload.get("analysis_error", ""),
                reason=wiki_payload.get("reason", ""),
                detail=wiki_payload.get("detail", ""),
                recoverable=wiki_payload.get("recoverable", False),
            )
            update_note_document_wiki_status(task_id, wiki_status)
            request_wiki_rebuild(output_dir, gpt=gpt, reason=f"task:{task_id}:analysis_complete")
            if wiki_status == "partial":
                schedule_partial_wiki_enhancement(output_dir, task_id, summary_input, markdown, gpt, update_note_document_wiki_status)
        except Exception as exc:
            logger.error(f"网页 Wiki extraction failed for task {task_id}: {exc}", exc_info=True)
            if WikiJobStore(output_dir=output_dir).read(task_id).get("status") == "canceled":
                update_note_document_wiki_status(task_id, "canceled")
                return
            WikiJobStore(output_dir=output_dir).write(
                task_id,
                "failed",
                stage=getattr(exc, "stage", "analysis"),
                error=str(exc),
                reason="analysis_error",
                detail=str(exc),
                recoverable=True,
            )
            update_note_document_wiki_status(task_id, "failed")

    def _get_gpt(self, model_name: str, provider_id: str):
        from app.gpt.notemeld_gpt import NotemeldGPT
        from app.services.model import ModelService
        from app.services.provider import ProviderService

        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            raise ValueError(f"未找到模型供应商: {provider_id}")
        config = ModelService.build_saved_model_config(provider, model_name)
        # T11: 走 notemeld-ai 适配器（NotemeldGPT），回滚时换回 GPTFactory().from_config(config)
        return NotemeldGPT.from_config(config)

    def _provider_name(self, provider_id: str) -> str:
        try:
            from app.services.provider import ProviderService

            provider = ProviderService.get_provider_by_id(provider_id)
            return provider["name"] if provider else "unknown"
        except Exception:
            return "unknown"

    def _main_text(self, summary_input) -> str:
        page = summary_input.page_context
        if not page:
            return summary_input.title or ""
        return page.main_text_summary or page.description or page.title or summary_input.source_url or ""

    def _extracted_main_text(self, summary_input) -> str:
        page = summary_input.page_context
        if not page:
            return ""
        return (page.main_text_summary or "").strip()

    def _output_dir(self) -> Path:
        output_dir = NOTE_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _update_status(self, task_id: Optional[str], status: TaskStatus | str, message: Optional[str] = None) -> None:
        if not task_id:
            return
        try:
            emit_note_progress(task_id, status, message)
        except Exception as exc:
            logger.error(f"写入网页笔记状态失败 (task_id={task_id}): {exc}")
