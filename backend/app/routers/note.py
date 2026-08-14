# app/routers/note.py
from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Request
from pydantic import BaseModel, validator, model_validator
from dataclasses import asdict

from app.db.video_task_dao import get_task_by_video
from app.enmus.exception import NoteErrorEnum
from app.enmus.note_enums import DownloadQuality
from app.exceptions.note import NoteError
from app.services.collector_status import build_collector_timings
from app.services.note import NoteGenerator, logger
from app.services.note_document_store import delete_note_task_artifacts
from app.services.note_task_store import cancel_note_task, is_note_task_canceled
from app.services.web_note import WebNoteGenerator
from app.services.conversation_import_service import ConversationImportRequest, ConversationImportService
from app.services.file_ingest_service import detect_uploaded_file_kind, extract_uploaded_file_content, resolve_uploaded_file_path
from app.services.task_status_writer import (
    NOTE_PROGRESS_STEPS,
    emit_note_failed,
    emit_note_progress,
    emit_note_result,
    get_registered_task_input,
    register_task_conversation,
)
from app.services.task_serial_executor import task_serial_executor
from app.utils.response import ResponseWrapper as R
from app.utils.storage_paths import note_output_dir, upload_dir
from app.utils.url_parser import extract_video_id
from app.validators.video_url_validator import is_supported_video_url
from fastapi.responses import FileResponse, Response, StreamingResponse
import httpx
from app.enmus.task_status_enums import TaskStatus
from app.services.conversation_store import get_latest_user_message, upsert_conversation
from app.models.audio_model import AudioDownloadResult
from app.models.gpt_model import GPTSource
from app.models.notes_model import NoteResult
from app.models.summary_input import DocumentContext
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.services.ingestion.materialization import IngestionMaterializationService
from app.services.ingestion.pipeline import IngestionPipeline
from app.services.ingestion.types import IngestionRequest

# from app.services.downloader import download_raw_audio
# from app.services.whisperer import transcribe_audio

router = APIRouter()


class RecordRequest(BaseModel):
    video_id: str
    platform: str
    task_id: Optional[str] = None


class VideoRequest(BaseModel):
    video_url: str
    platform: str
    force_web_fallback: Optional[bool] = False
    quality: DownloadQuality
    screenshot: Optional[bool] = False
    link: Optional[bool] = False
    model_name: str
    provider_id: str
    conversation_id: Optional[str] = None
    task_id: Optional[str] = None
    format: Optional[list] = []
    style: str = None
    extras: Optional[str]=None
    output_type: Optional[str] = "note_markdown"
    video_understanding: Optional[bool] = False
    video_interval: Optional[int] = 0
    grid_size: Optional[list] = []
    vision_mode: Optional[str] = None
    max_sampling_points: Optional[int] = None
    enable_refine_engine: Optional[bool] = False
    # 客户端（如浏览器插件）已经在用户浏览器里抓到字幕，直接传给后端复用，
    # 跳过 download_subtitles 和音频转写。形如：
    #   {"language": "zh", "full_text": "...", "segments": [{"start","end","text"}, ...]}
    prefetched_transcript: Optional[dict] = None
    retry_attempt_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_supported_request(self):
        url = str(self.video_url)
        parsed = urlparse(url)
        if self.platform == "web_link":
            if parsed.scheme not in ("http", "https"):
                raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                                message=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.message)
            return self

        if parsed.scheme in ("http", "https"):
            # 是网络链接，继续用原有平台校验
            if not is_supported_video_url(url):
                raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                                message=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.message)
        return self


class UploadedFileIngestRequest(BaseModel):
    file_url: str
    file_name: str
    content_type: Optional[str] = None
    mode: str
    conversation_id: Optional[str] = None
    model_name: Optional[str] = None
    provider_id: Optional[str] = None
    format: Optional[list] = []
    style: Optional[str] = None
    extras: Optional[str] = None


NOTE_OUTPUT_DIR = str(note_output_dir())
UPLOAD_DIR = str(upload_dir())
MAX_UPLOAD_BYTES = int(os.getenv("NOTEMELD_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
ALLOWED_UPLOAD_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".rtf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".mp3",
    ".m4a",
    ".wav",
    ".aac",
    ".ogg",
    ".flac",
    ".opus",
    ".mp4",
    ".mov",
    ".m4v",
    ".avi",
    ".mkv",
    ".webm",
}
ALLOWED_UPLOAD_CONTENT_TYPES = {
    "text/markdown",
    "text/plain",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "image/png",
    "image/jpeg",
    "image/webp",
}
IMAGE_PROXY_ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.getenv(
        "NOTEMELD_IMAGE_PROXY_HOSTS",
        "i0.hdslb.com,i1.hdslb.com,i2.hdslb.com,archive.biliimg.com,"
        "p3.douyinpic.com,p5.douyinpic.com,p6.douyinpic.com,p9.douyinpic.com,"
        "p3-sign.douyinpic.com,p5-sign.douyinpic.com,p6-sign.douyinpic.com,p9-sign.douyinpic.com,"
        "p3-pc-sign.douyinpic.com,p5-pc-sign.douyinpic.com,p6-pc-sign.douyinpic.com,p9-pc-sign.douyinpic.com,"
        "i.ytimg.com,yt3.ggpht.com,"
        "p1.a.yximgs.com,p2.a.yximgs.com,p3.a.yximgs.com,p5.a.yximgs.com,tx2.a.yximgs.com,tx3.a.yximgs.com",
    ).split(",")
    if host.strip()
}

IMAGE_PROXY_REFERERS = {
    "www.bilibili.com/": {"i0.hdslb.com", "i1.hdslb.com", "i2.hdslb.com", "archive.biliimg.com"},
    "www.douyin.com/": {
        "p3.douyinpic.com",
        "p5.douyinpic.com",
        "p6.douyinpic.com",
        "p9.douyinpic.com",
        "p3-sign.douyinpic.com",
        "p5-sign.douyinpic.com",
        "p6-sign.douyinpic.com",
        "p9-sign.douyinpic.com",
        "p3-pc-sign.douyinpic.com",
        "p5-pc-sign.douyinpic.com",
        "p6-pc-sign.douyinpic.com",
        "p9-pc-sign.douyinpic.com",
    },
    "www.youtube.com/": {"i.ytimg.com", "yt3.ggpht.com"},
    "www.kuaishou.com/": {
        "p1.a.yximgs.com",
        "p2.a.yximgs.com",
        "p3.a.yximgs.com",
        "p5.a.yximgs.com",
        "tx2.a.yximgs.com",
        "tx3.a.yximgs.com",
    },
}


def _resolve_image_proxy_referer(hostname: str) -> str:
    normalized_host = (hostname or "").strip().lower()
    for referer_host, allowed_hosts in IMAGE_PROXY_REFERERS.items():
        if normalized_host in allowed_hosts:
            return f"https://{referer_host}"
    return "https://www.bilibili.com/"


def _sanitize_upload_name(file_name: str) -> str:
    return Path(file_name or "upload.bin").name or "upload.bin"


def _detect_upload_signature(file_name: str, content: bytes) -> bool:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if suffix == ".webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if suffix == ".pdf":
        return content.startswith(b"%PDF")
    if suffix in {".docx", ".pptx"}:
        return content.startswith(b"PK\x03\x04")
    return True


def _validate_upload_payload(file_name: str, content_type: str, content: bytes) -> None:
    suffix = Path(file_name).suffix.lower()
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=415, detail="不支持的文件类型")
    if normalized_type and (
        normalized_type in ALLOWED_UPLOAD_CONTENT_TYPES
        or normalized_type in {"application/octet-stream", "binary/octet-stream"}
        or normalized_type.startswith("audio/")
        or normalized_type.startswith("video/")
    ):
        pass
    elif normalized_type:
        raise HTTPException(status_code=415, detail="不支持的 content type")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="上传文件过大")
    if not _detect_upload_signature(file_name, content):
        raise HTTPException(status_code=415, detail="文件内容与扩展名不匹配")


def _resolve_upload_path_by_id(upload_id: str) -> Path:
    matches = sorted(Path(UPLOAD_DIR).glob(f"{upload_id}.*"))
    if len(matches) != 1:
        raise HTTPException(status_code=404, detail="上传文件不存在")
    return matches[0]


def _is_public_ip(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return ip.is_global


def _with_live_stage_elapsed(status_content: dict) -> dict:
    status = status_content.get("status")
    if status not in NOTE_PROGRESS_STEPS or status == TaskStatus.SUCCESS.value:
        return status_content

    stage_started_at = status_content.get("stage_started_at")
    stage_timings = status_content.get("stage_timings")
    if not stage_started_at or not isinstance(stage_timings, dict):
        return status_content

    try:
        started_at = datetime.fromisoformat(stage_started_at)
    except Exception:
        return status_content

    next_content = dict(status_content)
    next_timings = dict(stage_timings)
    current_timing = dict(next_timings.get(status) or {})
    current_timing["status"] = "running"
    current_timing["elapsed_ms"] = max(0, int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000))
    next_timings[status] = current_timing
    next_content["stage_timings"] = next_timings
    return next_content


def _parse_note_user_input(content: str) -> tuple[str, str | None]:
    lines = [line.rstrip() for line in content.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return "", None

    source = lines[0].strip()
    extras = "\n".join(lines[1:]).strip() or None
    return source, extras


def _resolve_note_request_input(data: VideoRequest) -> tuple[str, str | None]:
    conversation_id = data.conversation_id
    if not conversation_id:
        raise HTTPException(status_code=400, detail="generate_note 需要 conversation_id 以读取最后一条用户输入")

    if data.task_id:
        task_input = get_registered_task_input(data.task_id)
        source_url = str(task_input.get("source_url") or "").strip()
        if source_url:
            extras = task_input.get("extras")
            return source_url, str(extras) if extras is not None else None
        request_source = str(data.video_url or "").strip()
        if request_source:
            return request_source, data.extras

    latest_message = get_latest_user_message(conversation_id)
    if latest_message is None:
        raise HTTPException(status_code=400, detail="未找到可用于生成笔记的用户输入消息")

    source, extras = _parse_note_user_input(latest_message.get("content", ""))
    if not source:
        raise HTTPException(status_code=400, detail="最后一条用户输入消息缺少有效内容")
    return source, extras


def _build_document_transcript(content: str) -> TranscriptResult:
    parts = [part.strip() for part in re.split(r"\n{2,}", content) if part.strip()]
    if not parts:
        parts = [content.strip()]
    segments = [
        TranscriptSegment(start=float(index), end=float(index + 1), text=part)
        for index, part in enumerate(parts)
        if part
    ]
    if not segments:
        raise ValueError("上传文档中没有可用文本")
    full_text = "\n\n".join(segment.text for segment in segments)
    return TranscriptResult(language="zh", full_text=full_text, segments=segments)


def save_note_to_file(task_id: str, note):
    if is_note_task_canceled(task_id):
        return
    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json"), "w", encoding="utf-8") as f:
        json.dump(asdict(note), f, ensure_ascii=False, indent=2)


def _extract_note_result_title(markdown: str | None, fallback: str = "") -> str:
    for line in (markdown or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback.strip()


def _wiki_status_for_task(task_id: str) -> str:
    from app.services.wiki_job_store import WikiJobStore

    job_payload = WikiJobStore(output_dir=Path(NOTE_OUTPUT_DIR)).read(task_id)
    job_status = job_payload.get("status")
    if job_status == "success":
        return "success"
    if job_status == "failed":
        return "failed"
    return "pending"


def _append_note_result_for_task(task_id: str, note, source_url: str, platform: str) -> None:
    if is_note_task_canceled(task_id):
        return
    title = _extract_note_result_title(
        getattr(note, "markdown", ""),
        getattr(getattr(note, "audio_meta", None), "title", "") or source_url,
    ) or "生成笔记"
    emit_note_result(
        task_id,
        {
            "message_id": f"note-result-{task_id}",
            "content": title,
            "title": title,
            "source_url": source_url,
            "platform": platform,
            "wiki_status": _wiki_status_for_task(task_id),
        },
    )


def _persist_prefetched_transcript(task_id: str, transcript: dict) -> None:
    """把客户端预取的字幕写到 NoteGenerator 期望的转写缓存文件里。

    NoteGenerator.generate 会优先读 <task_id>_transcript.json，命中即跳过 download_subtitles
    与音频转写流程。要求字段：language(可空)/full_text/segments[{start,end,text}]
    """
    segments = transcript.get("segments") or []
    cleaned_segments = []
    for s in segments:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        cleaned_segments.append({
            "start": float(s.get("start", 0)),
            "end": float(s.get("end", 0)),
            "text": text,
        })
    if not cleaned_segments:
        raise ValueError("prefetched_transcript 没有可用的 segments")

    full_text = transcript.get("full_text") or " ".join(s["text"] for s in cleaned_segments)
    payload = {
        "language": transcript.get("language") or "zh",
        "full_text": full_text,
        "segments": cleaned_segments,
    }

    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    target = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}_transcript.json")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"已写入客户端预取字幕缓存: {target} ({len(cleaned_segments)} 段)")


def run_note_task(task_id: str, video_url: str, platform: str, quality: DownloadQuality,
                  link: bool = False, screenshot: bool = False, model_name: str = None, provider_id: str = None,
                  _format: list = None, style: str = None, extras: str = None, video_understanding: bool = False,
                  video_interval=0, grid_size=[], vision_mode: str = None, max_sampling_points: int = None,
                  enable_refine_engine: bool = False, output_type: str = "note_markdown"
                  ):

    if not model_name or not provider_id:
        raise HTTPException(status_code=400, detail="请选择模型和提供者")

    def _execute_note_task():
        return NoteGenerator().generate(
            video_url=video_url,
            platform=platform,
            quality=quality,
            task_id=task_id,
            model_name=model_name,
            provider_id=provider_id,
            link=link,
            _format=_format,
            style=style,
            extras=extras,
            screenshot=screenshot,
            video_understanding=video_understanding,
            video_interval=video_interval,
            grid_size=grid_size,
            vision_mode=vision_mode,
            max_sampling_points=max_sampling_points,
            enable_refine_engine=enable_refine_engine,
            output_type=output_type,
        )

    logger.info(f"任务进入执行队列 (task_id={task_id})")
    note = task_serial_executor.run(_execute_note_task)
    logger.info(f"Note generated: {task_id}")
    if not note or not note.markdown:
        logger.warning(f"任务 {task_id} 执行失败，跳过保存")
        status_path = Path(NOTE_OUTPUT_DIR) / f"{task_id}.status.json"
        try:
            if status_path.exists():
                status_payload = json.loads(status_path.read_text(encoding="utf-8"))
                if (
                    status_payload.get("status") == TaskStatus.FAILED.value
                    and str(status_payload.get("message") or "").strip()
                ):
                    return
        except Exception:
            pass
        emit_note_failed(task_id, "笔记生成失败，请重试")
        return
    save_note_to_file(task_id, note)
    _append_note_result_for_task(task_id, note, str(video_url), platform)

    # 自动建立向量索引（用于 AI 问答），失败不影响笔记生成
    try:
        from app.services.vector_store import VectorStoreManager
        VectorStoreManager().index_task(task_id)
    except Exception as e:
        logger.warning(f"向量索引失败（不影响笔记）: {e}")


def run_web_note_task(
    task_id: str,
    web_url: str,
    model_name: str = None,
    provider_id: str = None,
    _format: list = None,
    style: str = None,
    extras: str = None,
    output_type: str = "note_markdown",
):
    if not model_name or not provider_id:
        raise HTTPException(status_code=400, detail="请选择模型和提供者")

    logger.info(f"网页任务进入执行队列 (task_id={task_id})")
    note = WebNoteGenerator().generate(
        web_url=web_url,
        task_id=task_id,
        model_name=model_name,
        provider_id=provider_id,
        _format=_format,
        style=style,
        extras=extras,
        output_type=output_type,
    )
    logger.info(f"Web note generated: {task_id}")
    if not note or not note.markdown:
        logger.warning(f"网页任务 {task_id} 执行失败，跳过保存")
        return
    save_note_to_file(task_id, note)
    _append_note_result_for_task(task_id, note, str(web_url), "web_link")


def run_uploaded_document_note_task(
    task_id: str,
    file_url: str,
    file_name: str,
    content_type: Optional[str] = None,
    model_name: str = None,
    provider_id: str = None,
    _format: list = None,
    style: str = None,
    extras: str = None,
    output_type: str = "note_markdown",
):
    if not model_name or not provider_id:
        raise HTTPException(status_code=400, detail="请选择模型和提供者")

    logger.info(f"上传文档任务进入执行队列 (task_id={task_id})")
    ingestion_result = IngestionPipeline().run_document(
        IngestionRequest(
            job_id=task_id,
            file_url=file_url,
            file_name=file_name,
            content_type=content_type,
            model_name=model_name,
            provider_id=provider_id,
            user_options={
                "format": _format or [],
                "style": style,
                "extras": extras,
                "output_type": output_type,
            },
        )
    )
    document_context: DocumentContext = ingestion_result.to_document_context()
    payload = {
        "title": ingestion_result.parsed_document.title,
        "content": ingestion_result.parsed_document.text,
        "file_kind": "document",
        "parsed_document_path": ingestion_result.sidecar_path,
    }
    transcript = _build_document_transcript(payload["content"])
    generator = NoteGenerator()
    gpt = generator._get_gpt(model_name, provider_id)
    audio_meta = AudioDownloadResult(
        file_path=str(resolve_uploaded_file_path(file_url)),
        title=payload["title"],
        duration=0,
        cover_url=None,
        platform="uploaded_document",
        video_id=task_id,
        raw_info={
            "file_name": file_name,
            "source_url": file_url,
            "content_type": content_type or "",
            "parsed_document_path": ingestion_result.sidecar_path,
            "document_context": {
                "parser_name": document_context.parser_name,
                "page_count": document_context.page_count,
                "quality": document_context.quality,
            },
        },
    )
    markdown_cache_file = Path(NOTE_OUTPUT_DIR) / f"{task_id}_markdown.md"
    markdown = generator._summarize_text(
        task_id=task_id,
        audio_meta=audio_meta,
        transcript=transcript,
        gpt=gpt,
        provider_id=provider_id,
        markdown_cache_file=markdown_cache_file,
        platform="uploaded_document",
        link=False,
        screenshot=False,
        formats=_format or [],
        style=style,
        extras=extras,
        video_understanding=False,
        vision_mode=None,
        max_sampling_points=None,
        enable_refine_engine=False,
        video_img_urls=[],
        output_type=output_type,
    )
    if not markdown:
        emit_note_failed(task_id, "文档笔记生成失败，请重试")
        return
    note = NoteResult(markdown=markdown, transcript=transcript, audio_meta=audio_meta)
    save_note_to_file(task_id, note)
    try:
        IngestionMaterializationService().materialize(ingestion_result)
    except Exception as e:
        logger.warning(f"文档知识物化失败（不影响笔记）: {e}")
    generator._schedule_summary_sidecars(
        task_id=task_id,
        video_url=str(file_url),
        platform="uploaded_document",
        audio_meta=audio_meta,
        transcript=transcript,
        markdown=markdown,
        user_options=generator._build_summary_sidecar_options(
            output_type=output_type,
            style=style,
            formats=_format or [],
            extras=extras,
            video_understanding=False,
            vision_mode=None,
            max_sampling_points=None,
            enable_refine_engine=False,
            video_img_urls=[],
            model_name=model_name,
            provider_id=provider_id,
        ),
        gpt=gpt,
    )
    _append_note_result_for_task(task_id, note, str(file_url), "uploaded_document")


@router.post('/delete_task')
def delete_task(data: RecordRequest):
    try:
        result = delete_note_task_artifacts(data.task_id) if data.task_id else {}
        if data.task_id:
            cancel_note_task(data.task_id, "任务已删除，任务已取消")
        NoteGenerator().delete_note(video_id=data.video_id, platform=data.platform)
        return R.success(result, msg='删除成功')
    except Exception as e:
        return R.error(msg=e)


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = _sanitize_upload_name(file.filename)
    content = await file.read()
    content_type = file.content_type or ""
    _validate_upload_payload(safe_name, content_type, content)
    suffix = Path(safe_name).suffix.lower()
    upload_id = uuid.uuid4().hex
    stored_name = f"{upload_id}{suffix}"
    file_location = Path(UPLOAD_DIR) / stored_name
    with open(file_location, "wb+") as f:
        f.write(content)

    return R.success({
        "url": f"/api/note/uploads/{upload_id}",
        "upload_id": upload_id,
        "file_name": safe_name,
        "stored_name": stored_name,
        "content_type": content_type,
        "file_kind": detect_uploaded_file_kind(safe_name, content_type),
    })


@router.get("/uploads/{upload_id}")
def read_uploaded_file(upload_id: str):
    path = _resolve_upload_path_by_id(upload_id)
    media_type, _ = mimetypes.guess_type(path.name)
    headers = {"X-Content-Type-Options": "nosniff"}
    if not (media_type or "").startswith("image/"):
        headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
    return FileResponse(path, media_type=media_type or "application/octet-stream", headers=headers)


@router.post("/uploaded_files/ingest")
def ingest_uploaded_file(data: UploadedFileIngestRequest, background_tasks: BackgroundTasks):
    try:
        kind = detect_uploaded_file_kind(data.file_name, data.content_type)
        source_type = "uploaded_file"

        if data.mode == "chat":
            payload = extract_uploaded_file_content(
                file_url=data.file_url,
                file_name=data.file_name,
                content_type=data.content_type,
            )
            result = ConversationImportService().import_markdown(
                ConversationImportRequest(
                    import_mode="chat_asset",
                    conversation_id=data.conversation_id,
                    title=payload["title"],
                    content=payload["content"],
                    format="markdown",
                    file_name=data.file_name,
                    source_url=data.file_url,
                    source_type=source_type,
                    metadata={"content_type": data.content_type or "", "file_kind": kind},
                )
            )
            return R.success({"action": "chat_asset", "asset_content": payload["content"], "file_kind": kind, **result.model_dump()})

        if data.mode != "note":
            return R.error("unsupported mode", code=400)

        if kind == "markdown":
            payload = extract_uploaded_file_content(
                file_url=data.file_url,
                file_name=data.file_name,
                content_type=data.content_type,
            )
            result = ConversationImportService().import_markdown(
                ConversationImportRequest(
                    import_mode="note",
                    conversation_id=data.conversation_id,
                    title=payload["title"],
                    content=payload["content"],
                    format="markdown",
                    file_name=data.file_name,
                    source_url=data.file_url,
                    source_type=source_type,
                    metadata={"content_type": data.content_type or "", "file_kind": kind},
                )
            )
            return R.success({"action": "imported_note", "file_kind": kind, **result.model_dump()})

        if kind in {"audio", "video"}:
            return R.error("media files should use generate_note with local platform", code=400)

        if not data.model_name or not data.provider_id:
            return R.error("请选择模型和提供者", code=400)

        conversation_id = data.conversation_id or f"conv_{uuid.uuid4().hex}"
        task_id = str(uuid.uuid4())
        upsert_conversation(
            {
                "id": conversation_id,
                "mode": "note",
                "title": Path(data.file_name).stem or "未命名文档",
                "status": TaskStatus.PENDING.value,
                "noteState": "generating",
                "platform": "uploaded_document",
                "linkedNoteTaskId": task_id,
                "formData": {
                    "video_url": data.file_url,
                    "platform": "uploaded_document",
                    "quality": "medium",
                    "model_name": data.model_name,
                    "provider_id": data.provider_id,
                    "style": data.style,
                    "extras": data.extras,
                },
            }
        )
        register_task_conversation(task_id, conversation_id, source_url=data.file_url, extras=data.extras)
        emit_note_progress(task_id, TaskStatus.PENDING, "文档已上传，等待后台生成笔记")
        background_tasks.add_task(
            run_uploaded_document_note_task,
            task_id,
            data.file_url,
            data.file_name,
            data.content_type,
            data.model_name,
            data.provider_id,
            data.format,
            data.style,
            data.extras,
        )
        return R.success(
            {
                "action": "note_task",
                "conversation_id": conversation_id,
                "task_id": task_id,
                "file_kind": kind,
                "message": "文档笔记任务已提交",
            }
        )
    except ValueError as exc:
        return R.error(str(exc), code=400)


@router.post("/generate_note")
def generate_note(data: VideoRequest, background_tasks: BackgroundTasks):
    try:
        if not data.model_name or not data.provider_id:
            raise HTTPException(status_code=400, detail="请选择模型和提供者")

        resolved_video_url, resolved_extras = _resolve_note_request_input(data)
        conversation_id = data.conversation_id or data.task_id
        effective_platform = "web_link" if data.force_web_fallback else data.platform
        is_web_link = effective_platform == "web_link"
        video_id = None if is_web_link else extract_video_id(resolved_video_url, effective_platform)
        # if not video_id:
        #     raise HTTPException(status_code=400, detail="无法提取视频 ID")
        # existing = get_task_by_video(video_id, data.platform)
        # if existing:
        #     return R.error(
        #         msg='笔记已生成，请勿重复发起',
        #
        #     )
        if data.task_id:
            # 如果传了task_id，说明是重试！
            task_id = data.task_id
            logger.info(f"重试模式，复用已有 task_id={task_id}")
        else:
            # 正常新建任务
            task_id = str(uuid.uuid4())

        register_task_conversation(
            task_id,
            conversation_id,
            source_url=resolved_video_url,
            extras=resolved_extras,
            attempt_id=data.retry_attempt_id,
        )

        if conversation_id:
            upsert_conversation(
                {
                    "id": conversation_id,
                    "mode": "note",
                    "status": TaskStatus.PENDING.value,
                    "noteState": "generating",
                    "platform": effective_platform,
                    "linkedNoteTaskId": task_id,
                    "formData": {**data.model_dump(), "task_id": task_id, "conversation_id": conversation_id},
                }
            )

        # 统一先写入 PENDING，表示已进入队列等待串行执行
        emit_note_progress(task_id, TaskStatus.PENDING, "任务已提交，等待后台生成")

        # 客户端已经抓好字幕的话，写到转写缓存文件，NoteGenerator 的 cache-hit 逻辑会直接用上
        if data.prefetched_transcript:
            try:
                _persist_prefetched_transcript(task_id, data.prefetched_transcript)
            except Exception as e:
                logger.warning(f"写入预取字幕失败 (task_id={task_id}): {e}")

        if is_web_link:
            background_tasks.add_task(
                run_web_note_task,
                task_id,
                resolved_video_url,
                data.model_name,
                data.provider_id,
                data.format,
                data.style,
                resolved_extras,
                data.output_type,
            )
        else:
            background_tasks.add_task(run_note_task, task_id, resolved_video_url, effective_platform, data.quality, data.link,
                                      data.screenshot, data.model_name, data.provider_id, data.format, data.style,
                                      resolved_extras, data.video_understanding, data.video_interval, data.grid_size,
                                      data.vision_mode, data.max_sampling_points, data.enable_refine_engine,
                                      data.output_type)
        return R.success({
            "task_id": task_id,
            "message": "任务已进入后台队列；如果需要本地转写模型，系统会在后台准备并通过任务状态提示进度。",
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("提交生成笔记任务失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task_status/{task_id}")
def get_task_status(task_id: str):
    status_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.status.json")
    result_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json")
    wiki_status = _wiki_status_for_task(task_id)
    task_input = get_registered_task_input(task_id)
    timing_fields = {
        "stage_timings": {},
        "collector_timings": {},
        "stage_started_at": "",
        "updated_at": "",
    }

    def status_payload(extra: dict | None = None) -> dict:
        payload = {
            "task_id": task_id,
            "wiki_status": wiki_status,
            "attempt_id": task_input.get("attempt_id", ""),
            "attempt": task_input.get("attempt", 0),
            "source_url": task_input.get("source_url", ""),
            "extras": task_input.get("extras", ""),
        }
        payload.update(extra or {})
        return payload

    # 优先读状态文件
    if os.path.exists(status_path):
        with open(status_path, "r", encoding="utf-8") as f:
            status_content = _with_live_stage_elapsed(json.load(f))

        status = status_content.get("status")
        message = status_content.get("message", "")
        timing_fields = {
            "stage_timings": status_content.get("stage_timings", {}),
            "collector_timings": build_collector_timings(status_content),
            "stage_started_at": status_content.get("stage_started_at", ""),
            "updated_at": status_content.get("updated_at", ""),
        }

        if status == TaskStatus.SUCCESS.value:
            # 成功状态的话，继续读取最终笔记内容
            if os.path.exists(result_path):
                with open(result_path, "r", encoding="utf-8") as rf:
                    result_content = json.load(rf)
                return R.success(status_payload({
                    "status": status,
                    "result": result_content,
                    "message": message,
                    **timing_fields,
                }))
            else:
                # 理论上不会出现，保险处理
                return R.success(status_payload({
                    "status": TaskStatus.PENDING.value,
                    "message": "任务完成，但结果文件未找到",
                    **timing_fields,
                }))

        if status == TaskStatus.FAILED.value:
            return R.success(status_payload({
                "status": status,
                "message": message or "任务失败",
                **timing_fields,
            }))

        if status == TaskStatus.CANCELED.value:
            return R.success(status_payload({
                "status": status,
                "message": message or "任务已取消",
                **timing_fields,
            }))

        # 处理中状态
        return R.success(status_payload({
            "status": status,
            "message": message,
            **timing_fields,
        }))

    # 没有状态文件，但有结果
    if os.path.exists(result_path):
        with open(result_path, "r", encoding="utf-8") as f:
            result_content = json.load(f)
        return R.success(status_payload({
            "status": TaskStatus.SUCCESS.value,
            "result": result_content,
            **timing_fields,
        }))

    if not task_input:
        return R.success(status_payload({
            "status": "NOT_FOUND",
            "message": "任务不存在或已被删除",
            **timing_fields,
        }))

    # 已注册但尚未写入状态文件，视为排队中
    return R.success(status_payload({
        "status": TaskStatus.PENDING.value,
        "message": "任务排队中",
        **timing_fields,
    }))


@router.post("/wiki/retry/{task_id}")
def retry_wiki_extraction(task_id: str, background_tasks: BackgroundTasks):
    from app.services.note_document_store import update_note_document_wiki_status
    from app.services.wiki_job_store import WikiJobStore

    update_note_document_wiki_status(task_id, "pending")
    WikiJobStore(output_dir=Path(NOTE_OUTPUT_DIR)).write(task_id, "pending", stage="analysis")

    def _retry():
        from app.models.summary_input import SummaryInput
        from app.services.wiki_job_store import WikiJobStore
        from app.services.wiki_pipeline import WikiPipeline
        
        output_dir = Path(NOTE_OUTPUT_DIR)
        summary_input_path = output_dir / f"{task_id}_summary_input.json"
        result_path = output_dir / f"{task_id}.json"
        
        if not summary_input_path.exists() or not result_path.exists():
            return
            
        try:
            summary_input_data = json.loads(summary_input_path.read_text(encoding="utf-8"))
            result_data = json.loads(result_path.read_text(encoding="utf-8"))
            markdown = result_data.get("markdown", "")
            
            summary_input = SummaryInput(**summary_input_data)
            
            user_options = summary_input.user_options
            model_name = user_options.get("model_name")
            provider_id = user_options.get("provider_id")
            
            from app.gpt.notemeld_gpt import NotemeldGPT
            from app.services.model import ModelService
            from app.services.provider import ProviderService

            provider = ProviderService.get_provider_by_id(provider_id)
            if not provider:
                raise ValueError("Provider not found")

            config = ModelService.build_saved_model_config(provider, model_name)
            # T11: 走 notemeld-ai 适配器（NotemeldGPT），回滚时换回 GPTFactory().from_config(config)
            gpt = NotemeldGPT.from_config(config)
            if hasattr(gpt, "set_usage_context"):
                gpt.set_usage_context(
                    {
                        "task_id": task_id,
                        "provider_id": provider_id,
                        "provider_name": provider["name"],
                        "phase": "analysis",
                        "platform": summary_input.platform or summary_input.input_type,
                        "video_id": task_id,
                        "video_title": summary_input.title,
                        "request_meta": {
                            "source_type": summary_input.input_type,
                            "retry": True,
                        },
                    }
                )
            job_store = WikiJobStore(output_dir=output_dir)
            pipeline = WikiPipeline(output_dir=output_dir)
            job_store.write(task_id, "running", stage="analysis", detail="正在重试 Wiki 知识提取", recoverable=True)
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
            from app.services.wiki_rebuild_service import request_wiki_rebuild

            request_wiki_rebuild(output_dir, gpt=gpt, reason=f"task:{task_id}:retry_analysis_complete")
        except Exception as e:
            logger.error(f"Wiki extraction retry failed for {task_id}: {e}")
            if WikiJobStore(output_dir=output_dir).read(task_id).get("status") == "canceled":
                update_note_document_wiki_status(task_id, "canceled")
                return
            WikiJobStore(output_dir=output_dir).write(
                task_id,
                "failed",
                stage=getattr(e, "stage", "analysis"),
                error=str(e),
                reason="analysis_error",
                detail=str(e),
                recoverable=True,
            )
            update_note_document_wiki_status(task_id, "failed")

    background_tasks.add_task(_retry)
    return R.success({"message": "已触发 Wiki 重试任务"})


@router.get("/wiki/status/{task_id}")
def get_wiki_status(task_id: str):
    from app.services.wiki_job_store import WikiJobStore

    payload = WikiJobStore(output_dir=Path(NOTE_OUTPUT_DIR)).read(task_id)
    return R.success(payload)


@router.post("/wiki/cancel/{task_id}")
def cancel_wiki_extraction(task_id: str):
    from app.services.note_document_store import update_note_document_wiki_status
    from app.services.wiki_job_store import WikiJobStore

    payload = WikiJobStore(output_dir=Path(NOTE_OUTPUT_DIR)).cancel(task_id)
    update_note_document_wiki_status(task_id, "canceled")
    return R.success(payload, msg="已取消 Wiki 提取")

@router.get("/image_proxy")
async def image_proxy(request: Request, url: str):
    parsed = urlparse((url or "").strip())
    hostname = (parsed.hostname or "").strip().lower()
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise HTTPException(status_code=400, detail="无效的图片地址")
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="不允许代理该地址")
    if _is_public_ip(hostname):
        raise HTTPException(status_code=403, detail="不允许使用 IP 字面量地址")
    if hostname not in IMAGE_PROXY_ALLOWED_HOSTS:
        raise HTTPException(status_code=403, detail="图片地址不在白名单中")

    headers = {
        "Referer": _resolve_image_proxy_referer(hostname),
        "User-Agent": request.headers.get("User-Agent", ""),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            resp = await client.get(url, headers=headers)

            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail="图片获取失败")

            content_type = resp.headers.get("Content-Type", "image/jpeg")
            if not content_type.lower().startswith("image/"):
                raise HTTPException(status_code=415, detail="代理结果不是图片")

            content_length = int(resp.headers.get("Content-Length", "0") or "0")
            if content_length and content_length > 5 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="代理图片过大")

            return Response(
                content=resp.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Content-Type": content_type,
                    "X-Content-Type-Options": "nosniff",
                },
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="图片代理失败")
