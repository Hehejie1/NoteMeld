from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from app.services.file_ingest_service import resolve_uploaded_file_path
from app.services.ocr.provider import get_ocr_provider


SCHEMA_VERSION = "conversion-artifact.v1"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_image_ocr(
    *,
    file_url: str,
    file_name: str,
    source: dict[str, Any] | None = None,
    request_id: str | None = None,
    turn_id: str | None = None,
) -> dict[str, Any]:
    request_id = str(request_id or uuid.uuid4())
    input_sha256 = _digest(file_url)
    try:
        path = resolve_uploaded_file_path(file_url)
        input_sha256 = _file_digest(path)
        result = get_ocr_provider().extract_text(path)
    except (TypeError, ValueError) as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": request_id,
            "status": "failed",
            "diagnostic": {"code": "ocr_unavailable", "message": str(exc), "recoverable": True},
            "provenance": {
                "tool_id": "image.ocr", "tool_version": "host",
                "plugin_id": "official.image-ocr", "plugin_version": "0.1.0",
                "input_sha256": "", "source": source, "turn_id": turn_id,
            },
        }
    except Exception:
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": request_id,
            "status": "failed",
            "diagnostic": {"code": "ocr_failed", "message": "image OCR failed", "recoverable": True},
            "provenance": {
                "tool_id": "image.ocr", "tool_version": "host",
                "plugin_id": "official.image-ocr", "plugin_version": "0.1.0",
                "input_sha256": "", "source": source, "turn_id": turn_id,
            },
        }

    text = str(result.get("text") or "").strip()
    lines = list(result.get("lines") or [])
    pages = list(result.get("pages") or [])
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "status": "completed" if text else "needs_attention",
        "artifact": {
            "kind": "ocr",
            "media_type": "application/json",
            "format": Path(file_name or "image").suffix.lower().lstrip(".") or "image",
            "sha256": _digest(payload),
            "content": text,
            "metadata": {
                "title": Path(file_name or "未命名图片").stem or "未命名图片",
                "engine": result.get("engine") or "unknown",
                "confidence": result.get("confidence"),
                "pages": pages,
                "lines": lines,
                "positioning": "bbox",
            },
        },
        "provenance": {
            "tool_id": "image.ocr", "tool_version": "host",
            "plugin_id": "official.image-ocr", "plugin_version": "0.1.0",
            "input_sha256": input_sha256, "source": source, "turn_id": turn_id,
        },
    }


__all__ = ["extract_image_ocr"]
