"""Small product capability registry owned by the NoteMeld Host.

The Rust SDK owns discovery, scheduling and cancellation.  This module only
adapts existing NoteMeld knowledge services to the SDK ToolDriver boundary.
It deliberately exposes bounded, read-only capabilities first.
"""
from __future__ import annotations

import inspect
import uuid
from typing import Any, Callable

from app.agent_host.note_contract import NoteId, SdkNoteDto
from app.agent_host.note_store_adapter import NoteActorDto, NoteMeldNoteStoreAdapter, NoteProvenanceDto
from app.utils.storage_paths import database_path
from app.services.note_document_store import read_note_document_by_title
from app.services.conversation_store import upsert_conversation
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
        "note:create": {
            "name": "note:create",
            "description": "通过 NoteMeld Note authority 创建一篇带 provenance 的 Note。",
            "risk": "write",
            "safe": False,
            "input_schema": {"type": "object", "properties": {
                "title": {"type": "string", "minLength": 1},
                "content": {"type": "string", "minLength": 1},
                "source_url": {"type": "string"}, "platform": {"type": "string"},
                "parent_note_id": {"type": "string"}, "request_id": {"type": "string"},
            }, "required": ["title", "content"]},
        },
        "note:link": {
            "name": "note:link",
            "description": "通过 NoteMeld Note authority 关联两篇 Note。",
            "risk": "write",
            "safe": False,
            "input_schema": {"type": "object", "properties": {
                "source_note_id": {"type": "string", "minLength": 1},
                "target_note_id": {"type": "string", "minLength": 1},
                "kind": {"type": "string"}, "request_id": {"type": "string"},
            }, "required": ["source_note_id", "target_note_id"]},
        },
        "note:relations": {
            "name": "note:relations",
            "description": "读取 Note 的来源关系和 provenance。",
            "risk": "safe",
            "safe": True,
            "input_schema": {"type": "object", "properties": {
                "note_id": {"type": "string", "minLength": 1},
            }, "required": ["note_id"]},
        },
    }

    def describe(self, names: list[str]) -> list[dict[str, Any]]:
        selected = names or ["wiki:search", "note:search", "note:read"]
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
            store = NoteMeldNoteStoreAdapter(database_path(), conversation_id=str(getattr(signal, "session_id", "") or "agent"))
            result = [note.__dict__ for note in store.search(query, limit=limit)]
        elif name == "note:read":
            title = str(arguments.get("title") or "").strip()
            if not title:
                raise InvalidCapabilityArguments("title 不能为空")
            result = read_note_document_by_title(title)
            if result is None:
                raise CapabilityBusinessError("Note 不存在")
        elif name == "note:create":
            title = str(arguments.get("title") or "").strip()
            content = str(arguments.get("content") or "")
            if not title or not content:
                raise InvalidCapabilityArguments("title 和 content 不能为空")
            request_id = str(arguments.get("request_id") or call_id or uuid.uuid4())
            note_id = NoteId(str(arguments.get("note_id") or uuid.uuid4()))
            provenance = NoteProvenanceDto(
                actor=NoteActorDto("agent", "agent"),
                operation_id="",
                turn_id=str(getattr(signal, "turn_id", "") or "") or None,
                sources=(),
            )
            conversation_id = str(getattr(signal, "session_id", "") or "agent")
            upsert_conversation({"id": conversation_id, "mode": "chat", "title": "Agent Note"})
            store = NoteMeldNoteStoreAdapter(database_path(), conversation_id=conversation_id)
            created = store.create(SdkNoteDto(note_id=note_id, title=title, content=content,
                                               source_url=str(arguments.get("source_url") or ""),
                                               platform=str(arguments.get("platform") or "")), request_id,
                                   provenance=provenance)
            result = {"note_id": str(created.note.note_id), "title": created.note.title,
                      "operation_id": created.operation_id, "replayed": created.replayed}
            if arguments.get("parent_note_id"):
                linked = store.link(NoteId(str(arguments["parent_note_id"])), note_id,
                                    f"{request_id}:relation", provenance=provenance)
                result["relation"] = {"relation_id": linked.relation.relation_id, "kind": linked.relation.kind}
        elif name == "note:link":
            request_id = str(arguments.get("request_id") or call_id or uuid.uuid4())
            provenance = NoteProvenanceDto(actor=NoteActorDto("agent", "agent"),
                                            turn_id=str(getattr(signal, "turn_id", "") or "") or None)
            store = NoteMeldNoteStoreAdapter(database_path(), conversation_id=str(getattr(signal, "session_id", "") or "agent"))
            linked = store.link(NoteId(str(arguments.get("source_note_id") or "")),
                                NoteId(str(arguments.get("target_note_id") or "")), request_id,
                                provenance=provenance, kind=str(arguments.get("kind") or "related"))
            result = {"relation_id": linked.relation.relation_id, "source_note_id": str(linked.relation.source),
                      "target_note_id": str(linked.relation.target), "kind": linked.relation.kind,
                      "operation_id": linked.operation_id, "replayed": linked.replayed}
        elif name == "note:relations":
            note_id = NoteId(str(arguments.get("note_id") or ""))
            store = NoteMeldNoteStoreAdapter(database_path(), conversation_id=str(getattr(signal, "session_id", "") or "agent"))
            result = {"note_id": str(note_id), "relations": [r.__dict__ for r in store.relations(note_id)],
                      "provenance": list(store.provenance(note_id)), "sources": [s.__dict__ for s in store.sources(note_id)]}
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
