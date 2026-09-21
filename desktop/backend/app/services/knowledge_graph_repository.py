from __future__ import annotations

from typing import Any

from app.services.knowledge_repository import KnowledgeRepository


class KnowledgeGraphRepository:
    """Graph-facing facade; SQLite owns canonical nodes and provenance."""

    def __init__(self, repository: KnowledgeRepository | None = None):
        self.repository = repository or KnowledgeRepository()

    def search(self, query: str, *, article_ids: list[str] | None, relation_types: list[str] | None, limit: int) -> dict[str, Any]:
        terms = self.repository.search_terms(query, article_ids, limit)
        term_ids = list(dict.fromkeys(str(item.get("term_id")) for item in terms if item.get("term_id")))
        relations = self.repository.search_relations(term_ids, article_ids, relation_types, limit) if term_ids else []
        return {"terms": terms, "relations": relations}
