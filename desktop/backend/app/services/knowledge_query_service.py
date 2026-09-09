from __future__ import annotations

from typing import Any, Callable

from app.models.knowledge_retrieval import KnowledgeQueryError, KnowledgeResult, bounded_top_k, result_envelope, validate_article_ids
from app.services.knowledge_graph_repository import KnowledgeGraphRepository
from app.services.knowledge_repository import KnowledgeRepository
from app.services.knowledge_evidence_index import KnowledgeEvidenceIndex


class KnowledgeQueryService:
    def __init__(self, *, repository: KnowledgeRepository | None = None, vector_index: KnowledgeEvidenceIndex | None = None):
        self.repository = repository or KnowledgeRepository()
        self.vector_index = vector_index or KnowledgeEvidenceIndex()
        self.graph = KnowledgeGraphRepository(self.repository)

    def article_lookup(self, *, article_ids: list[str] | None = None, query: str | None = None, max_chars: int = 12000) -> dict[str, Any]:
        article_ids = validate_article_ids(article_ids)
        rows = self.repository.get_articles(article_ids)
        if query:
            needle = str(query).strip().lower()
            rows = [row for row in rows if needle in f"{row['title']}\n{row['content']}".lower()]
        results = [KnowledgeResult(
            layer="K0",
            article_id=row["article_id"],
            result_id=row["article_id"],
            title=row["title"],
            text=row["content"][:max_chars],
            source_ref={"article_id": row["article_id"]},
            metadata={"source_type": row["source_type"], "source_url": row["source_url"]},
        ) for row in rows]
        return result_envelope("knowledge:article_lookup", results)

    def evidence_search(self, *, query: str, article_ids: list[str] | None = None, location: dict[str, Any] | None = None, top_k: int = 10, cancel_check: Callable[[], bool] | None = None) -> dict[str, Any]:
        article_ids = validate_article_ids(article_ids)
        top_k = bounded_top_k(top_k)
        if not str(query or "").strip():
            raise KnowledgeQueryError("invalid_arguments", "query is required")
        if cancel_check and cancel_check():
            return result_envelope("knowledge:evidence_search", [], ["cancelled"])
        lexical = self.repository.search_chunks(query, article_ids, top_k * 2)
        vector = self.vector_index.query("K1", query, article_ids, top_k)
        by_id: dict[str, KnowledgeResult] = {}
        for row in lexical:
            item = KnowledgeResult(
                layer="K1",
                article_id=str(row["article_id"]),
                result_id=str(row["chunk_id"]),
                title=str(row.get("title") or ""),
                text=str(row.get("content") or ""),
                location={"section_path": row.get("section_path")},
                scores={"vector": None, "bm25": float(row.get("rank") or 0)},
                source_ref={"article_id": row["article_id"], "chunk_id": row["chunk_id"]},
            )
            by_id[item.result_id] = item
        for row in vector:
            metadata = row.get("metadata") or {}
            result_id = str(metadata.get("result_id") or row.get("id"))
            if article_ids is not None and str(metadata.get("article_id")) not in article_ids:
                continue
            item = by_id.get(result_id) or KnowledgeResult(
                layer="K1",
                article_id=str(metadata.get("article_id") or ""),
                result_id=result_id,
                title=str(metadata.get("title") or ""),
                text=str(row.get("text") or ""),
                location={"page_number": metadata.get("page_number"), "section_path": metadata.get("section_path")},
                source_ref={"article_id": metadata.get("article_id"), "chunk_id": result_id},
            )
            item.scores["vector"] = 1.0 - float(row.get("distance") or 0)
            by_id[result_id] = item
        results = [item for item in by_id.values() if self._matches_location(item, location)]
        results.sort(key=lambda item: self._score(item), reverse=True)
        return result_envelope("knowledge:evidence_search", results[:top_k])

    def profile_search(self, *, query: str, article_ids: list[str] | None = None, filters: dict[str, Any] | None = None, top_k: int = 20) -> dict[str, Any]:
        article_ids = validate_article_ids(article_ids)
        top_k = bounded_top_k(top_k, default=20)
        if not str(query or "").strip():
            raise KnowledgeQueryError("invalid_arguments", "query is required")
        lexical = self.repository.search_profiles(query, article_ids, top_k * 2)
        vector = self.vector_index.query("K2", query, article_ids, top_k)
        results: dict[str, KnowledgeResult] = {}
        for row in lexical:
            result = KnowledgeResult(
                layer="K2", article_id=str(row["article_id"]), result_id=str(row["profile_id"]),
                title=str(row.get("title") or ""), text=f"{row.get('summary') or ''}\n{row.get('topics') or ''}",
                scores={"vector": None, "bm25": float(row.get("rank") or 0)},
                source_ref={"article_id": row["article_id"], "profile_id": row["profile_id"]},
            )
            results[result.result_id] = result
        for row in vector:
            metadata = row.get("metadata") or {}
            article_id = str(metadata.get("article_id") or "")
            if article_ids is not None and article_id not in article_ids:
                continue
            result_id = str(metadata.get("result_id") or row.get("id"))
            result = results.get(result_id) or KnowledgeResult(layer="K2", article_id=article_id, result_id=result_id, title=str(metadata.get("title") or ""), text=str(row.get("text") or ""), source_ref={"article_id": article_id, "profile_id": result_id})
            result.scores["vector"] = 1.0 - float(row.get("distance") or 0)
            results[result_id] = result
        ordered = sorted(results.values(), key=lambda item: self._score(item), reverse=True)
        return result_envelope("knowledge:profile_search", ordered[:top_k])

    def semantic_search(self, *, query: str, article_ids: list[str] | None = None, node_types: list[str] | None = None, relation_types: list[str] | None = None, hops: int = 1, top_k: int = 20) -> dict[str, Any]:
        article_ids = validate_article_ids(article_ids)
        top_k = bounded_top_k(top_k, default=20)
        if not str(query or "").strip():
            raise KnowledgeQueryError("invalid_arguments", "query is required")
        if int(hops) < 0 or int(hops) > 2:
            raise KnowledgeQueryError("invalid_arguments", "hops must be between 0 and 2")
        graph = self.graph.search(query, article_ids=article_ids, relation_types=relation_types, limit=top_k)
        allowed_types = set(node_types or [])
        results = []
        for row in graph["terms"]:
            if allowed_types and str(row.get("term_type")) not in allowed_types:
                continue
            results.append(KnowledgeResult(
                layer="K3", article_id=str(row.get("article_id") or ""), result_id=str(row.get("term_id") or ""),
                title=str(row.get("name") or ""), text=str(row.get("description") or row.get("name") or ""),
                scores={"vector": None, "bm25": float(row.get("rank") or 0), "graph": 1.0},
                source_ref={"article_id": row.get("article_id"), "term_id": row.get("term_id")},
                metadata={"node_type": row.get("term_type"), "aliases": row.get("aliases")},
            ))
        for row in graph["relations"]:
            results.append(KnowledgeResult(
                layer="K3", article_id=str(row["article_id"]), result_id=str(row["relation_id"]),
                title=f"{row['source_name']} - {row['target_name']}",
                text=f"{row['source_name']} {row['relation_type']} {row['target_name']}",
                scores={"vector": None, "bm25": None, "graph": float(row.get("weight") or 1.0)},
                source_ref={"article_id": row["article_id"], "evidence_id": row.get("evidence_id"), "relation_id": row["relation_id"]},
                metadata={"relation_type": row["relation_type"]},
            ))
        return result_envelope("knowledge:semantic_search", results[:top_k])

    def _matches_location(self, item: KnowledgeResult, location: dict[str, Any] | None) -> bool:
        if not location:
            return True
        page = item.location.get("page_number")
        if location.get("page_from") is not None and (page is None or page < int(location["page_from"])):
            return False
        if location.get("page_to") is not None and (page is None or page > int(location["page_to"])):
            return False
        section = location.get("section_path")
        return not section or str(section).lower() in str(item.location.get("section_path") or "").lower()

    def _score(self, item: KnowledgeResult) -> float:
        return sum(value or 0 for value in item.scores.values())
