from __future__ import annotations

import asyncio
from typing import Any, Callable

from app.models.knowledge_retrieval import CAPABILITY_IDS, KnowledgeQueryError
from app.services.knowledge_query_service import KnowledgeQueryService


class _KnowledgeTool:
    execution_mode = "serial"

    def __init__(self, provider: "KnowledgeCapabilityProvider", descriptor: dict[str, Any]):
        self.provider = provider
        self.name = descriptor["id"]
        self.description = descriptor["description"]
        self.parameters = descriptor["parameters"]

    async def execute(self, call_id, params, signal, on_update):
        if getattr(signal, "aborted", False):
            return {"call_id": call_id, "content": [{"type": "text", "text": "cancelled"}]}
        await on_update({"call_id": call_id, "stage": "query_started", "capability_id": self.name})
        try:
            result = await self.provider.invoke(self.name, params, call_id=call_id, signal=signal, on_progress=on_update)
        except KnowledgeQueryError as exc:
            result = {"schema_version": "knowledge_result.v1", "capability_id": self.name, "error": {"code": exc.code, "message": exc.message}, "results": [], "total": 0}
        return {"call_id": call_id, "content": [{"type": "json", "json": result}], "structured_content": result}


class KnowledgeCapabilityProvider:
    """Product-owned manifest and invocation adapter for the four K tools."""

    def __init__(self, query_service: KnowledgeQueryService | None = None, *, use_wiki: bool = True):
        self.query_service = query_service or KnowledgeQueryService()
        self.use_wiki = use_wiki

    def manifest(self) -> list[dict[str, Any]]:
        descriptors = [
            {"id": "knowledge:article_lookup", "name": "article_lookup", "description": "按 article_id 精确读取 K0 文章事实源。", "parameters": {"type": "object", "properties": {"article_ids": {"type": "array", "items": {"type": "string"}}, "query": {"type": "string"}}}},
            {"id": "knowledge:evidence_search", "name": "evidence_search", "description": "在 K1 原文证据块中执行带文章和页码过滤的混合检索。", "parameters": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}, "article_ids": {"type": "array", "items": {"type": "string"}}, "location": {"type": "object"}, "top_k": {"type": "integer"}}}},
            {"id": "knowledge:profile_search", "name": "profile_search", "description": "在 K2 高密文档画像中圈定候选文章。", "parameters": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}, "article_ids": {"type": "array", "items": {"type": "string"}}, "filters": {"type": "object"}, "top_k": {"type": "integer"}}}},
            {"id": "knowledge:semantic_search", "name": "semantic_search", "description": "搜索 K3 实体、概念、关系及其文章证据 provenance。", "parameters": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}, "article_ids": {"type": "array", "items": {"type": "string"}}, "node_types": {"type": "array"}, "relation_types": {"type": "array"}, "hops": {"type": "integer"}, "top_k": {"type": "integer"}}}},
        ]
        if not self.use_wiki:
            descriptors = [item for item in descriptors if item["id"] not in {"knowledge:profile_search", "knowledge:semantic_search"}]
        return descriptors

    def get_tool(self, name: str) -> _KnowledgeTool | None:
        descriptor = next((item for item in self.manifest() if item["id"] == name or item["name"] == name), None)
        return _KnowledgeTool(self, descriptor) if descriptor else None

    async def describe(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        descriptors = self.manifest()
        if not names:
            return descriptors
        selected = set(names)
        return [item for item in descriptors if item["id"] in selected or item["name"] in selected]

    async def invoke(self, name: str, arguments: dict[str, Any], call_id: str = "", signal: Any = None, on_progress: Callable[[dict[str, Any]], Any] | None = None) -> dict[str, Any]:
        canonical = name if name.startswith("knowledge:") else f"knowledge:{name}"
        if canonical not in {item["id"] for item in self.manifest()}:
            raise KnowledgeQueryError("unknown_tool", f"unknown knowledge capability: {name}")
        if on_progress is not None:
            update = on_progress({"call_id": call_id, "stage": "query_dispatch"})
            if asyncio.iscoroutine(update):
                await update
        if canonical == "knowledge:article_lookup":
            return self.query_service.article_lookup(**arguments)
        if canonical == "knowledge:evidence_search":
            return self.query_service.evidence_search(**arguments, cancel_check=lambda: bool(getattr(signal, "aborted", False)))
        if canonical == "knowledge:profile_search":
            return self.query_service.profile_search(**arguments)
        return self.query_service.semantic_search(**arguments)


__all__ = ["CAPABILITY_IDS", "KnowledgeCapabilityProvider"]
