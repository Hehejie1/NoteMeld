"""P3-T1: 工作空间目录管理 + 路径穿越校验 + 内建工具。

工作空间结构::

    <data_dir>/note_results/workspaces/{cid}/
        assets/      # Agent 上传/产出的资产
        skills/      # Skill 脚本与配置
        canvases/    # 画布（P4 占位）
        memory/      # 会话级临时记忆
        scratch/     # 临时草稿

设计要点：
- 路径穿越校验：所有解析后的真实路径必须以 ``workspaces/{cid}/`` 为前缀，
  否则抛 ``PermissionError``（前端接口转 403）。
- 懒创建：访问时若目录不存在自动 mkdir -p。
- ``workspace_list`` / ``workspace_read`` / ``workspace_write`` 三个 AgentTool
  仅作用于 ``cid`` 对应的工作空间，参数 ``path`` 为相对路径。
- 前端只读接口见 ``routers/conversation.py``。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from app.agent.core.signal import AbortSignal
from app.agent.core.tool import AgentTool, ToolResult
from app.utils.logger import get_logger
from app.utils.storage_paths import note_output_dir

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 路径与目录管理
# ---------------------------------------------------------------------------

#: 工作空间允许的子目录名（相对根的顶层目录）。
ALLOWED_TOP_DIRS: tuple[str, ...] = ("assets", "skills", "canvases", "memory", "scratch")

#: 单文件读取最大字节数（避免 Agent 一次读爆 context）。
MAX_READ_BYTES = 256 * 1024

#: 单文件写入最大字节数。
MAX_WRITE_BYTES = 256 * 1024

#: 允许的相对路径模式：字母/数字/下划线/短横线/点/斜杠，禁止 ``..`` 段。
_SAFE_REL_RE = re.compile(r"^[A-Za-z0-9_\-./]+$")


class WorkspaceError(PermissionError):
    """工作空间路径校验失败。"""


def workspaces_root() -> Path:
    """所有工作空间的根目录：``<note_output_dir>/workspaces``。"""
    return (note_output_dir() / "workspaces").resolve()


def workspace_root(cid: str) -> Path:
    """单个会话工作空间根目录，并进行路径穿越校验。

    Args:
        cid: 会话 id。

    Returns:
        已 resolve 的工作空间根 Path（不保证已存在）。

    Raises:
        WorkspaceError: cid 含非法字符或解析后越界。
    """
    if not cid or not isinstance(cid, str):
        raise WorkspaceError("conversation_id 不能为空")
    # cid 必须是文件系统安全字符
    if not re.match(r"^[A-Za-z0-9_\-]+$", cid):
        raise WorkspaceError(f"非法 conversation_id: {cid!r}")

    root = (workspaces_root() / cid).resolve()
    expected_prefix = str(workspaces_root())
    if not str(root).startswith(expected_prefix + os.sep) and str(root) != expected_prefix:
        raise WorkspaceError("path traversal detected")
    return root


def ensure_workspace(cid: str) -> Path:
    """确保工作空间目录及子目录存在，返回根 Path。"""
    root = workspace_root(cid)
    for sub in ALLOWED_TOP_DIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def resolve_safe_path(cid: str, rel_path: str, *, create_parents: bool = False) -> Path:
    """解析相对路径到工作空间内的绝对路径，并校验不越界。

    Args:
        cid: 会话 id。
        rel_path: 相对工作空间根的路径；必须为相对路径且不含 ``..`` 段。
        create_parents: 是否创建父目录。

    Returns:
        已 resolve 的绝对 Path。

    Raises:
        WorkspaceError: 路径越界或非法。
    """
    if rel_path is None:
        raise WorkspaceError("path 不能为空")
    rel_path = str(rel_path).strip()
    if not rel_path:
        raise WorkspaceError("path 不能为空")
    # 禁止绝对路径
    if rel_path.startswith("/") or rel_path.startswith("\\"):
        raise WorkspaceError("禁止绝对路径")
    # 禁止 Windows 盘符
    if len(rel_path) >= 2 and rel_path[1] == ":":
        raise WorkspaceError("禁止盘符路径")
    # 禁止 .. 段
    parts = re.split(r"[\\/]+", rel_path)
    if any(part == ".." for part in parts):
        raise WorkspaceError("禁止 .. 路径段")
    if not _SAFE_REL_RE.match(rel_path):
        raise WorkspaceError(f"非法 path: {rel_path!r}")

    root = workspace_root(cid)
    target = (root / rel_path).resolve()
    expected_prefix = str(root)
    if not (str(target) == expected_prefix or str(target).startswith(expected_prefix + os.sep)):
        raise WorkspaceError("path traversal detected")

    if create_parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    return target


# ---------------------------------------------------------------------------
# 列出 / 读 / 写 操作
# ---------------------------------------------------------------------------

def list_directory(cid: str, rel_path: str = "") -> dict:
    """列出工作空间内某目录。

    Returns:
        ``{"path": rel, "entries": [{"name","type","size"}]}``。
    """
    target = resolve_safe_path(cid, rel_path or ".")
    if not target.exists():
        return {"path": rel_path or "", "entries": []}
    if not target.is_dir():
        raise WorkspaceError(f"不是目录: {rel_path}")

    entries: list[dict] = []
    for child in sorted(target.iterdir()):
        try:
            if child.is_dir():
                entries.append({"name": child.name, "type": "directory", "size": 0})
            elif child.is_file():
                entries.append({
                    "name": child.name,
                    "type": "file",
                    "size": child.stat().st_size,
                })
        except OSError as exc:
            logger.warning("workspace list skip %s: %s", child, exc)
    return {"path": rel_path or "", "entries": entries}


def read_file(cid: str, rel_path: str, *, max_bytes: int = MAX_READ_BYTES) -> dict:
    """读取工作空间内某文件。"""
    target = resolve_safe_path(cid, rel_path)
    if not target.exists():
        raise FileNotFoundError(rel_path)
    if not target.is_file():
        raise WorkspaceError(f"不是文件: {rel_path}")

    size = target.stat().st_size
    # 二进制安全读取；文本尝试 utf-8 解码失败则返回 base64
    with target.open("rb") as f:
        raw = f.read(max_bytes + 1)
    truncated = len(raw) > max_bytes
    raw = raw[:max_bytes]
    try:
        text = raw.decode("utf-8")
        encoding = "utf-8"
        content = text
    except UnicodeDecodeError:
        import base64
        content = base64.b64encode(raw).decode("ascii")
        encoding = "base64"

    return {
        "path": rel_path,
        "size": size,
        "truncated": truncated,
        "encoding": encoding,
        "content": content,
    }


def write_file(cid: str, rel_path: str, content: str, *, encoding: str = "utf-8") -> dict:
    """写入工作空间内某文件（覆盖）。"""
    if len(content) > MAX_WRITE_BYTES:
        raise WorkspaceError(f"内容超过最大写入字节 ({MAX_WRITE_BYTES})")
    target = resolve_safe_path(cid, rel_path, create_parents=True)
    if encoding == "utf-8":
        raw = content.encode("utf-8")
    elif encoding == "base64":
        import base64
        raw = base64.b64decode(content)
    else:
        raise WorkspaceError(f"不支持的 encoding: {encoding}")

    # 原子写：临时文件 + replace
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(target)
    return {
        "path": rel_path,
        "size": len(raw),
        "encoding": encoding,
    }


# ---------------------------------------------------------------------------
# AgentTool 工厂：workspace_list / workspace_read / workspace_write
# ---------------------------------------------------------------------------

_WORKSPACE_LIST_PARAMS: dict = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "相对工作空间根的目录路径，缺省为根目录",
        },
    },
    "required": [],
}

_WORKSPACE_READ_PARAMS: dict = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "相对工作空间根的文件路径"},
    },
    "required": ["path"],
}

_WORKSPACE_WRITE_PARAMS: dict = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "相对工作空间根的文件路径"},
        "content": {"type": "string", "description": "文件内容（utf-8 文本或 base64）"},
        "encoding": {
            "type": "string",
            "enum": ["utf-8", "base64"],
            "description": "内容编码，默认 utf-8",
        },
    },
    "required": ["path", "content"],
}


def create_workspace_tools(cid: str) -> list[AgentTool]:
    """构造工作空间三个 AgentTool。

    Args:
        cid: 会话 id；工具仅可访问此会话的工作空间。
    """
    return [
        _build_workspace_list(cid),
        _build_workspace_read(cid),
        _build_workspace_write(cid),
    ]


def _build_workspace_list(cid: str) -> AgentTool:
    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        rel = str(params.get("path") or "")
        try:
            payload = await asyncio.to_thread(list_directory, cid, rel)
        except WorkspaceError as exc:
            return _error_result(call_id, str(exc))
        except FileNotFoundError as exc:
            return _error_result(call_id, f"路径不存在: {exc}")
        return _text_result(call_id, json.dumps(payload, ensure_ascii=False))

    return AgentTool(
        name="workspace_list",
        description="列出当前会话工作空间目录内容。path 为相对路径，缺省为根目录。",
        parameters=_WORKSPACE_LIST_PARAMS,
        execution_mode="parallel",
        execute=execute,
    )


def _build_workspace_read(cid: str) -> AgentTool:
    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        rel = str(params.get("path") or "")
        try:
            payload = await asyncio.to_thread(read_file, cid, rel)
        except WorkspaceError as exc:
            return _error_result(call_id, str(exc))
        except FileNotFoundError:
            return _error_result(call_id, f"文件不存在: {rel}")
        return _text_result(call_id, json.dumps(payload, ensure_ascii=False))

    return AgentTool(
        name="workspace_read",
        description="读取当前会话工作空间内的文件。返回 {path,size,truncated,encoding,content}。",
        parameters=_WORKSPACE_READ_PARAMS,
        execution_mode="parallel",
        execute=execute,
    )


def _build_workspace_write(cid: str) -> AgentTool:
    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        rel = str(params.get("path") or "")
        content = str(params.get("content") or "")
        encoding = str(params.get("encoding") or "utf-8")
        try:
            payload = await asyncio.to_thread(write_file, cid, rel, content, encoding=encoding)
        except WorkspaceError as exc:
            return _error_result(call_id, str(exc))
        return _text_result(call_id, json.dumps(payload, ensure_ascii=False))

    return AgentTool(
        name="workspace_write",
        description="写入当前会话工作空间内的文件（覆盖）。encoding 默认 utf-8，可传 base64。",
        parameters=_WORKSPACE_WRITE_PARAMS,
        execution_mode="serial",  # 写操作串行避免冲突
        execute=execute,
    )


# ---------------------------------------------------------------------------
# ToolResult 构造助手（与 builtin_tools.py 一致风格）
# ---------------------------------------------------------------------------

def _text_result(call_id: str, text: str) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        content=[{"type": "text", "text": text}],
        is_error=False,
    )


def _error_result(call_id: str, message: str, *, details: dict | None = None) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        content=[{"type": "text", "text": json.dumps({"error": message}, ensure_ascii=False)}],
        is_error=True,
        details=details or {},
    )


__all__ = [
    "ALLOWED_TOP_DIRS",
    "WorkspaceError",
    "workspaces_root",
    "workspace_root",
    "ensure_workspace",
    "resolve_safe_path",
    "list_directory",
    "read_file",
    "write_file",
    "create_workspace_tools",
]
