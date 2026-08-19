"""Small product capability registry owned by the NoteMeld Host.

The Rust SDK owns discovery, scheduling and cancellation.  This module only
adapts existing NoteMeld knowledge services to the SDK ToolDriver boundary.
It deliberately exposes bounded, read-only capabilities first.
"""
from __future__ import annotations

import inspect
from typing import Any, Callable

from app.services.note_document_store import read_note_document_by_title, search_note_documents_by_title
from app.services.wiki_search import WikiSearch
from app.utils.storage_paths import note_output_dir


class CapabilityError(Exception):
    """Safe product error that may cross the ToolDriver boundary."""

    code = "business_error"


class UnknownCapabilityError(CapabilityError):
    code = "unknown_tool"


class InvalidCapabilityArguments(CapabilityError):
    code = "invalid_arguments"


class CapabilityBusinessError(CapabilityError):
    code = "business_error"


class NoteMeldCapabilityRegistry:
    _DESCRIPTORS = {
        "wiki:search": {
            "name": "wiki:search",
            "description": "在 NoteMeld 已编译 Wiki 中搜索相关知识和来源。",
            "risk": "safe",
            "safe": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
        "note:search": {
            "name": "note:search",
            "description": "按标题搜索用户保存的 Note。",
            "risk": "safe",
            "safe": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
        "note:read": {
            "name": "note:read",
            "description": "按标题读取一篇用户保存的 Note。",
            "risk": "safe",
            "safe": True,
            "input_schema": {
                "type": "object",
                "properties": {"title": {"type": "string", "minLength": 1}},
                "required": ["title"],
            },
        },
    }

    def describe(self, names: list[str]) -> list[dict[str, Any]]:
        selected = names or list(self._DESCRIPTORS)
        return [self._DESCRIPTORS[name] for name in selected if name in self._DESCRIPTORS]

    def get_tool(self, name: str) -> dict[str, Any] | None:
        return self._DESCRIPTORS.get(name)

    async def invoke(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: str,
        signal: Any,
        on_update: Callable[[dict[str, Any]], Any],
    ) -> dict[str, Any]:
        del call_id, signal
        if name not in self._DESCRIPTORS:
            raise UnknownCapabilityError("未知产品能力")
        update_result = on_update({"message": "正在读取 NoteMeld 知识", "progress": 0.0})
        if inspect.isawaitable(update_result):
            await update_result
        if name == "wiki:search":
            query = str(arguments.get("query") or "").strip()
            if not query:
                raise InvalidCapabilityArguments("query 不能为空")
            try:
                limit = max(1, min(int(arguments.get("limit") or 5), 20))
            except (TypeError, ValueError) as error:
                raise InvalidCapabilityArguments("limit 必须是整数") from error
            result = WikiSearch(note_output_dir() / "wiki").search(query, limit=limit)
        elif name == "note:search":
            query = str(arguments.get("query") or "").strip()
            if not query:
                raise InvalidCapabilityArguments("query 不能为空")
            try:
                limit = max(1, min(int(arguments.get("limit") or 10), 20))
            except (TypeError, ValueError) as error:
                raise InvalidCapabilityArguments("limit 必须是整数") from error
            result = search_note_documents_by_title(query, limit=limit)
        elif name == "note:read":
            title = str(arguments.get("title") or "").strip()
            if not title:
                raise InvalidCapabilityArguments("title 不能为空")
            result = read_note_document_by_title(title)
            if result is None:
                raise CapabilityBusinessError("Note 不存在")
        update_result = on_update({"message": "知识读取完成", "progress": 1.0})
        if inspect.isawaitable(update_result):
            await update_result
        return result


__all__ = [
    "CapabilityBusinessError",
    "CapabilityError",
    "InvalidCapabilityArguments",
    "NoteMeldCapabilityRegistry",
    "UnknownCapabilityError",
]
