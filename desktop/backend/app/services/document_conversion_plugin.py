from __future__ import annotations

import json
import hashlib
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from app.services.file_ingest_service import resolve_uploaded_file_path
from app.utils.storage_paths import plugin_active_pointer, plugins_root_dir


SCHEMA_VERSION = "conversion-artifact.v1"
DEFAULT_TIMEOUT_SECONDS = 120


class DocumentConversionError(ValueError):
    def __init__(self, code: str, message: str, *, recoverable: bool = True):
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable


def _plugin_root() -> Path:
    configured = str(os.environ.get("NOTEMELD_PLUGINS_DIR") or "").strip()
    if configured:
        configured_root = Path(configured).expanduser().resolve()
        if (configured_root / "plugins").is_dir():
            return configured_root / "plugins" / "official-document-to-markdown"
        if configured_root.name == "plugins":
            return configured_root / "official-document-to-markdown"
    workspace_root = Path(__file__).resolve().parents[4].parent
    sibling = workspace_root / "notemeld-plugins" / "plugins" / "official-document-to-markdown"
    packaged_workspace = workspace_root / "packages" / "notemeld-plugins" / "plugins" / "official-document-to-markdown"
    return packaged_workspace if packaged_workspace.is_dir() else sibling


def _binary_path() -> Path | None:
    configured = str(os.environ.get("NOTEMELD_DOCUMENT_TO_MARKDOWN_BIN") or "").strip()
    candidates = [Path(configured)] if configured else []
    pointer = plugin_active_pointer("official.document-to-markdown")
    if pointer.is_file():
        version = pointer.read_text(encoding="utf-8").strip()
        if version and "/" not in version and "\\" not in version:
            candidates.append(
                plugins_root_dir() / "versions" / "official.document-to-markdown" / version / "bin" / "notemeld-document-to-markdown"
            )
    root = _plugin_root()
    candidates.extend(
        [
            root / "target" / "release" / "notemeld-document-to-markdown",
            root / "target" / "debug" / "notemeld-document-to-markdown",
        ]
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    return None


def _error_envelope(request_id: str, code: str, message: str, recoverable: bool, input_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "status": "failed",
        "diagnostic": {"code": code, "message": message, "recoverable": recoverable},
        "provenance": {
            "tool_id": "document.to_markdown",
            "tool_version": "host",
            "plugin_id": "official.document-to-markdown",
            "plugin_version": "unknown",
            "input_sha256": input_sha256,
        },
    }


def convert_document_to_markdown(
    *,
    file_url: str,
    file_name: str,
    source: dict[str, Any] | None = None,
    request_id: str | None = None,
    turn_id: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run the portable Rust document converter through its JSONL boundary.

    The Host resolves the uploaded file and owns the process boundary. The plugin
    never receives NoteMeld database access and only returns a conversion artifact.
    """
    request_id = str(request_id or uuid.uuid4())
    try:
        input_path = resolve_uploaded_file_path(file_url)
    except (TypeError, ValueError) as exc:
        raise DocumentConversionError("invalid_arguments", "uploaded file could not be resolved", recoverable=False) from exc

    binary = _binary_path()
    input_sha256 = hashlib.sha256(input_path.read_bytes()).hexdigest()
    if binary is None:
        return _error_envelope(
            request_id,
            "plugin_unavailable",
            "document conversion plugin is not installed or built",
            True,
            input_sha256,
        )

    request = {
        "operation": "document.to_markdown",
        "request_id": request_id,
        "input_path": str(input_path),
        "input_name": str(file_name or input_path.name),
        "source": source,
        "turn_id": turn_id,
    }
    try:
        completed = subprocess.run(
            [str(binary)],
            input=json.dumps(request, ensure_ascii=False) + "\n",
            text=True,
            capture_output=True,
            timeout=max(1, min(int(timeout_seconds), 600)),
            cwd=str(binary.parent.parent.parent),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _error_envelope(request_id, "tool_timeout", "document conversion timed out", True, input_sha256)
    except OSError as exc:
        return _error_envelope(request_id, "tool_execution_error", "document conversion could not be started", True, input_sha256)

    if completed.returncode != 0:
        return _error_envelope(request_id, "tool_execution_error", "document conversion failed", True, input_sha256)
    output = next((line.strip() for line in completed.stdout.splitlines() if line.strip()), "")
    try:
        result = json.loads(output)
    except json.JSONDecodeError:
        return _error_envelope(request_id, "invalid_tool_output", "document conversion returned invalid output", True, input_sha256)
    if not isinstance(result, dict) or result.get("schema_version") != SCHEMA_VERSION:
        return _error_envelope(request_id, "invalid_tool_output", "document conversion returned an unknown artifact", True, input_sha256)
    return result


__all__ = ["DocumentConversionError", "convert_document_to_markdown"]
