"""P2-T2: 内建 AgentTool 集合（7 个）。

迁移自 ``chat_tools.py`` 的 3 个工具（``lookup_transcript`` / ``get_video_info``
/ ``get_note_content``）+ 新增 4 个（``search_knowledge`` / ``read_note`` /
``read_transcript`` / ``get_compile_status``）。

设计要点：
- 复用 ``chat_tools._load_note_data`` / ``_lookup_transcript`` / ``_get_video_info``
  / ``_get_note_content`` 的同步实现，避免逻辑分叉。
- 所有 execute 函数均为 async；同步 IO 通过 ``asyncio.to_thread`` 包装，避免阻塞
  agent_loop（同时兼容 signal.aborted 检测）。
- 返回 ``ToolResult`` 或等价 dict；loop 内部统一规范化。
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Optional

from app.agent.core.signal import AbortSignal
from app.agent.core.tool import AgentTool, ToolResult
from app.utils.logger import get_logger
from app.utils.storage_paths import note_output_dir

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 参数 schema 复用 chat_tools 的 OpenAI function calling 定义
# ---------------------------------------------------------------------------

_LOOKUP_TRANSCRIPT_PARAMS: dict = {
    "type": "object",
    "properties": {
        "start_time": {
            "type": "number",
            "description": "起始时间（秒），例如 0 表示视频开头，60 表示第1分钟",
        },
        "end_time": {
            "type": "number",
            "description": "结束时间（秒），不传则到末尾",
        },
        "keyword": {
            "type": "string",
            "description": "搜索关键词，返回包含该关键词的转录片段",
        },
        "position": {
            "type": "string",
            "enum": ["start", "end"],
            "description": "快捷位置：start=视频开头前30句，end=视频结尾后30句",
        },
    },
    "required": [],
}

_EMPTY_PARAMS: dict = {"type": "object", "properties": {}, "required": []}

_SEARCH_KNOWLEDGE_PARAMS: dict = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "检索查询语句",
        },
        "limit": {
            "type": "integer",
            "description": "返回结果条数上限，默认 6",
        },
        "scope": {
            "type": "string",
            "enum": ["note", "wiki", "all"],
            "description": "检索范围：note=仅当前关联笔记向量；wiki=仅 llm wiki；all=两者合并（默认）",
        },
    },
    "required": ["query"],
}

_READ_NOTE_PARAMS: dict = {
    "type": "object",
    "properties": {
        "task_id": {
            "type": "string",
            "description": "笔记任务 id；不传时使用会话关联的 linked_task_id",
        },
        "max_length": {
            "type": "integer",
            "description": "返回 markdown 最大字符数，默认 5000",
        },
    },
    "required": [],
}

_READ_TRANSCRIPT_PARAMS: dict = {
    "type": "object",
    "properties": {
        "task_id": {
            "type": "string",
            "description": "笔记任务 id；不传时使用会话关联的 linked_task_id",
        },
        "start_time": {
            "type": "number",
            "description": "起始时间（秒）",
        },
        "end_time": {
            "type": "number",
            "description": "结束时间（秒）",
        },
        "keyword": {
            "type": "string",
            "description": "关键词过滤",
        },
        "limit": {
            "type": "integer",
            "description": "返回片段上限，默认 50",
        },
    },
    "required": [],
}

_GET_COMPILE_STATUS_PARAMS: dict = {
    "type": "object",
    "properties": {
        "task_id": {
            "type": "string",
            "description": "笔记任务 id；不传时使用会话关联的 linked_task_id",
        },
    },
    "required": [],
}


# ---------------------------------------------------------------------------
# 工具构造入口
# ---------------------------------------------------------------------------

def create_builtin_tools(task_id: Optional[str] = None) -> list[AgentTool]:
    """创建 P2 内建工具集合。

    Args:
        task_id: 会话关联的 linked_task_id；工具参数缺省时使用此值。

    Returns:
        7 个 AgentTool 实例。
    """
    return [
        _build_lookup_transcript(task_id),
        _build_get_video_info(task_id),
        _build_get_note_content(task_id),
        _build_search_knowledge(task_id),
        _build_read_note(task_id),
        _build_read_transcript(task_id),
        _build_get_compile_status(task_id),
    ]


# ---------------------------------------------------------------------------
# 迁移自 chat_tools 的 3 个工具
# ---------------------------------------------------------------------------

def _build_lookup_transcript(task_id: Optional[str]) -> AgentTool:
    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        from app.services.chat_tools import _lookup_transcript, _load_note_data

        tid = params.get("task_id") or task_id
        if not tid:
            return _error_result(call_id, "缺少 task_id（参数或会话 linked_task_id）")
        data = await asyncio.to_thread(_load_note_data, tid)
        if not data:
            return _error_result(call_id, "笔记数据不存在", details={"task_id": tid})
        # 复用旧实现：返回 JSON 字符串
        text = await asyncio.to_thread(_lookup_transcript, data, params)
        return _text_result(call_id, text)

    return AgentTool(
        name="lookup_transcript",
        description=(
            "查询视频原始转录文本。可按时间范围筛选、按关键词搜索、或获取指定位置的内容。"
            "（默认作用于会话关联的 linked_task_id；可通过 task_id 参数指定其他笔记）"
        ),
        parameters=_LOOKUP_TRANSCRIPT_PARAMS,
        execution_mode="parallel",
        execute=execute,
    )


def _build_get_video_info(task_id: Optional[str]) -> AgentTool:
    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        from app.services.chat_tools import _get_video_info, _load_note_data

        tid = params.get("task_id") or task_id
        if not tid:
            return _error_result(call_id, "缺少 task_id")
        data = await asyncio.to_thread(_load_note_data, tid)
        if not data:
            return _error_result(call_id, "笔记数据不存在", details={"task_id": tid})
        text = await asyncio.to_thread(_get_video_info, data)
        return _text_result(call_id, text)

    return AgentTool(
        name="get_video_info",
        description=(
            "获取视频的完整元信息，包括标题、作者、简介、标签、时长、播放量等。"
            "（默认作用于会话关联的 linked_task_id；可通过 task_id 参数指定其他笔记）"
        ),
        parameters=_EMPTY_PARAMS,
        execution_mode="parallel",
        execute=execute,
    )


def _build_get_note_content(task_id: Optional[str]) -> AgentTool:
    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        from app.services.chat_tools import _get_note_content, _load_note_data

        tid = params.get("task_id") or task_id
        if not tid:
            return _error_result(call_id, "缺少 task_id")
        data = await asyncio.to_thread(_load_note_data, tid)
        if not data:
            return _error_result(call_id, "笔记数据不存在", details={"task_id": tid})
        text = await asyncio.to_thread(_get_note_content, data)
        return _text_result(call_id, text)

    return AgentTool(
        name="get_note_content",
        description=(
            "获取 AI 生成的完整笔记内容（Markdown 格式）。"
            "（默认作用于会话关联的 linked_task_id；可通过 task_id 参数指定其他笔记）"
        ),
        parameters=_EMPTY_PARAMS,
        execution_mode="parallel",
        execute=execute,
    )


# ---------------------------------------------------------------------------
# 新增 4 个工具
# ---------------------------------------------------------------------------

def _build_search_knowledge(task_id: Optional[str]) -> AgentTool:
    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        query = str(params.get("query") or "").strip()
        if not query:
            return _error_result(call_id, "缺少 query 参数")
        limit = int(params.get("limit") or 6)
        scope = str(params.get("scope") or "all").lower()
        if scope not in {"note", "wiki", "all"}:
            scope = "all"

        results: list[dict] = []

        # 笔记向量检索
        if scope in {"note", "all"} and task_id:
            try:
                from app.services.vector_store import VectorStoreManager

                chunks = await asyncio.to_thread(
                    VectorStoreManager().query,
                    task_id,
                    query,
                    limit,
                )
                for chunk in chunks or []:
                    meta = chunk.get("metadata", {})
                    results.append({
                        "source_type": meta.get("source_type", "note"),
                        "text": chunk.get("text", ""),
                        "metadata": meta,
                    })
            except Exception as exc:  # noqa: BLE001
                logger.warning("search_knowledge 笔记检索失败: %s", exc)

        # Wiki 检索
        if scope in {"wiki", "all"}:
            try:
                from app.services.wiki_search import WikiSearch

                wiki_sources = await asyncio.to_thread(
                    WikiSearch(note_output_dir() / "wiki").search,
                    query,
                    limit,
                )
                for src in wiki_sources or []:
                    results.append({
                        "source_type": "wiki",
                        "text": src.get("text", "") or src.get("snippet", ""),
                        "title": src.get("title", ""),
                        "page_id": src.get("page_id", ""),
                        "metadata": src.get("metadata", {}),
                    })
            except Exception as exc:  # noqa: BLE001
                logger.warning("search_knowledge wiki 检索失败: %s", exc)

        payload = {
            "query": query,
            "scope": scope,
            "linked_task_id": task_id,
            "total": len(results),
            "results": results,
        }
        return _text_result(call_id, json.dumps(payload, ensure_ascii=False))

    return AgentTool(
        name="search_knowledge",
        description=(
            "在知识库中检索内容。可在当前关联笔记的向量索引和 llm wiki 中检索。"
            "返回匹配片段列表（含 source_type / text / metadata）。"
            "scope: note=仅笔记向量；wiki=仅 wiki；all=两者合并（默认）。"
        ),
        parameters=_SEARCH_KNOWLEDGE_PARAMS,
        execution_mode="parallel",
        execute=execute,
    )


def _build_read_note(task_id: Optional[str]) -> AgentTool:
    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        from app.services.chat_tools import _load_note_data

        tid = params.get("task_id") or task_id
        if not tid:
            return _error_result(call_id, "缺少 task_id")
        max_length = int(params.get("max_length") or 5000)
        data = await asyncio.to_thread(_load_note_data, tid)
        if not data:
            return _error_result(call_id, "笔记数据不存在", details={"task_id": tid})
        md = data.get("markdown", "")
        if isinstance(md, list):
            md = md[-1].get("content", "") if md else ""
        if len(md) > max_length:
            md = md[:max_length] + "\n\n... (内容过长已截断)"
        payload = {"task_id": tid, "markdown": md}
        return _text_result(call_id, json.dumps(payload, ensure_ascii=False))

    return AgentTool(
        name="read_note",
        description=(
            "读取指定笔记的 markdown 全文。task_id 不传时使用会话关联的 linked_task_id。"
            "可通过 max_length 限制返回长度（默认 5000 字符）。"
        ),
        parameters=_READ_NOTE_PARAMS,
        execution_mode="parallel",
        execute=execute,
    )


def _build_read_transcript(task_id: Optional[str]) -> AgentTool:
    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        from app.services.chat_tools import _load_note_data

        tid = params.get("task_id") or task_id
        if not tid:
            return _error_result(call_id, "缺少 task_id")
        data = await asyncio.to_thread(_load_note_data, tid)
        if not data:
            return _error_result(call_id, "笔记数据不存在", details={"task_id": tid})

        segments = data.get("transcript", {}).get("segments", []) or []
        start_time = params.get("start_time")
        end_time = params.get("end_time")
        keyword = str(params.get("keyword") or "").strip().lower()
        limit = int(params.get("limit") or 50)

        filtered = segments
        if start_time is not None:
            filtered = [s for s in filtered if s.get("end", 0) >= start_time]
        if end_time is not None:
            filtered = [s for s in filtered if s.get("start", 0) <= end_time]
        if keyword:
            filtered = [s for s in filtered if keyword in (s.get("text", "") or "").lower()]

        truncated = len(filtered) > limit
        filtered = filtered[:limit]
        payload = {
            "task_id": tid,
            "total_segments": len(segments),
            "returned": len(filtered),
            "truncated": truncated,
            "segments": [
                {
                    "start": round(s.get("start", 0), 1),
                    "end": round(s.get("end", 0), 1),
                    "text": s.get("text", ""),
                }
                for s in filtered
            ],
        }
        return _text_result(call_id, json.dumps(payload, ensure_ascii=False))

    return AgentTool(
        name="read_transcript",
        description=(
            "读取视频转录片段。可按时间范围、关键词过滤，限制返回条数。"
            "task_id 不传时使用会话关联的 linked_task_id。"
        ),
        parameters=_READ_TRANSCRIPT_PARAMS,
        execution_mode="parallel",
        execute=execute,
    )


def _build_get_compile_status(task_id: Optional[str]) -> AgentTool:
    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        tid = params.get("task_id") or task_id
        if not tid:
            return _error_result(call_id, "缺少 task_id")
        status_path = note_output_dir() / f"{tid}.status.json"
        result_path = note_output_dir() / f"{tid}.json"

        def _read() -> dict:
            payload: dict = {"task_id": tid, "status": "UNKNOWN", "exists": False}
            if status_path.exists():
                try:
                    raw = json.loads(status_path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        payload.update(raw)
                        payload["status"] = raw.get("status", "UNKNOWN")
                        payload["exists"] = True
                except Exception as exc:  # noqa: BLE001
                    logger.warning("读取 status 文件失败: %s", exc)
            payload["result_file_exists"] = result_path.exists()
            return payload

        payload = await asyncio.to_thread(_read)
        return _text_result(call_id, json.dumps(payload, ensure_ascii=False))

    return AgentTool(
        name="get_compile_status",
        description=(
            "查询笔记编译任务状态（PENDING/DOWNLOADING/TRANSCRIBING/SUMMARIZING/SUCCESS/FAILED/CANCELED 等）。"
            "task_id 不传时使用会话关联的 linked_task_id。"
        ),
        parameters=_GET_COMPILE_STATUS_PARAMS,
        execution_mode="parallel",
        execute=execute,
    )


# ---------------------------------------------------------------------------
# ToolResult 构造助手
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


__all__ = ["create_builtin_tools"]
