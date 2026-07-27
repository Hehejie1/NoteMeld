from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Tuple, Union, Any

from fastapi import HTTPException
from pydantic import HttpUrl
from dotenv import load_dotenv

from app.downloaders.base import Downloader
from app.downloaders.bilibili_downloader import BilibiliDownloader
from app.downloaders.douyin_downloader import DouyinDownloader
from app.downloaders.local_downloader import LocalDownloader
from app.downloaders.youtube_downloader import YoutubeDownloader
from app.db import note_style_dao
from app.db.video_task_dao import delete_task_by_video, insert_video_task
from app.enmus.exception import NoteErrorEnum, ProviderErrorEnum
from app.enmus.task_status_enums import TaskStatus
from app.enmus.note_enums import DownloadQuality
from app.exceptions.note import NoteError
from app.exceptions.provider import ProviderError
from app.gpt.base import GPT
from app.gpt.gpt_factory import GPTFactory
from app.gpt.provider_runtime import normalize_model_error
from app.models.audio_model import AudioDownloadResult
from app.models.gpt_model import GPTSource
from app.models.model_config import ModelConfig
from app.models.notes_model import AudioDownloadResult, NoteResult
from app.models.summary_plan import SummaryPlan, build_default_render_contract
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.renderers.export_outline_renderer import ExportOutlineRenderer
from app.renderers.note_renderer import NoteRenderer
from app.services.context_normalizer import ContextNormalizer
from app.services.html_to_markdown import html_to_markdown
from app.services.ingestion.transcript_adapter import TranscriptIngestionAdapter
from app.services.constant import SUPPORT_PLATFORM_MAP
from app.services.model import ModelService
from app.services.multisource_video_collector import MultiSourceVideoCollector
from app.services.note_document_store import update_note_document_wiki_status
from app.services.provider import ProviderService
from app.services.source_inspector import SourceInspector
from app.services.summary_refine_engine import SummaryRefineEngine
from app.services.summary_planner import SummaryPlanner, VisionSamplingPlanner
from app.services.task_status_writer import emit_note_progress
from app.services.note_task_store import is_note_task_canceled
from app.services.wiki_job_store import WikiJobStore
from app.services.wiki_enhancement_queue import schedule_wiki_extraction
from app.transcriber.base import Transcriber
from app.transcriber.transcriber_provider import get_transcriber, _transcribers
from app.utils.markdown_assets import localize_remote_markdown_images, write_markdown_assets_sidecar
from app.utils.note_helper import replace_content_markers, prepend_source_link
from app.utils.screenshot_marker import extract_screenshot_timestamps
from app.utils.status_code import StatusCode
from app.utils.storage_paths import note_output_dir, screenshot_dir
from app.utils.video_helper import generate_screenshot
from app.utils.video_reader import VideoReader

# ------------------ 环境变量与全局配置 ------------------

# 从 .env 文件中加载环境变量
load_dotenv()

# 后端 API 地址与端口（若有需要可以在代码其他部分使用 BACKEND_BASE_URL）
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8483")
BACKEND_BASE_URL = f"{API_BASE_URL}:{BACKEND_PORT}"

# 输出目录（用于缓存音频、转写、Markdown 文件，以及存储截图）
NOTE_OUTPUT_DIR = note_output_dir()
NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_OUTPUT_DIR = str(screenshot_dir())
# 图片基础 URL（用于生成 Markdown 中的图片链接，需前端静态目录对应）
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "/static/screenshots")

# 日志配置
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

GENERIC_MARKDOWN_TITLES = {
    "知识卡片",
    "深度研究",
    "快速摘要",
    "行动清单",
    "会议纪要",
    "视频解析",
    "网页提炼",
    "AI 对话沉淀",
}


def _transcript_segments_to_dicts(segments: list) -> list[dict]:
    normalized = []
    for segment in segments or []:
        if isinstance(segment, dict):
            normalized.append(segment)
        else:
            normalized.append(asdict(segment))
    return normalized


def _run_transcript_ingestion_best_effort(task_id: str, source_url: str, title: str, segments: list[dict]) -> None:
    try:
        TranscriptIngestionAdapter().ingest(
            task_id=task_id,
            source_url=source_url,
            title=title,
            segments=segments,
        )
    except Exception as exc:
        logger.warning("转录摄取产物生成失败（不影响笔记）: %s", exc)


def _normalize_transcript_payload(data: dict, source_label: str = "转写缓存") -> TranscriptResult | None:
    full_text = str(data.get("full_text") or "").strip()
    cleaned_segments = []
    for segment in data.get("segments", []) or []:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        cleaned_segments.append(
            TranscriptSegment(
                start=float(segment.get("start", 0)),
                end=float(segment.get("end", 0)),
                text=text,
            )
        )

    if not cleaned_segments and full_text:
        cleaned_segments.append(TranscriptSegment(start=0, end=0, text=full_text))

    if not cleaned_segments:
        logger.warning(f"{source_label} 没有可用文本片段，将重新获取")
        return None

    return TranscriptResult(
        language=data.get("language"),
        full_text=full_text or " ".join(segment.text for segment in cleaned_segments),
        segments=cleaned_segments,
        raw=data.get("raw"),
    )


class NoteGenerator:
    """
    NoteGenerator 用于执行视频/音频下载、转写、GPT 生成笔记、插入截图/链接、
    以及将任务信息写入状态文件与数据库等功能。
    """

    def __init__(self):
        from app.services.transcriber_config_manager import TranscriberConfigManager
        config_manager = TranscriberConfigManager()
        self.model_size: str = config_manager.get_whisper_model_size()
        self.device: Optional[str] = None
        self.transcriber_type: str = config_manager.get_transcriber_type()
        self.transcriber: Transcriber = self._init_transcriber()
        self.video_path: Optional[Path] = None
        self.video_img_urls=[]
        logger.info("NoteGenerator 初始化完成")


    # ---------------- 公有方法 ----------------

    def _looks_like_html(self, content: str) -> bool:
        lowered = (content or "").lower()
        return any(tag in lowered for tag in ("<article", "<section", "<div", "<p", "<h1", "<h2"))

    def _apply_style_output_formats(self, content: str, style: Optional[str]) -> str:
        if not style:
            return content
        template = note_style_dao.get_style_template(style)
        if not template:
            return content
        output_formats = template.get("output_formats") or ["markdown"]
        if output_formats == ["html"]:
            return content
        markdown = html_to_markdown(content) if self._looks_like_html(content) else content
        if output_formats == ["markdown"]:
            return markdown
        if "html" in output_formats and "markdown" in output_formats:
            return (
                "<!-- HTML_OUTPUT_START -->\n"
                f"{content}\n"
                "<!-- HTML_OUTPUT_END -->\n\n"
                "<!-- MARKDOWN_OUTPUT_START -->\n"
                f"{markdown}"
                "<!-- MARKDOWN_OUTPUT_END -->"
            )
        return content

    def _merge_multisource_extras(self, extras: Optional[str], bundle) -> Optional[str]:
        blocks = []
        base = str(extras).strip() if extras else ""
        if base:
            blocks.append(base)

        web_search_content = str(getattr(getattr(bundle, "web_search", None), "content", "") or "").strip()
        if web_search_content:
            blocks.append(f"## 网页搜索补充上下文\n{web_search_content}")

        frame_context_content = str(getattr(getattr(bundle, "frame_context", None), "content", "") or "").strip()
        if frame_context_content:
            blocks.append(f"## 视频画面补充上下文\n{frame_context_content}")

        return "\n\n".join(blocks) if blocks else extras

    def _apply_multisource_video_path(self, bundle) -> None:
        frame_context = getattr(bundle, "frame_context", None)
        artifacts = getattr(frame_context, "artifacts", {}) or {}
        video_path = artifacts.get("video_path")
        if video_path:
            self.video_path = Path(video_path)

    def generate(
        self,
        video_url: Union[str, HttpUrl],
        platform: str,
        quality: DownloadQuality = DownloadQuality.medium,
        task_id: Optional[str] = None,
        model_name: Optional[str] = None,
        provider_id: Optional[str] = None,
        link: bool = False,
        screenshot: bool = False,
        _format: Optional[List[str]] = None,
        style: Optional[str] = None,
        extras: Optional[str] = None,
        output_path: Optional[str] = None,
        video_understanding: bool = False,
        video_interval: int = 0,
        grid_size: Optional[List[int]] = None,
        vision_mode: Optional[str] = None,
        max_sampling_points: Optional[int] = None,
        enable_refine_engine: bool = False,
        output_type: str = "note_markdown",
    ) -> NoteResult | None:
        """
        主流程：按步骤依次下载、转写、GPT 总结、截图/链接处理、存库、返回 NoteResult。

        :param video_url: 视频或音频链接
        :param platform: 平台名称，对应 SUPPORT_PLATFORM_MAP 中的键
        :param quality: 下载音频的质量枚举
        :param task_id: 用于标识本次任务的唯一 ID，亦用于状态文件和缓存文件命名
        :param model_name: GPT 模型名称
        :param provider_id: 模型供应商 ID
        :param link: 是否在笔记中插入视频片段链接
        :param screenshot: 是否在笔记中替换 Screenshot 标记为图片
        :param _format: 包含 'link' 或 'screenshot' 等字符串的列表，决定后续处理
        :param style: GPT 生成笔记的风格
        :param extras: 额外参数，传递给 GPT
        :param output_path: 下载输出目录（可选）
        :param video_understanding: 是否需要视频拼图理解（生成缩略图）
        :param video_interval: 视频帧截取间隔（秒），仅在 video_understanding 为 True 时生效
        :param grid_size: 生成缩略图时的网格大小，如 [3, 3]
        :return: NoteResult 对象，包含 markdown 文本、转写结果和音频元信息
        """
        if grid_size is None:
            grid_size = []

        try:
            logger.info(f"开始生成笔记 (task_id={task_id})")
            if is_note_task_canceled(task_id or ""):
                logger.info("任务已取消，跳过生成 (task_id=%s)", task_id)
                return None
            self._update_status(task_id, TaskStatus.PARSING)

            # 获取下载器与 GPT 实例

            downloader = self._get_downloader(platform)
            gpt = self._get_gpt(model_name, provider_id)

            # 缓存文件路径
            markdown_cache_file = NOTE_OUTPUT_DIR / f"{task_id}_markdown.md"
            formats = _format or []
            screenshot_enabled = screenshot or "screenshot" in formats
            frame_timestamps = self._build_vision_frame_timestamps(
                task_id=task_id,
                transcript=None,
                video_understanding=video_understanding,
                video_interval=video_interval,
                vision_mode=vision_mode,
                max_sampling_points=max_sampling_points,
            )

            try:
                bundle = MultiSourceVideoCollector().collect(
                    task_id=task_id or "video-task",
                    video_url=str(video_url),
                    platform=platform,
                    downloader=downloader,
                    gpt=gpt,
                    transcriber=self.transcriber,
                    quality=quality,
                    output_path=output_path,
                    screenshot=screenshot_enabled or video_understanding,
                    grid_size=grid_size,
                    frame_timestamps=frame_timestamps,
                )
                audio_meta = bundle.audio_meta
                transcript = bundle.transcript
                extras = self._merge_multisource_extras(extras, bundle)
                self._apply_multisource_video_path(bundle)
            except Exception as exc:
                return self._generate_web_fallback(
                    task_id=task_id,
                    video_url=video_url,
                    model_name=model_name,
                    provider_id=provider_id,
                    formats=formats,
                    style=style,
                    extras=extras,
                    output_type=output_type,
                    failed_stage="视频/音频下载",
                    exc=exc,
                )

            if audio_meta is None:
                return self._generate_web_fallback(
                    task_id=task_id,
                    video_url=video_url,
                    model_name=model_name,
                    provider_id=provider_id,
                    formats=formats,
                    style=style,
                    extras=extras,
                    output_type=output_type,
                    failed_stage="视频/音频下载",
                    exc=RuntimeError("音频元信息为空"),
                )

            if transcript is None or not transcript.segments:
                return self._generate_web_fallback(
                    task_id=task_id,
                    video_url=video_url,
                    model_name=model_name,
                    provider_id=provider_id,
                    formats=formats,
                    style=style,
                    extras=extras,
                    output_type=output_type,
                    failed_stage="音频转写",
                    exc=RuntimeError("转写结果为空"),
                )

            if is_note_task_canceled(task_id or ""):
                logger.info("任务已取消，跳过总结 (task_id=%s)", task_id)
                return None

            # 3. GPT 总结
            markdown = self._summarize_text(
                task_id=task_id,
                audio_meta=audio_meta,
                transcript=transcript,
                gpt=gpt,
                provider_id=provider_id,
                markdown_cache_file=markdown_cache_file,
                platform=platform,
                link=link,
                screenshot=screenshot,
                formats=_format or [],
                style=style,
                extras=extras,
                video_understanding=video_understanding,
                vision_mode=vision_mode,
                max_sampling_points=max_sampling_points,
                enable_refine_engine=enable_refine_engine,
                output_type=output_type,
                video_img_urls=self.video_img_urls,
            )

            markdown = self._apply_style_output_formats(markdown, style)

            if is_note_task_canceled(task_id or ""):
                logger.info("任务已取消，跳过保存 (task_id=%s)", task_id)
                return None

            # 4. 截图 & 链接替换
            if _format:
                markdown = self._post_process_markdown(
                    markdown=markdown,
                    video_path=self.video_path,
                    formats=_format,
                    audio_meta=audio_meta,
                    platform=platform,
                )

            markdown = prepend_source_link(markdown, str(video_url))
            asset_result = localize_remote_markdown_images(
                task_id=task_id,
                markdown=markdown,
                source_url=str(video_url),
            )
            markdown = asset_result.markdown or markdown
            markdown_cache_file.write_text(markdown, encoding="utf-8")
            write_markdown_assets_sidecar(note_output_dir(), task_id, asset_result.assets)

            # 5. 保存记录到数据库
            self._update_status(task_id, TaskStatus.SAVING)
            self._save_metadata(video_id=audio_meta.video_id, platform=platform, task_id=task_id)
            _run_transcript_ingestion_best_effort(
                task_id=task_id,
                source_url=(audio_meta.raw_info or {}).get("webpage_url") or str(video_url),
                title=audio_meta.title,
                segments=_transcript_segments_to_dicts(transcript.segments),
            )

            # 6. 完成
            self._update_status(task_id, TaskStatus.SUCCESS)
            logger.info(f"笔记生成成功 (task_id={task_id})")
            self._schedule_summary_sidecars(
                task_id=task_id,
                video_url=str(video_url),
                platform=platform,
                audio_meta=audio_meta,
                transcript=transcript,
                markdown=markdown,
                user_options=self._build_summary_sidecar_options(
                    output_type=output_type,
                    style=style,
                    formats=_format or [],
                    extras=extras,
                    video_understanding=video_understanding,
                    vision_mode=vision_mode,
                    max_sampling_points=max_sampling_points,
                    enable_refine_engine=enable_refine_engine,
                    video_img_urls=self.video_img_urls,
                    model_name=getattr(gpt, "model", None),
                    provider_id=provider_id,
                ),
                gpt=gpt,
            )
            return NoteResult(markdown=markdown, transcript=transcript, audio_meta=audio_meta)

        except Exception as exc:
            logger.error(f"生成笔记流程异常 (task_id={task_id})：{exc}", exc_info=True)
            self._update_status(task_id, TaskStatus.FAILED, message=normalize_model_error(exc))
            return None

    def _build_vision_frame_timestamps(
        self,
        task_id: Optional[str],
        transcript: Optional[TranscriptResult],
        video_understanding: bool,
        video_interval: int = 0,
        vision_mode: Optional[str] = None,
        max_sampling_points: Optional[int] = None,
    ) -> Optional[List[float]]:
        if not video_understanding or not transcript or vision_mode != "smart_sampling":
            return None
        from app.models.summary_input import MetaContext, SummaryInput, TranscriptContext

        summary_input = SummaryInput(
            input_id=task_id or "vision-sampling",
            input_type="video_link",
            source_url=None,
            platform=None,
            title=None,
            user_goal=None,
            user_options={
                "vision_mode": vision_mode,
                "video_interval": video_interval,
                "max_sampling_points": max_sampling_points,
            },
            page_context=None,
            transcript_context=TranscriptContext(
                language=transcript.language,
                full_text=transcript.full_text,
                segments=transcript.segments,
                duration=None,
            ),
            vision_context=None,
            social_context=None,
            meta_context=MetaContext(resource_type="video_link"),
        )
        policy = VisionSamplingPlanner().plan(summary_input)
        return policy.get("timestamps") or None

    @staticmethod
    def delete_note(video_id: str, platform: str) -> int:
        """
        删除数据库中对应 video_id 与 platform 的任务记录

        :param video_id: 视频 ID
        :param platform: 平台标识
        :return: 删除的记录数
        """
        logger.info(f"删除笔记记录 (video_id={video_id}, platform={platform})")
        return delete_task_by_video(video_id, platform)

    # ---------------- 私有方法 ----------------

    def _generate_web_fallback(
        self,
        *,
        task_id: Optional[str],
        video_url: Union[str, HttpUrl],
        model_name: Optional[str],
        provider_id: Optional[str],
        formats: List[str],
        style: Optional[str],
        extras: Optional[str],
        output_type: str,
        failed_stage: str,
        exc: Exception,
    ) -> NoteResult:
        fallback_task_id = task_id or "web-fallback"
        message = f"{failed_stage}失败，已切换网页抓取：{exc}"
        logger.warning("视频链路失败，切换网页兜底 (task_id=%s, stage=%s): %s", task_id, failed_stage, exc)
        failed_status = TaskStatus.TRANSCRIBING if "转写" in failed_stage else TaskStatus.DOWNLOADING
        self._update_status(fallback_task_id, failed_status, message=message)
        self._update_status(fallback_task_id, TaskStatus.PARSING, message=message)

        from app.services.web_note import WebNoteGenerator

        note = WebNoteGenerator().generate(
            web_url=str(video_url),
            task_id=fallback_task_id,
            model_name=model_name,
            provider_id=provider_id,
            _format=formats,
            style=style,
            extras=extras,
            output_type=output_type,
        )
        if note and note.markdown:
            return note
        raise RuntimeError(f"{failed_stage}失败，网页兜底也失败：{exc}")

    def _init_transcriber(self) -> Transcriber:
        """
        根据环境变量 TRANSCRIBER_TYPE 动态获取并实例化转写器
        """
        if self.transcriber_type not in _transcribers:
            logger.error(f"未找到支持的转写器：{self.transcriber_type}")
            raise Exception(f"不支持的转写器：{self.transcriber_type}")

        logger.info(f"使用转写器：{self.transcriber_type}, model_size={self.model_size}")
        return get_transcriber(transcriber_type=self.transcriber_type, model_size=self.model_size)

    def _get_gpt(self, model_name: Optional[str], provider_id: Optional[str]) -> GPT:
        """
        根据 provider_id 获取对应的 GPT 实例
        :param model_name: GPT 模型名称
        :param provider_id: 供应商 ID
        :return: GPT 实例
        """
        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            logger.error(f"[get_gpt] 未找到模型供应商: provider_id={provider_id}")
            raise ProviderError(code=ProviderErrorEnum.NOT_FOUND,message=ProviderErrorEnum.NOT_FOUND.message)
        logger.info(f"创建 GPT 实例 {provider_id}")
        config = ModelConfig(
            api_key=ModelService._resolve_api_key(provider),
            base_url=provider["base_url"],
            model_name=model_name,
            provider=provider["id"],
            name=provider["name"],
        )
        return GPTFactory().from_config(config)

    def _get_downloader(self, platform: str) -> Downloader:
        """
        根据平台名称获取对应的下载器实例

        :param platform: 平台标识，需在 SUPPORT_PLATFORM_MAP 中
        :return: 对应的 Downloader 子类实例
        """
        downloader_cls = SUPPORT_PLATFORM_MAP.get(platform)
        logger.debug(f"实例化下载器 -  {platform}")
        instance = None
        if not downloader_cls:
            logger.error(f"不支持的平台：{platform}")
            raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                            message=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.message)
        try:
            instance = downloader_cls
        except Exception as e:
            logger.error(f"实例化下载器失败：{e}")


        logger.info(f"使用下载器：{downloader_cls.__class__}")
        return instance

    def _update_status(self, task_id: Optional[str], status: Union[str, TaskStatus], message: Optional[str] = None):
        """
        创建或更新 {task_id}.status.json，并同步 note_progress 消息

        :param task_id: 任务唯一 ID
        :param status: TaskStatus 枚举或自定义状态字符串
        :param message: 可选消息，用于记录失败原因等
        """
        try:
            emit_note_progress(task_id, status, message)
        except Exception as e:
            logger.error(f"写入状态文件失败 (task_id={task_id})：{e}")

    def _handle_exception(self, task_id, exc):
        logger.error(f"任务异常 (task_id={task_id})", exc_info=True)
        error_message = getattr(exc, 'detail', str(exc))
        if isinstance(error_message, dict):
            try:
                error_message = json.dumps(error_message, ensure_ascii=False)
            except:
                error_message = str(error_message)
        self._update_status(task_id, TaskStatus.FAILED, message=normalize_model_error(error_message))

    def _download_media(
        self,
        downloader: Downloader,
        video_url: Union[str, HttpUrl],
        quality: DownloadQuality,
        audio_cache_file: Path,
        status_phase: TaskStatus,
        platform: str,
        output_path: Optional[str],
        screenshot: bool,
        video_understanding: bool,
        video_interval: int,
        grid_size: List[int],
        skip_download: bool = False,
        frame_timestamps: Optional[List[float]] = None,
    ) -> AudioDownloadResult | None:
        """
        1. 检查音频缓存；若不存在，则根据需要下载音频或视频（若需截图/可视化）。
        2. 如果需要视频，则先下载视频并生成缩略图集，再下载音频。
        3. 返回 AudioDownloadResult

        :param downloader: Downloader 实例
        :param video_url: 视频/音频链接
        :param quality: 音频下载质量
        :param audio_cache_file: 本地缓存 JSON 文件路径
        :param status_phase: 对应的状态枚举，如 TaskStatus.DOWNLOADING
        :param platform: 平台标识
        :param output_path: 下载输出目录（可为 None）
        :param screenshot: 是否需要在笔记中插入截图
        :param video_understanding: 是否需要生成缩略图
        :param video_interval: 视频截帧间隔
        :param grid_size: 缩略图网格尺寸
        :return: AudioDownloadResult 对象
        """
        task_id = audio_cache_file.stem.split("_")[0]
        self._update_status(task_id, status_phase)

        need_video = screenshot or video_understanding
        frame_interval = video_interval if video_interval and video_interval > 0 else 6
        if screenshot and not grid_size:
            grid_size = [2, 2]

        # 已有缓存，尝试加载
        if audio_cache_file.exists():
            logger.info(f"检测到音频缓存 ({audio_cache_file})，直接读取")
            try:
                data = json.loads(audio_cache_file.read_text(encoding="utf-8"))
                audio = AudioDownloadResult(**data)
                if need_video and not self.video_path:
                    logger.info("音频缓存命中，但当前任务仍需要视频资源，补拉视频文件")
                    video_path_str = downloader.download_video(video_url)
                    self.video_path = Path(video_path_str)
                    logger.info(f"视频下载完成：{self.video_path}")

                    if grid_size:
                        self.video_img_urls = VideoReader(
                            video_path=str(self.video_path),
                            grid_size=tuple(grid_size),
                            frame_interval=frame_interval,
                            frame_timestamps=frame_timestamps,
                            unit_width=960,
                            unit_height=540,
                            save_quality=80,
                        ).run()
                    else:
                        logger.info("未指定 grid_size，跳过缩略图生成")
                return audio
            except Exception as e:
                logger.warning(f"读取音频缓存失败，将重新下载：{e}")

        # 有字幕且不需要截图/视频理解时，只提取元信息不下载文件
        if skip_download:
            logger.info("已有字幕，仅提取视频元信息（不下载音视频）")
            try:
                audio = downloader.download(
                    video_url=video_url,
                    quality=quality,
                    output_dir=output_path,
                    need_video=False,
                    skip_download=True,
                )
                audio_cache_file.write_text(
                    json.dumps(asdict(audio), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info(f"元信息提取完成 ({audio_cache_file})")
                return audio
            except Exception as exc:
                logger.warning(f"元信息提取失败，将尝试完整下载: {exc}")

        if need_video:
            try:
                logger.info("开始下载视频")
                video_path_str = downloader.download_video(video_url)
                self.video_path = Path(video_path_str)
                logger.info(f"视频下载完成：{self.video_path}")

                if grid_size:
                    self.video_img_urls = VideoReader(
                        video_path=str(self.video_path),
                        grid_size=tuple(grid_size),
                        frame_interval=frame_interval,
                        frame_timestamps=frame_timestamps,
                        unit_width=960,
                        unit_height=540,
                        save_quality=80,
                    ).run()
                else:
                    logger.info("未指定 grid_size，跳过缩略图生成")
            except Exception as exc:
                logger.error(f"视频下载失败：{exc}")
                self._update_status(task_id, TaskStatus.DOWNLOADING, message=f"视频下载失败，准备切换网页抓取：{exc}")
                raise

        # 下载音频
        try:
            logger.info("开始下载音频")
            audio = downloader.download(
                video_url=video_url,
                quality=quality,
                output_dir=output_path,
                need_video=need_video,
            )
            audio_cache_file.write_text(json.dumps(asdict(audio), ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"音频下载并缓存成功 ({audio_cache_file})")
            return audio
        except Exception as exc:
            logger.error(f"音频下载失败：{exc}")
            self._update_status(task_id, TaskStatus.DOWNLOADING, message=f"音频下载失败，准备切换网页抓取：{exc}")
            raise


    def _get_transcript(
        self,
        downloader: Downloader,
        video_url: str,
        audio_file: str,
        transcript_cache_file: Path,
        status_phase: TaskStatus,
        task_id: Optional[str] = None,
    ) -> TranscriptResult | None:
        """
        优先获取平台字幕，没有则 fallback 到音频转写

        :param downloader: 下载器实例
        :param video_url: 视频链接
        :param audio_file: 音频文件路径（用于 fallback 转写）
        :param transcript_cache_file: 缓存文件路径
        :param status_phase: 状态枚举
        :param task_id: 任务 ID
        :return: TranscriptResult 对象
        """
        self._update_status(task_id, status_phase)

        # 已有缓存，直接返回
        if transcript_cache_file.exists():
            logger.info(f"检测到转写缓存 ({transcript_cache_file})，尝试读取")
            try:
                data = json.loads(transcript_cache_file.read_text(encoding="utf-8"))
                transcript = _normalize_transcript_payload(data)
                if transcript:
                    return transcript
            except Exception as e:
                logger.warning(f"加载转写缓存失败，将重新获取：{e}")

        # 1. 先尝试获取平台字幕
        logger.info("尝试获取平台字幕...")
        try:
            transcript = downloader.download_subtitles(video_url)
            if transcript and transcript.segments:
                logger.info(f"成功获取平台字幕，共 {len(transcript.segments)} 段")
                # 缓存结果
                transcript_cache_file.write_text(
                    json.dumps(asdict(transcript), ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                return transcript
            else:
                logger.info("平台无可用字幕，将使用音频转写")
        except Exception as e:
            logger.warning(f"获取平台字幕失败: {e}，将使用音频转写")

        # 2. Fallback 到音频转写
        return self._transcribe_audio(
            audio_file=audio_file,
            transcript_cache_file=transcript_cache_file,
            status_phase=status_phase,
        )

    def _transcribe_audio(
        self,
        audio_file: str,
        transcript_cache_file: Path,
        status_phase: TaskStatus,
    ) -> TranscriptResult | None:
        """
        1. 检查转写缓存；若存在则尝试加载，否则调用转写器生成并缓存。
        2. 返回 TranscriptResult 对象

        :param audio_file: 音频文件本地路径
        :param transcript_cache_file: 转写结果缓存路径
        :param status_phase: 对应的状态枚举，如 TaskStatus.TRANSCRIBING
        :return: TranscriptResult 对象
        """
        task_id = transcript_cache_file.stem.split("_")[0]
        self._update_status(task_id, status_phase)

        # 已有缓存，尝试加载
        if transcript_cache_file.exists():
            logger.info(f"检测到转写缓存 ({transcript_cache_file})，尝试读取")
            try:
                data = json.loads(transcript_cache_file.read_text(encoding="utf-8"))
                transcript = _normalize_transcript_payload(data)
                if transcript:
                    return transcript
            except Exception as e:
                logger.warning(f"加载转写缓存失败，将重新转写：{e}")

        # 调用转写器
        try:
            logger.info("开始转写音频")
            transcript = self.transcriber.transcript(file_path=audio_file)
            if not _normalize_transcript_payload(asdict(transcript), "音频转写结果"):
                raise RuntimeError("转写结果为空，无法生成摘要")
            transcript_cache_file.write_text(json.dumps(asdict(transcript), ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"转写并缓存成功 ({transcript_cache_file})")
            return transcript
        except Exception as exc:
            logger.error(f"音频转写失败：{exc}")
            self._update_status(task_id, TaskStatus.TRANSCRIBING, message=f"音频转写失败，准备切换网页抓取：{exc}")
            raise

    def _build_summary_sidecar_options(
        self,
        *,
        output_type: str,
        style: Optional[str],
        formats: List[str],
        extras: Optional[str],
        video_understanding: bool,
        vision_mode: Optional[str],
        max_sampling_points: Optional[int],
        enable_refine_engine: bool,
        video_img_urls: List[str],
        model_name: Optional[str],
        provider_id: str,
    ) -> dict:
        return {
            "output_type": output_type or "note_markdown",
            "style": style,
            "format": formats,
            "extras": extras,
            "video_understanding": video_understanding,
            "vision_mode": vision_mode,
            "max_sampling_points": max_sampling_points,
            "enable_refine_engine": enable_refine_engine,
            "video_img_urls": video_img_urls,
            "model_name": model_name,
            "provider_id": provider_id,
            "enable_wiki": True,
        }

    def _schedule_summary_sidecars(
        self,
        task_id: str,
        video_url: str,
        platform: str,
        audio_meta: AudioDownloadResult,
        transcript: TranscriptResult,
        markdown: str,
        user_options: dict,
        gpt: Optional[GPT] = None,
    ) -> None:
        def _run() -> None:
            try:
                self._build_summary_sidecars(
                    task_id=task_id,
                    video_url=video_url,
                    platform=platform,
                    audio_meta=audio_meta,
                    transcript=transcript,
                    markdown=markdown,
                    user_options=user_options,
                    gpt=gpt,
                )
            except Exception as exc:
                logger.warning(f"启动 Wiki 后台抽取失败，不影响笔记生成: {exc}")

        worker = threading.Thread(target=_run, name=f"wiki-sidecars-{task_id}", daemon=True)
        worker.start()

    def _build_summary_sidecars(
        self,
        task_id: str,
        video_url: str,
        platform: str,
        audio_meta: AudioDownloadResult,
        transcript: TranscriptResult,
        markdown: str,
        user_options: dict,
        gpt: Optional[GPT] = None,
    ) -> None:
        output_dir = note_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)

        inspection = SourceInspector().inspect(video_url)
        normalizer = ContextNormalizer()
        summary_input = normalizer.from_video_task(
            task_id=task_id,
            video_url=video_url,
            platform=platform,
            audio_meta=audio_meta,
            transcript=transcript,
            user_options=user_options,
            inspection=inspection,
        )
        pack = normalizer.build_weighted_pack(summary_input)
        plan = SummaryPlanner().plan(summary_input, pack)
        vision_context = self._build_vision_context_from_policy(
            plan.vision_policy,
            summary_input.user_options.get("video_img_urls", []),
        )
        summary_input.vision_context = vision_context

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
        (output_dir / f"{task_id}_vision_frames.json").write_text(
            json.dumps(asdict(vision_context), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if summary_input.social_context:
            (output_dir / f"{task_id}_social_context.json").write_text(
                json.dumps(asdict(summary_input.social_context), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if summary_input.user_options.get("enable_wiki", True):
            WikiJobStore(output_dir=output_dir).write(task_id, "pending", stage="analysis", detail="Wiki 提取已进入后台队列", recoverable=True)
            update_note_document_wiki_status(task_id, "pending")
            schedule_wiki_extraction(output_dir, task_id, summary_input, markdown, gpt, update_note_document_wiki_status)

    def _build_vision_context_from_policy(self, vision_policy: dict, video_img_urls: list[str]):
        from app.models.summary_input import VisionContext, VisionFrame

        mode = vision_policy.get("mode", "disabled")
        frames = []
        image_urls = video_img_urls or []
        for index, point in enumerate(vision_policy.get("sampling_points", [])):
            image_url = image_urls[min(index, len(image_urls) - 1)] if image_urls else ""
            text = point.get("text") or point.get("reason") or "采样画面"
            frames.append(
                VisionFrame(
                    timestamp=float(point.get("timestamp", 0.0)),
                    image_url=image_url,
                    summary=f"待视觉模型识别：{text}",
                    detected_text=point.get("text"),
                    visual_type=point.get("source", "unknown"),
                    importance=float(point.get("importance", 0.0)),
                )
            )
        return VisionContext(mode=mode, frames=frames)

    def _summarize_text(
        self,
        task_id: str,
        audio_meta: AudioDownloadResult,
        transcript: TranscriptResult,
        gpt: GPT,
        provider_id: str,
        markdown_cache_file: Path,
        platform: str,
        link: bool,
        screenshot: bool,
        formats: List[str],
        style: Optional[str],
        extras: Optional[str],
        video_understanding: bool,
        vision_mode: Optional[str],
        max_sampling_points: Optional[int],
        enable_refine_engine: bool,
        video_img_urls: List[str],
        output_type: str = "note_markdown",
    ) -> str | None:
        """
        调用 GPT 对转写结果进行总结，生成 Markdown 文本并缓存。

        :param audio_meta: AudioDownloadResult 元信息
        :param transcript: TranscriptResult 转写结果
        :param gpt: GPT 实例
        :param markdown_cache_file: Markdown 缓存路径
        :param link: 是否在笔记中插入链接
        :param screenshot: 是否在笔记中生成截图占位
        :param formats: 包含 'link' 或 'screenshot' 的列表
        :param style: GPT 输出风格
        :param extras: GPT 额外参数
        :return: 生成的 Markdown 字符串
        """
        self._update_status(task_id, TaskStatus.SUMMARIZING)
        provider = ProviderService.get_provider_by_id(provider_id)
        if hasattr(gpt, "set_usage_context"):
            gpt.set_usage_context({
                "task_id": task_id,
                "provider_id": provider_id,
                "provider_name": provider["name"] if provider else "unknown",
                "phase": "summarize",
                "platform": platform,
                "video_id": audio_meta.video_id,
                "video_title": audio_meta.title,
                "request_meta": {
                    "link": link,
                    "screenshot": screenshot,
                    "video_understanding": video_understanding,
                    "style": style,
                    "format": formats,
                    "extras_present": bool(extras),
                },
            })

        sidecar_options = {
            "output_type": output_type or "note_markdown",
            "style": style,
            "format": formats,
            "extras": extras,
            "video_understanding": video_understanding,
            "vision_mode": vision_mode,
            "max_sampling_points": max_sampling_points,
            "enable_refine_engine": enable_refine_engine,
            "video_img_urls": video_img_urls,
            "model_name": getattr(gpt, "model", None),
            "provider_id": provider_id,
            "enable_wiki": True,
        }
        try:
            video_url = audio_meta.raw_info.get("webpage_url") or ""
            inspection = SourceInspector().inspect(video_url)
            normalizer = ContextNormalizer()
            summary_input = normalizer.from_video_task(
                task_id=task_id,
                video_url=video_url,
                platform=platform,
                audio_meta=audio_meta,
                transcript=transcript,
                user_options=sidecar_options,
                inspection=inspection,
            )
            pack = normalizer.build_weighted_pack(summary_input)
            plan = SummaryPlanner().plan(summary_input, pack)
            extras = NoteRenderer().build_extras_with_context(extras, pack, plan)
        except Exception as exc:
            logger.warning(f"构建统一总结上下文失败，继续使用原始总结链路: {exc}")
            pack = None
            plan = None

        source = GPTSource(
            title=audio_meta.title,
            segment=transcript.segments,
            tags=audio_meta.raw_info.get("tags", []),
            screenshot=screenshot,
            video_img_urls=video_img_urls,
            link=link,
            _format=formats,
            style=style,
            extras=extras,
            checkpoint_key=task_id,
        )

        try:
            if enable_refine_engine and plan and plan.strategy in ("hybrid", "map_reduce"):
                markdown = self._run_refine_summary(
                    task_id=task_id,
                    audio_meta=audio_meta,
                    transcript=transcript,
                    gpt=gpt,
                    plan=plan,
                    pack=pack,
                    style=style,
                    extras=extras,
                    video_img_urls=video_img_urls,
                )
            else:
                try:
                    markdown = gpt.summarize(source)
                except Exception as exc:
                    if not SummaryRefineEngine._is_final_retryable_error(exc):
                        raise
                    fallback_plan = self._build_fallback_refine_plan(
                        task_id=task_id,
                        plan=plan,
                        output_type=output_type,
                    )
                    logger.warning(
                        "直接总结请求体过大或网关超时，自动切换 map-reduce 兜底 task_id=%s error=%s",
                        task_id,
                        exc,
                    )
                    markdown = self._run_refine_summary(
                        task_id=task_id,
                        audio_meta=audio_meta,
                        transcript=transcript,
                        gpt=gpt,
                        plan=fallback_plan,
                        pack=pack,
                        style=style,
                        extras=extras,
                        video_img_urls=video_img_urls,
                    )
            markdown_cache_file.write_text(markdown, encoding="utf-8")
            logger.info(f"GPT 总结并缓存成功 ({markdown_cache_file})")
            return markdown
        except Exception as exc:
            logger.error(f"GPT 总结失败：{exc}")
            self._handle_exception(task_id, exc)
            raise

    def _run_refine_summary(
        self,
        *,
        task_id: str,
        audio_meta: AudioDownloadResult,
        transcript: TranscriptResult,
        gpt: GPT,
        plan: SummaryPlan,
        pack: Any,
        style: Optional[str],
        extras: Optional[str],
        video_img_urls: List[str],
    ) -> str:
        output_dir = Path(os.getenv("NOTE_OUTPUT_DIR", str(NOTE_OUTPUT_DIR)))
        refine_engine = SummaryRefineEngine()
        result = refine_engine.run(
            task_id=task_id,
            title=audio_meta.title,
            segments=transcript.segments,
            gpt=gpt,
            plan=plan,
            pack=pack,
            style=style,
            extras=extras,
            tags=audio_meta.raw_info.get("tags", []),
            video_img_urls=video_img_urls,
        )
        refine_engine.write_trace(output_dir, task_id, result)
        return result.markdown

    def _build_fallback_refine_plan(
        self,
        *,
        task_id: str,
        plan: Optional[SummaryPlan],
        output_type: str,
    ) -> SummaryPlan:
        if plan and plan.strategy in ("hybrid", "map_reduce"):
            return plan
        return SummaryPlan(
            input_id=getattr(plan, "input_id", None) or task_id,
            output_type=getattr(plan, "output_type", None) or output_type or "note_markdown",
            strategy="map_reduce",
            chunk_policy=getattr(plan, "chunk_policy", None) or {
                "max_segments_per_chunk": SummaryRefineEngine.DEFAULT_MAX_SEGMENTS,
            },
            context_policy=getattr(plan, "context_policy", None) or {},
            vision_policy=getattr(plan, "vision_policy", None) or {},
            render_contract=getattr(plan, "render_contract", None) or build_default_render_contract(output_type or "note_markdown"),
            checkpoint_policy=getattr(plan, "checkpoint_policy", None) or {},
            wiki_policy=getattr(plan, "wiki_policy", None) or {},
        )

    def _post_process_markdown(
        self,
        markdown: str,
        video_path: Optional[Path],
        formats: List[str],
        audio_meta: AudioDownloadResult,
        platform: str,
    ) -> str:
        """
        对生成的 Markdown 做后期处理：插入截图和/或插入链接。

        :param markdown: 原始 Markdown 字符串
        :param video_path: 本地视频路径（可为 None）
        :param formats: 包含 'link' 或 'screenshot' 的列表
        :param audio_meta: AudioDownloadResult 元信息，用于链接替换
        :param platform: 平台标识，用于链接替换
        :return: 处理后的 Markdown 字符串
        """
        markdown = self._normalize_markdown_title(markdown, audio_meta)

        if "screenshot" in formats and video_path:
            try:
                if extract_screenshot_timestamps(markdown):
                    markdown = self._insert_screenshots(markdown, video_path) or markdown
                else:
                    markdown = self._insert_fallback_screenshot(markdown, video_path, audio_meta) or markdown
            except Exception as exc:
                logger.warning("截图插入失败，跳过该步骤")

        if "link" in formats:
            try:
                markdown = replace_content_markers(markdown, video_id=audio_meta.video_id, platform=platform)
            except Exception as e:
                logger.warning(f"链接插入失败，跳过该步骤：{e}")

        return markdown

    def _insert_fallback_screenshot(
        self,
        markdown: str,
        video_path: Path,
        audio_meta: AudioDownloadResult,
    ) -> str | None:
        timestamps = self._fallback_screenshot_timestamps(getattr(audio_meta, "duration", 0))
        screenshot_urls: list[str] = []
        for index, timestamp in enumerate(timestamps):
            img_path = generate_screenshot(str(video_path), str(IMAGE_OUTPUT_DIR), timestamp, index)
            img_file = Path(img_path)
            if not img_file.exists() or img_file.stat().st_size <= 0:
                logger.warning("fallback 截图文件不存在或为空，跳过: %s", img_path)
                continue
            screenshot_urls.append(f"{IMAGE_BASE_URL.rstrip('/')}/{img_file.name}")

        if not screenshot_urls:
            return markdown

        screenshot_block = "".join(f"![]({img_url})\n\n" for img_url in screenshot_urls)

        lines = markdown.splitlines(keepends=True)
        if lines and lines[0].lstrip().startswith("#"):
            insertion_index = 1
            while insertion_index < len(lines) and not lines[insertion_index].strip():
                insertion_index += 1
            lines.insert(insertion_index, "\n")
            lines.insert(insertion_index + 1, screenshot_block)
            return "".join(lines)
        return f"{screenshot_block}{markdown}"

    def _insert_screenshots(self, markdown: str, video_path: Path) -> str | None | Any:
        """
        扫描 Markdown 文本中所有 Screenshot 标记，并替换为实际生成的截图链接。

        :param markdown: 含有 *Screenshot-mm:ss 或 Screenshot-[mm:ss] 标记的 Markdown 文本
        :param video_path: 本地视频文件路径
        :return: 替换后的 Markdown 字符串
        """
        matches: List[Tuple[str, int]] = extract_screenshot_timestamps(markdown)
        for idx, (marker, ts) in enumerate(matches):
            try:
                img_path = generate_screenshot(str(video_path), str(IMAGE_OUTPUT_DIR), ts, idx)
                filename = Path(img_path).name
                # 构建前端可访问的 URL，例如 /static/screenshots/{filename}
                img_url = f"{IMAGE_BASE_URL.rstrip('/')}/{filename}"
                markdown = markdown.replace(marker, f"![]({img_url})", 1)
            except Exception as exc:
                logger.error(f"生成截图失败 (timestamp={ts})：{exc}")
                # self._handle_exception(task_id, exc)
                return None
        return markdown

    @staticmethod
    def _normalize_duration_seconds(duration: Any) -> int:
        raw_duration = float(duration or 0)
        if raw_duration <= 0:
            return 0
        if raw_duration > 1000:
            raw_duration = raw_duration / 1000.0
        return max(int(raw_duration), 0)

    def _fallback_screenshot_timestamps(self, duration: Any) -> list[int]:
        duration_seconds = self._normalize_duration_seconds(duration)
        if duration_seconds <= 0:
            return [1, 2, 3]

        preferred_ratios = (0.2, 0.5, 0.8)
        timestamps: list[int] = []
        for ratio in preferred_ratios:
            timestamp = min(max(int(duration_seconds * ratio), 1), duration_seconds)
            if timestamp not in timestamps:
                timestamps.append(timestamp)

        if not timestamps:
            timestamps.append(min(max(duration_seconds // 2, 1), duration_seconds))
        return timestamps

    def _normalize_markdown_title(self, markdown: str, audio_meta: AudioDownloadResult) -> str:
        lines = markdown.splitlines()
        if not lines:
            return markdown

        title_index = next((index for index, line in enumerate(lines) if line.lstrip().startswith("# ")), None)
        if title_index is None:
            return markdown

        raw_title = re.sub(r"^\s*#\s+", "", lines[title_index]).strip()
        if raw_title and raw_title not in GENERIC_MARKDOWN_TITLES:
            return markdown

        derived_title = self._derive_title_from_markdown(markdown, getattr(audio_meta, "title", ""))
        if not derived_title or derived_title == raw_title:
            return markdown

        lines[title_index] = f"# {derived_title}"
        return "\n".join(lines)

    @staticmethod
    def _derive_title_from_markdown(markdown: str, fallback_title: str = "") -> str:
        content_lines = markdown.splitlines()
        plain_lines: list[str] = []
        for line in content_lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("> 来源链接："):
                continue
            if stripped.startswith("#"):
                continue
            if stripped.startswith("![]("):
                continue
            plain_lines.append(stripped)

        body_text = " ".join(plain_lines)
        if body_text:
            for pattern in (r"“([^”]{4,40})”", r"《([^》]{2,40})》", r"\"([^\"]{4,40})\""):
                match = re.search(pattern, body_text)
                if match:
                    return match.group(1).strip()

            normalized = re.sub(r"^(视频|这期视频|本视频)(围绕|聚焦|主要讲|重点讲|讨论)?", "", body_text).strip("：:，, ")
            first_sentence = re.split(r"[。！？!?]", normalized, maxsplit=1)[0].strip()
            first_clause = re.split(r"[；;]", first_sentence, maxsplit=1)[0].strip()
            compact = re.sub(r"\s+", " ", first_clause).strip("，,：:、 ")
            if compact:
                return compact[:28].rstrip("，,：:、 ")

        return (fallback_title or "").strip()

    @staticmethod
    def _extract_screenshot_timestamps(markdown: str) -> List[Tuple[str, int]]:
        """
        从 Markdown 文本中提取所有 '*Screenshot-mm:ss' 或 'Screenshot-[mm:ss]' 标记，
        返回 [(原始标记文本, 时间戳秒数), ...] 列表。

        :param markdown: 原始 Markdown 文本
        :return: 标记与对应时间戳秒数的列表
        """
        return extract_screenshot_timestamps(markdown)

    def _save_metadata(self, video_id: str, platform: str, task_id: str) -> None:
        """
        将生成的笔记任务记录插入数据库

        :param video_id: 视频 ID
        :param platform: 平台标识
        :param task_id: 任务 ID
        """
        try:
            insert_video_task(video_id=video_id, platform=platform, task_id=task_id)
            logger.info(f"已保存任务记录到数据库 (video_id={video_id}, platform={platform}, task_id={task_id})")
        except Exception as e:
            logger.error(f"保存任务记录失败：{e}")
