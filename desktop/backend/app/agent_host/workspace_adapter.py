"""Product workspace read adapter independent of the removed Agent loop."""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any

from app.utils.storage_paths import workspaces_root

MAX_READ_BYTES = 256 * 1024
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_.\-/]+$")


class WorkspaceAdapterError(PermissionError):
    pass


def _root(conversation_id: str) -> Path:
    if not isinstance(conversation_id, str) or not _SAFE_ID.fullmatch(conversation_id):
        raise WorkspaceAdapterError("非法 conversation_id")
    root = (workspaces_root() / conversation_id).resolve()
    base = workspaces_root()
    if not str(root).startswith(str(base) + os.sep):
        raise WorkspaceAdapterError("path traversal detected")
    return root


def _path(conversation_id: str, relative: str) -> Path:
    if not relative or relative.startswith(('/', '\\')) or not _SAFE_PATH.fullmatch(relative):
        raise WorkspaceAdapterError("非法 workspace path")
    if any(part == ".." for part in re.split(r"[\\/]+", relative)):
        raise WorkspaceAdapterError("禁止 .. 路径段")
    root = _root(conversation_id)
    target = (root / relative).resolve()
    if not str(target).startswith(str(root) + os.sep):
        raise WorkspaceAdapterError("path traversal detected")
    return target


def list_directory(conversation_id: str, relative: str = "") -> dict[str, Any]:
    target = _root(conversation_id) if not relative else _path(conversation_id, relative)
    if not target.exists():
        return {"path": relative, "entries": []}
    if not target.is_dir():
        raise WorkspaceAdapterError("不是目录")
    entries = []
    for child in sorted(target.iterdir()):
        if child.is_dir():
            entries.append({"name": child.name, "type": "directory", "size": 0})
        elif child.is_file():
            entries.append({"name": child.name, "type": "file", "size": child.stat().st_size})
    return {"path": relative, "entries": entries}


def read_file(conversation_id: str, relative: str) -> dict[str, Any]:
    target = _path(conversation_id, relative)
    if not target.exists():
        raise FileNotFoundError(relative)
    if not target.is_file():
        raise WorkspaceAdapterError("不是文件")
    raw = target.read_bytes()
    if len(raw) > MAX_READ_BYTES:
        raise WorkspaceAdapterError("文件过大")
    try:
        return {"path": relative, "content": raw.decode("utf-8"), "encoding": "utf-8"}
    except UnicodeDecodeError:
        return {"path": relative, "content": base64.b64encode(raw).decode("ascii"), "encoding": "base64"}
