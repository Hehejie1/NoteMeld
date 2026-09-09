from __future__ import annotations

import json
import re
from typing import Any, Iterable

from sqlalchemy import delete, select, text

from app.db.engine import SessionLocal, get_engine
from app.db.knowledge_schema import ensure_knowledge_schema
from app.db.models.knowledge import (
    KnowledgeArticle,
    KnowledgeChunk,
    KnowledgeProfile,
    KnowledgeRelation,
    KnowledgeTerm,
    KnowledgeTermOccurrence,
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _normalized_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


class KnowledgeRepository:
    def __init__(self, *, session_factory=None, engine=None):
        self.engine = engine or get_engine()
        self.session_factory = session_factory or SessionLocal
        ensure_knowledge_schema(self.engine)

    def replace_article(
        self,
        *,
        article: dict[str, Any],
        chunks: Iterable[dict[str, Any]],
        profile: dict[str, Any],
        terms: Iterable[dict[str, Any]],
        relations: Iterable[dict[str, Any]],
        index_version: str,
    ) -> None:
        article_id = str(article["article_id"])
        chunks = [dict(item) for item in chunks]
        terms = [dict(item) for item in terms]
        relations = [dict(item) for item in relations]
        with self.session_factory.begin() as session:
            existing_term_ids = {
                row.normalized_name: row.term_id
                for row in session.execute(select(KnowledgeTerm)).scalars().all()
            }
            session.execute(delete(KnowledgeTermOccurrence).where(KnowledgeTermOccurrence.article_id == article_id))
            session.execute(delete(KnowledgeRelation).where(KnowledgeRelation.article_id == article_id))
            session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.article_id == article_id))
            session.execute(delete(KnowledgeProfile).where(KnowledgeProfile.article_id == article_id))
            current = session.get(KnowledgeArticle, article_id)
            if current is None:
                current = KnowledgeArticle(article_id=article_id)
                session.add(current)
            current.title = str(article.get("title") or "")
            current.source_type = str(article.get("source_type") or "")
            current.source_url = article.get("source_url")
            current.content = str(article.get("content") or "")
            current.status = str(article.get("status") or "active")
            current.metadata_json = _json(article.get("metadata") or {})
            current.index_version = index_version

            session.add(KnowledgeProfile(
                profile_id=f"{article_id}:profile",
                article_id=article_id,
                title=str(profile.get("title") or current.title),
                summary=str(profile.get("summary") or ""),
                topics_json=_json(profile.get("topics") or []),
                status=str(profile.get("status") or "complete"),
                index_version=index_version,
            ))
            session.flush()

            session.execute(text("DELETE FROM knowledge_chunk_fts WHERE article_id = :article_id"), {"article_id": article_id})
            session.execute(text("DELETE FROM knowledge_profile_fts WHERE article_id = :article_id"), {"article_id": article_id})
            session.execute(text("DELETE FROM knowledge_term_fts WHERE article_id = :article_id"), {"article_id": article_id})

            for index, chunk in enumerate(chunks):
                chunk_id = str(chunk.get("chunk_id") or f"{article_id}:chunk:{index}")
                metadata = dict(chunk.get("metadata") or {})
                row = KnowledgeChunk(
                    chunk_id=chunk_id,
                    article_id=article_id,
                    content=str(chunk.get("content") or ""),
                    page_number=chunk.get("page_number"),
                    section_path=chunk.get("section_path"),
                    start_time=chunk.get("start_time"),
                    end_time=chunk.get("end_time"),
                    chunk_index=int(chunk.get("chunk_index", index)),
                    metadata_json=_json(metadata),
                    index_version=index_version,
                )
                session.add(row)
                session.flush()
                session.execute(text(
                    "INSERT INTO knowledge_chunk_fts(chunk_id, article_id, content, title, section_path) "
                    "VALUES (:chunk_id, :article_id, :content, :title, :section_path)"
                ), {
                    "chunk_id": chunk_id,
                    "article_id": article_id,
                    "content": row.content,
                    "title": current.title,
                    "section_path": row.section_path or "",
                })

            session.execute(text(
                "INSERT INTO knowledge_profile_fts(profile_id, article_id, title, summary, topics) "
                "VALUES (:profile_id, :article_id, :title, :summary, :topics)"
            ), {
                "profile_id": f"{article_id}:profile",
                "article_id": article_id,
                "title": current.title,
                "summary": str(profile.get("summary") or ""),
                "topics": " ".join(str(item) for item in profile.get("topics") or []),
            })

            term_ids: dict[str, str] = {}
            for index, term in enumerate(terms):
                name = str(term.get("name") or "").strip()
                normalized = _normalized_name(name)
                if not normalized:
                    continue
                term_id = existing_term_ids.get(normalized) or str(term.get("term_id") or f"term:{normalized}")
                existing = session.get(KnowledgeTerm, term_id)
                if existing is None:
                    existing = KnowledgeTerm(
                        term_id=term_id,
                        term_type=str(term.get("term_type") or "concept"),
                        name=name,
                        normalized_name=normalized,
                        aliases_json=_json(term.get("aliases") or []),
                        description=str(term.get("description") or ""),
                    )
                    session.add(existing)
                term_ids[normalized] = term_id
                existing_term_ids[normalized] = term_id
                session.flush()
                session.execute(text(
                    "INSERT INTO knowledge_term_fts(term_id, article_id, term_type, name, aliases, description, context) "
                    "VALUES (:term_id, :article_id, :term_type, :name, :aliases, :description, :context)"
                ), {
                    "term_id": term_id,
                    "article_id": article_id,
                    "term_type": existing.term_type,
                    "name": existing.name,
                    "aliases": existing.aliases_json,
                    "description": existing.description,
                    "context": str(term.get("context") or ""),
                })
                session.add(KnowledgeTermOccurrence(
                    occurrence_id=str(term.get("occurrence_id") or f"{article_id}:occurrence:{index}"),
                    term_id=term_id,
                    article_id=article_id,
                    evidence_id=term.get("evidence_id"),
                    context=str(term.get("context") or existing.description or existing.name),
                    index_version=index_version,
                ))

            for index, relation in enumerate(relations):
                source = _normalized_name(str(relation.get("source") or ""))
                target = _normalized_name(str(relation.get("target") or ""))
                if not source or not target:
                    continue
                source_id = term_ids.get(source) or existing_term_ids.get(source)
                target_id = term_ids.get(target) or existing_term_ids.get(target)
                if not source_id or not target_id:
                    continue
                session.add(KnowledgeRelation(
                    relation_id=str(relation.get("relation_id") or f"{article_id}:relation:{index}"),
                    source_term_id=source_id,
                    target_term_id=target_id,
                    article_id=article_id,
                    relation_type=str(relation.get("relation_type") or "related"),
                    evidence_id=relation.get("evidence_id"),
                    weight=float(relation.get("weight") or 1.0),
                    metadata_json=_json(relation.get("metadata") or {}),
                    index_version=index_version,
                ))

    def get_articles(self, article_ids: list[str] | None = None) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            query = select(KnowledgeArticle).where(KnowledgeArticle.deleted_at.is_(None), KnowledgeArticle.status == "active")
            if article_ids is not None:
                query = query.where(KnowledgeArticle.article_id.in_(article_ids))
            rows = session.execute(query.order_by(KnowledgeArticle.updated_at.desc())).scalars().all()
            return [self._article_dict(row) for row in rows]

    def search_chunks(self, query: str, article_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
        return self._search_fts("knowledge_chunk_fts", query, article_ids, limit, "chunk")

    def search_profiles(self, query: str, article_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
        return self._search_fts("knowledge_profile_fts", query, article_ids, limit, "profile")

    def search_terms(self, query: str, article_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
        return self._search_fts("knowledge_term_fts", query, article_ids, limit, "term")

    def search_relations(self, term_ids: list[str], article_ids: list[str] | None, relation_types: list[str] | None, limit: int) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            # SQLAlchemy cannot join the same mapped table twice without aliases;
            # use a bounded SQL query to keep the graph lookup explicit.
            sql = (
                "SELECT r.relation_id, r.article_id, r.relation_type, r.evidence_id, r.weight, "
                "s.name AS source_name, t.name AS target_name "
                "FROM knowledge_relations r "
                "JOIN knowledge_terms s ON s.term_id = r.source_term_id "
                "JOIN knowledge_terms t ON t.term_id = r.target_term_id "
                "WHERE (r.source_term_id IN ({ids}) OR r.target_term_id IN ({ids}))"
            ).format(ids=", ".join(f":term_{i}" for i in range(len(term_ids))))
            params: dict[str, Any] = {f"term_{i}": item for i, item in enumerate(term_ids)}
            if article_ids is not None:
                sql += " AND r.article_id IN (" + ", ".join(f":article_{i}" for i in range(len(article_ids))) + ")"
                params.update({f"article_{i}": item for i, item in enumerate(article_ids)})
            if relation_types:
                sql += " AND r.relation_type IN (" + ", ".join(f":relation_{i}" for i in range(len(relation_types))) + ")"
                params.update({f"relation_{i}": item for i, item in enumerate(relation_types)})
            sql += " ORDER BY r.weight DESC LIMIT :limit"
            params["limit"] = limit
            return [dict(row) for row in session.execute(text(sql), params).mappings().all()]

    def delete_article(self, article_id: str) -> None:
        with self.session_factory.begin() as session:
            session.execute(text("DELETE FROM knowledge_chunk_fts WHERE article_id = :article_id"), {"article_id": article_id})
            session.execute(text("DELETE FROM knowledge_profile_fts WHERE article_id = :article_id"), {"article_id": article_id})
            session.execute(text("DELETE FROM knowledge_term_fts WHERE article_id = :article_id"), {"article_id": article_id})
            session.execute(delete(KnowledgeRelation).where(KnowledgeRelation.article_id == article_id))
            session.execute(delete(KnowledgeTermOccurrence).where(KnowledgeTermOccurrence.article_id == article_id))
            session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.article_id == article_id))
            session.execute(delete(KnowledgeProfile).where(KnowledgeProfile.article_id == article_id))
            article = session.get(KnowledgeArticle, article_id)
            if article is not None:
                article.status = "deleted"
                article.deleted_at = func.now()

    def _search_fts(self, table: str, query: str, article_ids: list[str] | None, limit: int, kind: str) -> list[dict[str, Any]]:
        tokens = [item for item in re.findall(r"[\w\-]{2,}", str(query or "").lower()) if item]
        if not tokens:
            return []
        fts_query = " OR ".join(tokens)
        params: dict[str, Any] = {"query": fts_query, "limit": limit}
        article_clause = ""
        if article_ids is not None:
            article_clause = " AND article_id IN (" + ", ".join(f":article_{i}" for i in range(len(article_ids))) + ")"
            params.update({f"article_{i}": item for i, item in enumerate(article_ids)})
        columns = {
            "chunk": "chunk_id, article_id, content, title, section_path, bm25(knowledge_chunk_fts) AS rank",
            "profile": "profile_id, article_id, title, summary, topics, bm25(knowledge_profile_fts) AS rank",
            "term": "term_id, article_id, term_type, name, aliases, description, context, bm25(knowledge_term_fts) AS rank",
        }[kind]
        sql = f"SELECT {columns} FROM {table} WHERE {table} MATCH :query{article_clause} ORDER BY rank LIMIT :limit"
        with self.session_factory() as session:
            try:
                rows = session.execute(text(sql), params).mappings().all()
            except Exception:
                # FTS5 tokenization differs for CJK and punctuation. The fallback
                # still searches the indexed table, never the 100k source files.
                like = "%" + str(query).strip() + "%"
                params = {"like": like, "limit": limit}
                if article_ids is not None:
                    params.update({f"article_{i}": item for i, item in enumerate(article_ids)})
                search_columns = {
                    "chunk": "content",
                    "profile": "title OR summary OR topics",
                    "term": "name OR aliases OR description OR context",
                }[kind]
                rows = session.execute(text(
                    f"SELECT {columns.replace('bm25(knowledge_chunk_fts) AS rank', '0 AS rank').replace('bm25(knowledge_profile_fts) AS rank', '0 AS rank').replace('bm25(knowledge_term_fts) AS rank', '0 AS rank')} "
                    f"FROM {table} WHERE ({' LIKE :like OR '.join(search_columns.split(' OR '))} LIKE :like){article_clause} LIMIT :limit"
                ), params).mappings().all()
        return [dict(row) for row in rows]

    def _article_dict(self, row: KnowledgeArticle) -> dict[str, Any]:
        return {
            "article_id": row.article_id,
            "title": row.title,
            "source_type": row.source_type,
            "source_url": row.source_url,
            "content": row.content,
            "status": row.status,
            "metadata": json.loads(row.metadata_json or "{}"),
            "index_version": row.index_version,
        }
