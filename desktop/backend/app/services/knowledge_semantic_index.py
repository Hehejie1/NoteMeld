from __future__ import annotations

from app.services.knowledge_evidence_index import KnowledgeEvidenceIndex


class KnowledgeSemanticIndex:
    def __init__(self, index: KnowledgeEvidenceIndex | None = None):
        self.index = index or KnowledgeEvidenceIndex()

    def upsert(self, records: list[dict]) -> None:
        self.index.upsert("K3", records)

    def query(self, query: str, article_ids: list[str] | None, limit: int) -> list[dict]:
        return self.index.query("K3", query, article_ids, limit)
