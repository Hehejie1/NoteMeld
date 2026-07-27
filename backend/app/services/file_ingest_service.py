from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path
from typing import Optional

from app.downloaders.local_downloader import LocalDownloader
from app.services.ocr.provider import get_ocr_provider
from app.utils.storage_paths import upload_dir


MARKDOWN_EXTENSIONS = {"md", "markdown"}
AUDIO_EXTENSIONS = {"mp3", "m4a", "wav", "aac", "ogg", "flac", "opus"}
VIDEO_EXTENSIONS = {"mp4", "mov", "m4v", "avi", "mkv", "webm"}
DOCUMENT_EXTENSIONS = {"txt", "pdf", "doc", "docx", "ppt", "pptx", "rtf"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def _extension_of(file_name: str) -> str:
    return Path(file_name or "").suffix.lower().lstrip(".")


def detect_uploaded_file_kind(file_name: str, content_type: Optional[str] = None) -> str:
    ext = _extension_of(file_name)
    normalized_type = str(content_type or "").lower()

    if ext in MARKDOWN_EXTENSIONS or "markdown" in normalized_type:
        return "markdown"
    if normalized_type.startswith("audio/") or ext in AUDIO_EXTENSIONS:
        return "audio"
    if normalized_type.startswith("video/") or ext in VIDEO_EXTENSIONS:
        return "video"
    if normalized_type.startswith("image/") or ext in IMAGE_EXTENSIONS:
        return "image"
    if (
        ext in DOCUMENT_EXTENSIONS
        or "pdf" in normalized_type
        or "word" in normalized_type
        or "officedocument" in normalized_type
        or "presentation" in normalized_type
        or normalized_type.startswith("text/")
    ):
        return "document"
    return "document"


def resolve_uploaded_file_path(file_url: str) -> Path:
    raw = str(file_url or "").strip()
    if not raw:
        raise ValueError("file_url is required")

    uploads_root = upload_dir().resolve()

    if raw.startswith("/api/note/uploads/"):
        upload_id = raw.removeprefix("/api/note/uploads/").strip()
        if not upload_id:
            raise ValueError("uploaded file not found")
        matches = sorted(uploads_root.glob(f"{upload_id}.*"))
        if len(matches) == 1:
            return matches[0].resolve()
        raise ValueError("uploaded file not found")

    if raw.startswith("/uploads/"):
        candidate = uploads_root / Path(raw.removeprefix("/uploads/")).name
        normalized = candidate.resolve()
        if normalized.exists() and uploads_root in normalized.parents:
            return normalized

    raise ValueError("uploaded file not found")


def extract_uploaded_file_content(
    file_url: str,
    file_name: str,
    content_type: Optional[str] = None,
) -> dict:
    file_kind = detect_uploaded_file_kind(file_name, content_type)
    title = Path(file_name or "").stem or "未命名文件"

    if file_kind in {"audio", "video"}:
        return {
            "title": title,
            "content": transcribe_uploaded_media(file_url),
            "file_kind": file_kind,
        }

    path = resolve_uploaded_file_path(file_url)
    if file_kind == "markdown":
        return {"title": title, "content": path.read_text(encoding="utf-8"), "file_kind": file_kind}
    if file_kind == "image":
        try:
            result = get_ocr_provider().extract_text(path)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("图片无法识别，请确认图片格式有效") from exc
        text = str(result.get("text") or "").strip()
        if not text:
            raise ValueError("未识别到可用文本")
        return {"title": title, "content": text, "file_kind": "image"}

    ext = _extension_of(file_name)
    if ext in {"txt", "rtf"}:
        return {"title": title, "content": path.read_text(encoding="utf-8", errors="ignore"), "file_kind": "document"}
    if ext == "pdf":
        return {"title": title, "content": _extract_pdf_text(path), "file_kind": "document"}
    if ext in {"doc", "docx"}:
        try:
            return {"title": title, "content": _extract_docx_text(path), "file_kind": "document"}
        except Exception:
            return {"title": title, "content": path.read_text(encoding="utf-8", errors="ignore"), "file_kind": "document"}
    if ext in {"ppt", "pptx"}:
        try:
            return {"title": title, "content": _extract_pptx_text(path), "file_kind": "document"}
        except Exception:
            return {"title": title, "content": path.read_text(encoding="utf-8", errors="ignore"), "file_kind": "document"}
    return {"title": title, "content": path.read_text(encoding="utf-8", errors="ignore"), "file_kind": "document"}


def transcribe_uploaded_media(file_url: str) -> str:
    from app.services.note import NoteGenerator

    downloader = LocalDownloader()
    audio_meta = downloader.download(file_url)
    transcript = NoteGenerator().transcriber.transcript(file_path=audio_meta.file_path)
    content = str(getattr(transcript, "full_text", "") or "").strip()
    if not content:
        raise ValueError("无法从上传媒体中提取可用文本")
    return content


def _extract_pdf_text(path: Path) -> str:
    import fitz

    chunks: list[str] = []
    with fitz.open(path) as pdf:
        for page in pdf:
            text = page.get_text("text").strip()
            if text:
                chunks.append(text)
    return "\n\n".join(chunks).strip()


def _extract_docx_text(path: Path) -> str:
    from docx import Document as DocxDocument

    document = DocxDocument(path)
    parts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n".join(parts).strip()


def _extract_pptx_text(path: Path) -> str:
    slides: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.startswith("ppt/slides/slide") or not name.endswith(".xml"):
                continue
            xml = archive.read(name).decode("utf-8", errors="ignore")
            texts = re.findall(r"<a:t>(.*?)</a:t>", xml)
            merged = "\n".join(text.strip() for text in texts if text.strip())
            if merged:
                slides.append(merged)
    return "\n\n".join(slides).strip()
