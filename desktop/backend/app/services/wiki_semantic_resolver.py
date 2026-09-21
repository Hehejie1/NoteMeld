from __future__ import annotations

from typing import Any, Optional

from app.models.knowledge_packet import KnowledgeConcept, KnowledgeEntity


class WikiSemanticResolver:
    """Resolve wiki terms against the global wiki_terms registry."""

    def __init__(
        self,
        *,
        merge_threshold: float = 0.12,
        related_threshold: float = 0.35,
        n_results: int = 10,
    ):
        self.merge_threshold = merge_threshold
        self.related_threshold = related_threshold
        self.n_results = n_results

    def resolve_concept(self, concept: KnowledgeConcept, *, vector_store: Any) -> dict:
        return self._resolve_term(concept, term_type="concept", vector_store=vector_store)

    def resolve_entity(self, entity: KnowledgeEntity, *, vector_store: Any) -> dict:
        return self._resolve_term(entity, term_type="entity", vector_store=vector_store)

    def persist_concept(
        self,
        concept: KnowledgeConcept,
        *,
        vector_store: Any,
        resolution: Optional[dict] = None,
    ) -> Optional[dict]:
        return self._persist_term(
            concept,
            term_type="concept",
            vector_store=vector_store,
            resolution=resolution,
        )

    def persist_entity(
        self,
        entity: KnowledgeEntity,
        *,
        vector_store: Any,
        resolution: Optional[dict] = None,
    ) -> Optional[dict]:
        return self._persist_term(
            entity,
            term_type="entity",
            vector_store=vector_store,
            resolution=resolution,
        )

    def _resolve_term(self, term: Any, *, term_type: str, vector_store: Any) -> dict:
        term_name = getattr(term, "name", "")
        if vector_store is None or not term_name.strip():
            return self._none_result(term_name)

        candidates = self._collect_candidates(term, term_type=term_type, vector_store=vector_store)
        if not candidates:
            return self._none_result(term_name)

        exact_match = self._match_exact(term, candidates)
        if exact_match:
            return self._build_result(
                action="merge",
                canonical_name=exact_match.get("name") or term_name,
                matched_aliases=[],
                match_type="exact",
                candidate=exact_match,
            )

        alias_match, matched_aliases = self._match_alias(term, candidates)
        if alias_match:
            return self._build_result(
                action="merge",
                canonical_name=self._choose_alias_canonical_name(term, alias_match),
                matched_aliases=matched_aliases,
                match_type="alias",
                candidate=alias_match,
            )

        best_candidate = self._best_vector_candidate(candidates)
        if not best_candidate:
            return self._none_result(term_name)

        distance = self._distance(best_candidate)
        if distance is None:
            return self._none_result(term_name)
        if distance <= self.merge_threshold:
            return self._build_result(
                action="merge",
                canonical_name=best_candidate.get("name") or term_name,
                matched_aliases=[],
                match_type="vector",
                candidate=best_candidate,
            )
        if distance <= self.related_threshold:
            canonical_name = best_candidate.get("name") or term_name
            return self._build_result(
                action="semantic_related",
                canonical_name=canonical_name,
                matched_aliases=[],
                match_type="vector",
                candidate=best_candidate,
                semantic_related=[canonical_name],
            )
        return self._none_result(term_name)

    def _persist_term(
        self,
        term: Any,
        *,
        term_type: str,
        vector_store: Any,
        resolution: Optional[dict] = None,
    ) -> Optional[dict]:
        term_name = getattr(term, "name", "")
        if vector_store is None or not term_name.strip():
            return None

        current = self._fetch_existing_term(term_name, term_type=term_type, vector_store=vector_store)
        existing_source_count = 0
        if current:
            existing_source_count = int((current.get("metadata") or {}).get("source_count") or 0)

        term_id = f"{term_type}:{self._safe_id(term_name)}"
        prior_term_id = (resolution or {}).get("term_id")
        metadata = {
            "canonical_name": (resolution or {}).get("canonical_name") or term_name,
            "matched_aliases": list((resolution or {}).get("matched_aliases") or []),
            "semantic_related": list(
                (resolution or {}).get("semantic_related")
                or getattr(term, "semantic_related", [])
            ),
            "source_count": max(existing_source_count, 0) + 1,
        }
        record = vector_store.upsert_wiki_term(
            term_id=term_id,
            term_type=term_type,
            name=term_name,
            aliases=self._dedupe([*getattr(term, "aliases", [])]),
            description=getattr(term, "description", "") or "",
            metadata=metadata,
        )
        if (
            (resolution or {}).get("action") == "merge"
            and prior_term_id
            and prior_term_id != term_id
        ):
            vector_store.delete_wiki_term(prior_term_id)
        return record

    def _collect_candidates(self, term: Any, *, term_type: str, vector_store: Any) -> list[dict]:
        candidates_by_id: dict[str, dict] = {}
        for query_text in self._query_texts(term):
            if not query_text:
                continue
            for candidate in vector_store.query_wiki_terms(
                term_type=term_type,
                query_text=query_text,
                n_results=self.n_results,
            ):
                term_id = candidate.get("term_id") or candidate.get("name")
                if not term_id:
                    continue
                previous = candidates_by_id.get(term_id)
                if previous is None or self._distance(candidate) < self._distance(previous):
                    candidates_by_id[term_id] = candidate
        return sorted(
            candidates_by_id.values(),
            key=lambda item: (
                self._distance(item),
                self._normalize_text(item.get("name", "")),
            ),
        )

    def _query_texts(self, term: Any) -> list[str]:
        values = [getattr(term, "name", ""), *getattr(term, "aliases", [])]
        if getattr(term, "description", ""):
            values.append(getattr(term, "description", ""))
        return self._dedupe([value for value in values if str(value).strip()])

    def _match_exact(self, term: Any, candidates: list[dict]) -> Optional[dict]:
        normalized_name = self._normalize_text(getattr(term, "name", ""))
        for candidate in candidates:
            if self._normalize_text(candidate.get("name", "")) == normalized_name:
                return candidate
        return None

    def _match_alias(self, term: Any, candidates: list[dict]) -> tuple[Optional[dict], list[str]]:
        input_name = self._normalize_text(getattr(term, "name", ""))
        input_aliases = {
            self._normalize_text(alias)
            for alias in getattr(term, "aliases", [])
            if str(alias).strip()
        }
        for candidate in candidates:
            candidate_name = self._normalize_text(candidate.get("name", ""))
            candidate_aliases = {
                self._normalize_text(alias)
                for alias in (candidate.get("aliases") or [])
                if str(alias).strip()
            }
            matched = []
            if input_name and input_name in candidate_aliases:
                matched.append(getattr(term, "name", ""))
            if candidate_name and candidate_name in input_aliases:
                matched.append(candidate.get("name", ""))
            for alias in getattr(term, "aliases", []):
                if self._normalize_text(alias) in candidate_aliases:
                    matched.append(alias)
            if matched:
                return candidate, self._dedupe(matched)
        return None, []

    def _best_vector_candidate(self, candidates: list[dict]) -> Optional[dict]:
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda item: (
                self._distance(item),
                self._normalize_text(item.get("name", "")),
            ),
        )

    def _fetch_existing_term(self, name: str, *, term_type: str, vector_store: Any) -> Optional[dict]:
        results = vector_store.query_wiki_terms(term_type=term_type, query_text=name, n_results=5)
        normalized_name = self._normalize_text(name)
        for candidate in results:
            if self._normalize_text(candidate.get("name", "")) == normalized_name:
                return candidate
        return None

    def _choose_alias_canonical_name(self, term: Any, candidate: dict) -> str:
        options = [
            candidate.get("name", ""),
            getattr(term, "name", ""),
            *(candidate.get("aliases") or []),
            *getattr(term, "aliases", []),
        ]
        return max(
            self._dedupe(options),
            key=lambda value: (len(value.strip()), value.strip().lower()),
            default=candidate.get("name") or getattr(term, "name", ""),
        )

    def _build_result(
        self,
        *,
        action: str,
        canonical_name: str,
        matched_aliases: list[str],
        match_type: str,
        candidate: dict,
        semantic_related: Optional[list[str]] = None,
    ) -> dict:
        return {
            "action": action,
            "canonical_name": canonical_name,
            "matched_aliases": self._dedupe(matched_aliases),
            "semantic_related": self._dedupe(semantic_related or []),
            "match_type": match_type,
            "distance": candidate.get("distance"),
            "term_id": candidate.get("term_id"),
            "metadata": dict(candidate.get("metadata") or {}),
        }

    def _none_result(self, concept_name: str) -> dict:
        return {
            "action": "none",
            "canonical_name": concept_name,
            "matched_aliases": [],
            "semantic_related": [],
            "match_type": None,
            "distance": None,
            "term_id": None,
            "metadata": {},
        }

    def _distance(self, item: Optional[dict]) -> float:
        if not item:
            return float("inf")
        distance = item.get("distance")
        if distance is None:
            return float("inf")
        return float(distance)

    def _normalize_text(self, value: str) -> str:
        return " ".join((value or "").strip().lower().split())

    def _safe_id(self, value: str) -> str:
        return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)

    def _dedupe(self, values: list[str]) -> list[str]:
        result = []
        seen = set()
        for value in values:
            text = str(value or "").strip()
            key = self._normalize_text(text)
            if not text or key in seen:
                continue
            seen.add(key)
            result.append(text)
        return result
