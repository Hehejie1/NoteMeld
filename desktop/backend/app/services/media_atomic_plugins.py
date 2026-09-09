from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, is_dataclass
from typing import Any

from app.services.constant import SUPPORT_PLATFORM_MAP
from app.services.file_ingest_service import resolve_uploaded_file_path
from app.services.transcriber_config_manager import TranscriberConfigManager
from app.services.video_frame_collector import VideoFrameCollector
from app.transcriber.transcriber_provider import get_transcriber


SCHEMA_VERSION = "conversion-artifact.v1"
PLUGIN_VERSIONS = {
    "video.fetch": ("official.video-fetch", "0.1.0"),
    "audio.extract": ("official.audio-extract", "0.1.0"),
    "audio.transcribe": ("official.audio-transcribe", "0.1.0"),
    "video.frames": ("official.video-frames", "0.1.0"),
}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _provenance(tool_id: str, request_id: str, source: dict[str, Any] | None, turn_id: str | None) -> dict[str, Any]:
    plugin_id, plugin_version = PLUGIN_VERSIONS[tool_id]
    return {
        "tool_id": tool_id,
        "tool_version": "host",
        "plugin_id": plugin_id,
        "plugin_version": plugin_version,
        "input_sha256": _digest(str(source or {})),
        "source": source,
        "turn_id": turn_id,
    }


def _failure(tool_id: str, request_id: str, code: str, message: str, source: dict[str, Any] | None, turn_id: str | None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "status": "failed",
        "diagnostic": {"code": code, "message": message, "recoverable": True},
        "provenance": _provenance(tool_id, request_id, source, turn_id),
    }


def _downloader(platform: str, source_url: str):
    normalized = str(platform or "").strip().lower()
    if not normalized:
        normalized = "local" if source_url.startswith(("/uploads/", "/api/note/uploads/")) else "youtube"
    downloader = SUPPORT_PLATFORM_MAP.get(normalized)
    if downloader is None:
        raise ValueError("unsupported media platform")
    return normalized, downloader


def _effective_source_url(source_url: str) -> str:
    if source_url.startswith("/api/note/uploads/"):
        return str(resolve_uploaded_file_path(source_url))
    return source_url


def fetch_video_media(
    *,
    source_url: str,
    platform: str = "",
    include_video: bool = False,
    request_id: str | None = None,
    source: dict[str, Any] | None = None,
    turn_id: str | None = None,
) -> dict[str, Any]:
    request_id = str(request_id or uuid.uuid4())
    try:
        effective_source = _effective_source_url(source_url)
        normalized, downloader = _downloader(platform, effective_source)
        audio = downloader.download(effective_source, need_video=include_video)
        video_path = None
        if include_video:
            video_path = downloader.download_video(effective_source)
        raw = asdict(audio) if is_dataclass(audio) else dict(audio)
        metadata = {
            "title": raw.get("title") or "",
            "duration": raw.get("duration") or 0,
            "platform": normalized,
            "video_id": raw.get("video_id") or "",
            "has_audio": bool(raw.get("file_path")),
            "has_video": bool(video_path or raw.get("video_path")),
            "cover_url": raw.get("cover_url"),
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": request_id,
            "status": "completed",
            "artifact": {"kind": "media", "media_type": "video" if include_video else "audio", "format": "media", "sha256": _digest(str(metadata)), "content": "", "metadata": metadata},
            "provenance": _provenance("video.fetch", request_id, source or {"url": source_url, "platform": normalized}, turn_id),
        }
    except Exception:
        return _failure("video.fetch", request_id, "media_fetch_failed", "media could not be fetched", source, turn_id)


def extract_audio(
    *,
    source_url: str,
    platform: str = "",
    request_id: str | None = None,
    source: dict[str, Any] | None = None,
    turn_id: str | None = None,
) -> dict[str, Any]:
    request_id = str(request_id or uuid.uuid4())
    try:
        effective_source = _effective_source_url(source_url)
        normalized, downloader = _downloader(platform, effective_source)
        audio = downloader.download(effective_source, need_video=False)
        raw = asdict(audio) if is_dataclass(audio) else dict(audio)
        metadata = {"title": raw.get("title") or "", "duration": raw.get("duration") or 0, "platform": normalized, "video_id": raw.get("video_id") or "", "media_type": "audio"}
        return {
            "schema_version": SCHEMA_VERSION, "request_id": request_id, "status": "completed",
            "artifact": {"kind": "audio", "media_type": "audio/mpeg", "format": "audio", "sha256": _digest(str(metadata)), "content": "", "metadata": metadata},
            "provenance": _provenance("audio.extract", request_id, source or {"url": source_url, "platform": normalized}, turn_id),
        }
    except Exception:
        return _failure("audio.extract", request_id, "audio_extract_failed", "audio could not be extracted", source, turn_id)


def transcribe_audio(
    *,
    source_url: str,
    platform: str = "",
    request_id: str | None = None,
    source: dict[str, Any] | None = None,
    turn_id: str | None = None,
) -> dict[str, Any]:
    request_id = str(request_id or uuid.uuid4())
    try:
        effective_source = _effective_source_url(source_url)
        normalized, downloader = _downloader(platform, effective_source)
        subtitle = downloader.download_subtitles(effective_source) if normalized != "local" else None
        if subtitle is not None:
            transcript = subtitle
            mode = "subtitle"
        else:
            audio = downloader.download(effective_source, need_video=False)
            config = TranscriberConfigManager().get_config()
            transcriber = get_transcriber(
                transcriber_type=config["transcriber_type"],
                model_size=config.get("model_size", "base"),
                device="cpu",
            )
            transcript = transcriber.transcript(file_path=audio.file_path)
            mode = "audio"
        raw = asdict(transcript) if is_dataclass(transcript) else dict(transcript)
        segments = raw.get("segments") or []
        return {
            "schema_version": SCHEMA_VERSION, "request_id": request_id,
            "status": "completed" if raw.get("full_text") else "needs_attention",
            "artifact": {"kind": "transcript", "media_type": "application/json", "format": "transcript", "sha256": _digest(str(raw)), "content": raw.get("full_text") or "", "metadata": {"language": raw.get("language"), "segments": segments, "mode": mode}},
            "provenance": _provenance("audio.transcribe", request_id, source or {"url": source_url, "platform": normalized}, turn_id),
        }
    except Exception:
        return _failure("audio.transcribe", request_id, "transcription_failed", "audio transcription failed", source, turn_id)


def extract_video_frames(
    *,
    source_url: str,
    platform: str = "",
    timestamps: list[float] | None = None,
    request_id: str | None = None,
    source: dict[str, Any] | None = None,
    turn_id: str | None = None,
) -> dict[str, Any]:
    request_id = str(request_id or uuid.uuid4())
    try:
        effective_source = _effective_source_url(source_url)
        normalized, downloader = _downloader(platform, effective_source)
        collected = VideoFrameCollector().collect(
            task_id=request_id,
            screenshot=True,
            video_url=effective_source,
            downloader=downloader,
            frame_timestamps=timestamps,
            allow_vision=False,
        )
        raw = asdict(collected) if is_dataclass(collected) else dict(collected)
        frames = []
        for frame in raw.get("frames") or []:
            frames.append({key: value for key, value in frame.items() if key not in {"image_path", "path"}})
        return {
            "schema_version": SCHEMA_VERSION, "request_id": request_id,
            "status": "completed" if frames else "needs_attention",
            "artifact": {"kind": "video_frames", "media_type": "application/json", "format": "frames", "sha256": _digest(str(frames)), "content": raw.get("content") or "", "metadata": {"platform": normalized, "frames": frames, "frame_count": len(frames), "mode": raw.get("mode") or "ocr"}},
            "provenance": _provenance("video.frames", request_id, source or {"url": source_url, "platform": normalized}, turn_id),
        }
    except Exception:
        return _failure("video.frames", request_id, "frame_extraction_failed", "video frames could not be extracted", source, turn_id)


__all__ = ["extract_audio", "extract_video_frames", "fetch_video_media", "transcribe_audio"]
