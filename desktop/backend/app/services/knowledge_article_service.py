from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from app.models.knowledge_retrieval import INDEX_VERSION
from app.services.knowledge_evidence_index import KnowledgeEvidenceIndex
from app.services.knowledge_profile_index import KnowledgeProfileIndex
from app.services.knowledge_repository import KnowledgeRepository


class KnowledgeArticleService:
    def __init__(self, *, repository: KnowledgeRepository | None = None, vector_index: KnowledgeEvidenceIndex | None = None):
        self.repository = repository or KnowledgeRepository()
        self.vector_index = vector_index or KnowledgeEvidenceIndex()
        self.profile_index = KnowledgeProfileIndex(self.vector_index)

    def index_article(
        self,
        *,
        article_id: str,
        title: str,
        content: str,
        source_type: str = "",
        source_url: str | None = None,
        profile: dict[str, Any] | None = None,
        chunks: list[dict[str, Any]] | None = None,
        terms: list[dict[str, Any]] | None = None,
        relations: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        profile = profile or {"title": title, "summary": self._fallback_summary(content), "topics": [], "status": "partial"}
        chunks = chunks or self._markdown_chunks(article_id, content)
        terms = terms or []
        relations = relations or []
        article = {
            "article_id": article_id,
            "title": title,
            "source_type": source_type,
            "source_url": source_url,
            "content": content,
            "metadata": metadata or {},
        }
        self.repository.replace_article(
            article=article,
            chunks=chunks,
            profile=profile,
            terms=terms,
            relations=relations,
            index_version=INDEX_VERSION,
        )
        self.vector_index.upsert("K1", [self._chunk_vector_record(article_id, title, item) for item in chunks if str(item.get("content") or "").strip()])
        self.profile_index.upsert([{
            "id": f"{article_id}:profile",
            "article_id": article_id,
            "title": title,
            "text": f"{title}\n{profile.get('summary') or ''}\n{' '.join(str(item) for item in profile.get('topics') or [])}",
        }])
        self.vector_index.upsert("K3", [
            {
                "id": str(item.get("occurrence_id") or f"{article_id}:term:{index}"),
                "article_id": article_id,
                "term_type": item.get("term_type"),
                "text": f"{item.get('name') or ''}\n{item.get('description') or ''}\n{item.get('context') or ''}",
            }
            for index, item in enumerate(terms)
        ])
        return {"article_id": article_id, "index_version": INDEX_VERSION, "chunk_count": len(chunks), "term_count": len(terms)}

    def index_from_note_file(self, article_id: str, *, note_path: str | Path | None = None, contribution_path: str | Path | None = None) -> dict[str, Any]:
        from app.utils.storage_paths import note_output_dir

        note_path = Path(note_path or note_output_dir() / f"{article_id}.json")
        if not note_path.exists():
            raise FileNotFoundError(f"note source missing: {article_id}")
        note = json.loads(note_path.read_text(encoding="utf-8"))
        contribution = {}
        if contribution_path is None:
            contribution_path = note_output_dir() / "wiki" / "contributions" / f"{article_id}.json"
        contribution_path = Path(contribution_path)
        if contribution_path.exists():
            try:
                contribution = json.loads(contribution_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                contribution = {}
        markdown = str(note.get("markdown") or note.get("content") or "")
        title = str(note.get("title") or contribution.get("title") or article_id)
        terms = self._terms_from_contribution(article_id, contribution)
        relations = self._relations_from_contribution(article_id, contribution)
        profile = {
            "title": title,
            "summary": str(contribution.get("summary") or self._fallback_summary(markdown)),
            "topics": contribution.get("topics") or [],
            "status": "complete" if contribution.get("summary") else "partial",
        }
        return self.index_article(
            article_id=article_id,
            title=title,
            content=markdown,
            source_type=str(contribution.get("source_type") or note.get("source_type") or note.get("platform") or ""),
            source_url=note.get("source_url") or note.get("url"),
            profile=profile,
            chunks=self._chunks_from_contribution_or_markdown(article_id, markdown, contribution),
            terms=terms,
            relations=relations,
            metadata={"task_id": article_id},
        )

    def index_from_packet(self, packet: Any, markdown: str) -> dict[str, Any]:
        contribution = asdict(packet) if is_dataclass(packet) else dict(packet or {})
        article_id = str(contribution.get("source_id") or contribution.get("packet_id") or "").strip()
        if not article_id:
            raise ValueError("knowledge packet source_id is required")
        title = str(contribution.get("title") or article_id)
        return self.index_article(
            article_id=article_id,
            title=title,
            content=markdown,
            source_type=str(contribution.get("source_type") or ""),
            profile={
                "title": title,
                "summary": str(contribution.get("summary") or self._fallback_summary(markdown)),
                "topics": contribution.get("topics") or [],
                "status": "complete" if contribution.get("summary") else "partial",
            },
            chunks=self._chunks_from_contribution_or_markdown(article_id, markdown, contribution),
            terms=self._terms_from_contribution(article_id, contribution),
            relations=self._relations_from_contribution(article_id, contribution),
            metadata={"packet_id": contribution.get("packet_id")},
        )

    def _chunks_from_contribution_or_markdown(self, article_id: str, markdown: str, contribution: dict[str, Any]) -> list[dict[str, Any]]:
        evidence = contribution.get("evidence") or []
        if evidence:
            chunks = []
            for index, item in enumerate(evidence):
                text = str(item.get("text") or "").strip()
                if text:
                    chunks.append({
                        "chunk_id": str(item.get("evidence_id") or f"{article_id}:chunk:{index}"),
                        "content": text,
                        "chunk_index": index,
                        "page_number": item.get("page_number"),
                        "start_time": item.get("timestamp"),
                        "metadata": {"evidence_id": item.get("evidence_id")},
                    })
            if chunks:
                return chunks
        return self._markdown_chunks(article_id, markdown)

    def _markdown_chunks(self, article_id: str, markdown: str) -> list[dict[str, Any]]:
        sections = re.split(r"(?=^#{1,3}\s)", markdown, flags=re.MULTILINE)
        chunks = []
        for index, section in enumerate(sections):
            text = section.strip()
            if not text:
                continue
            heading = re.match(r"^#{1,3}\s+(.+)", text)
            chunks.append({
                "chunk_id": f"{article_id}:chunk:{index}",
                "content": text[:12000],
                "chunk_index": index,
                "section_path": heading.group(1).strip() if heading else None,
                "metadata": {"source_type": "markdown"},
            })
        return chunks or [{"chunk_id": f"{article_id}:chunk:0", "content": markdown[:12000], "chunk_index": 0, "metadata": {}}]

    def _terms_from_contribution(self, article_id: str, contribution: dict[str, Any]) -> list[dict[str, Any]]:
        terms = []
        for term_type, items in (("entity", contribution.get("entities") or []), ("concept", contribution.get("concepts") or [])):
            for item in items:
                if not item.get("name"):
                    continue
                evidence = item.get("evidence") or []
                terms.append({
                    "term_id": f"{term_type}:{str(item['name']).strip().lower()}",
                    "term_type": term_type,
                    "name": item.get("name"),
                    "aliases": item.get("aliases") or [],
                    "description": item.get("description") or "",
                    "context": str((evidence[0] if evidence else {}).get("text") or ""),
                    "evidence_id": (evidence[0] if evidence else {}).get("evidence_id"),
                    "occurrence_id": f"{article_id}:{term_type}:{str(item['name']).strip().lower()}",
                })
        return terms

    def _relations_from_contribution(self, article_id: str, contribution: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "relation_id": f"{article_id}:relation:{index}",
                "source": item.get("source"),
                "target": item.get("target"),
                "relation_type": item.get("relation_type") or "related",
                "weight": item.get("weight") or 1.0,
            }
            for index, item in enumerate(contribution.get("relations") or [])
        ]

    def _chunk_vector_record(self, article_id: str, title: str, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item.get("chunk_id")),
            "article_id": article_id,
            "title": title,
            "text": str(item.get("content") or ""),
            "page_number": item.get("page_number"),
            "section_path": item.get("section_path"),
        }

    def _fallback_summary(self, content: str) -> str:
        return re.sub(r"\s+", " ", content).strip()[:600]
