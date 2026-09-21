"""Build a safe local-to-cloud session import snapshot."""
from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
from pathlib import Path
from typing import Any, Iterable


class SnapshotError(ValueError):
    """Raised when a local snapshot cannot be built safely."""


_EXCLUDED_NAMES = {".git", ".ssh", ".aws", ".azure", ".gnupg", "skills", "plugins", "applications", "app-packages"}
_EXCLUDED_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def _excluded(path: Path) -> bool:
    for part in path.parts:
        lowered = part.lower()
        if lowered in _EXCLUDED_NAMES or lowered.startswith(".env"):
            return True
        if lowered.startswith(("credentials", "secrets", "cookies")) or lowered.endswith(_EXCLUDED_SUFFIXES):
            return True
    return False


def _iter_files(root: Path) -> Iterable[tuple[Path, str]]:
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if not _excluded(Path(name)) and not (current_path / name).is_symlink()]
        for name in files:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.is_file() or _excluded(Path(relative)):
                continue
            yield path, relative


def build_import_snapshot(*, request_id: str, source_session_id: str, source_device_id: str,
                          workspace_root: str | Path, title: str = "Imported session",
                          conversation: dict[str, Any] | None = None, events: list[dict[str, Any]] | None = None,
                          compression: dict[str, Any] | list[Any] | None = None, memory: dict[str, Any] | list[Any] | None = None,
                          model_descriptor: dict[str, Any] | None = None, mcp_config: dict[str, Any] | list[Any] | None = None,
                          tool_records: list[dict[str, Any]] | None = None, approval_records: list[dict[str, Any]] | None = None,
                          task_state: dict[str, Any] | None = None, provenance: dict[str, Any] | None = None,
                          max_bytes: int = 256 * 1024 * 1024, max_files: int = 10_000) -> dict[str, Any]:
    """Return a SessionImport-compatible dictionary with safe workspace files."""
    root = Path(workspace_root).expanduser()
    if not root.exists() or not root.is_dir() or root.is_symlink():
        raise SnapshotError("workspace root must be an existing non-symlink directory")
    if max_bytes < 0 or max_files < 0:
        raise SnapshotError("snapshot limits must be non-negative")
    candidates = sorted(_iter_files(root), key=lambda item: item[1])
    if len(candidates) > max_files:
        raise SnapshotError("workspace file limit exceeded")
    files: list[dict[str, Any]] = []
    total = 0
    for path, relative in candidates:
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise SnapshotError(f"unable to read workspace file: {relative}") from exc
        total += len(content)
        if total > max_bytes:
            raise SnapshotError("workspace byte limit exceeded")
        mime_type = mimetypes.guess_type(relative)[0] or ({".md": "text/markdown", ".json": "application/json"}.get(path.suffix.lower()) or "application/octet-stream")
        files.append({"path": relative, "content_base64": base64.b64encode(content).decode("ascii"),
                      "sha256": hashlib.sha256(content).hexdigest(), "size": len(content),
                      "mime_type": mime_type})
    return {"request_id": request_id, "source_session_id": source_session_id, "source_device_id": source_device_id,
            "title": title, "conversation": conversation or {}, "events": events or [], "compression": compression,
            "memory": memory, "model_descriptor": model_descriptor or {}, "mcp_config": mcp_config or {},
            "tool_records": tool_records or [], "approval_records": approval_records or [], "task_state": task_state or {},
            "provenance": provenance or {}, "files": files}
