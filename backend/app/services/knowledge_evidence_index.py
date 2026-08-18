from __future__ import annotations

from typing import Any

from app.services.vector_store import VECTOR_DB_DIR


class KnowledgeEvidenceIndex:
    COLLECTIONS = {"K1": "knowledge_k1_v1", "K2": "knowledge_k2_v1", "K3": "knowledge_k3_v1"}

    def __init__(self, *, client=None, enabled: bool = True):
        self.enabled = enabled
        self.client = client
        if self.enabled and self.client is None:
            try:
                import chromadb
                from chromadb.config import Settings

                self.client = chromadb.PersistentClient(path=VECTOR_DB_DIR, settings=Settings(anonymized_telemetry=False))
            except Exception:
                # SQLite FTS remains the authoritative lexical index when a
                # packaged/test environment has no usable Chroma client.
                self.enabled = False

    def upsert(self, layer: str, records: list[dict[str, Any]]) -> None:
        if not self.enabled or not records:
            return
        collection = self.client.get_or_create_collection(
            name=self.COLLECTIONS[layer],
            metadata={"hnsw:space": "cosine", "index_version": "knowledge_index.v1"},
        )
        collection.upsert(
            ids=[str(item["id"]) for item in records],
            documents=[str(item.get("text") or "") for item in records],
            metadatas=[self._metadata(item) for item in records],
        )

    def query(self, layer: str, query: str, article_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
        if not self.enabled or self.client is None:
            return []
        try:
            collection = self.client.get_collection(self.COLLECTIONS[layer])
            where = None
            if article_ids is not None:
                where = {"article_id": {"$in": article_ids}}
            results = collection.query(query_texts=[query], n_results=limit, where=where)
        except Exception:
            return []
        rows = []
        for index, document in enumerate((results.get("documents") or [[]])[0]):
            metadata = (results.get("metadatas") or [[]])[0][index] or {}
            rows.append({
                "id": (results.get("ids") or [[]])[0][index],
                "text": document,
                "metadata": metadata,
                "distance": (results.get("distances") or [[]])[0][index],
            })
        return rows

    def _metadata(self, item: dict[str, Any]) -> dict[str, Any]:
        return {key: (value if value is not None else "") for key, value in {
            "article_id": item.get("article_id"),
            "title": item.get("title"),
            "page_number": item.get("page_number"),
            "section_path": item.get("section_path"),
            "term_type": item.get("term_type"),
            "result_id": item.get("id"),
        }.items()}
