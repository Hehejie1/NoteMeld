from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class WikiSearch:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.sources_dir = self.base_dir / "sources"
        self.entities_dir = self.base_dir / "entities"
        self.concepts_dir = self.base_dir / "concepts"
        self.contributions_dir = self.base_dir / "contributions"

    def search(
        self,
        query: str,
        limit: int = 5,
        intent: Any | None = None,
        linked_task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        tokens = self._tokens(query)
        if not tokens:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        scored.extend(
            (item.get("score", 0), item)
            for item in self._search_contributions(tokens, intent=intent, linked_task_id=linked_task_id)
        )
        for page_type, directory in (
            ("source", self.sources_dir),
            ("entity", self.entities_dir),
            ("concept", self.concepts_dir),
        ):
            if not directory.exists():
                continue
            for page_path in directory.glob("*.md"):
                page_id = page_path.stem
                contribution = self._read_contribution(page_id) if page_type == "source" else {}
                markdown = page_path.read_text(encoding="utf-8")
                title = contribution.get("title") or self._title_from_markdown(markdown) or page_id
                haystack = self._haystack(title, markdown, contribution)
                score = sum(haystack.count(token) for token in tokens)
                if score <= 0:
                    continue
                scored.append(
                    (
                        float(score),
                        {
                            "id": f"wiki-{page_type}-{page_id}",
                            "type": f"wiki_{page_type}" if page_type != "source" else "wiki_claim",
                            "text": self._snippet(markdown, contribution),
                            "snippet": self._snippet(markdown, contribution),
                            "source_type": "wiki",
                            "title": title,
                            "page_id": page_id,
                            "page_type": page_type,
                            "score": float(score),
                            "metadata": {
                                "wiki_type": page_type,
                                "page_id": page_id,
                            },
                        },
                    )
                )

        scored.sort(key=lambda item: (-item[0], item[1]["title"]))
        return [item for _, item in scored[:limit]]

    def _read_contribution(self, page_id: str) -> dict[str, Any]:
        contribution_path = self.contributions_dir / f"{page_id}.json"
        if not contribution_path.exists():
            return {}
        try:
            return json.loads(contribution_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _search_contributions(
        self,
        tokens: list[str],
        intent: Any | None = None,
        linked_task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.contributions_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        for path in self.contributions_dir.glob("*.json"):
            try:
                packet = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            source_id = str(packet.get("source_id") or packet.get("task_id") or path.stem)
            current_bonus = 2.0 if linked_task_id and linked_task_id == source_id else 0.0
            results.extend(self._score_concepts(packet, tokens, source_id, current_bonus))
            results.extend(self._score_entities(packet, tokens, source_id, current_bonus))
            results.extend(self._score_claims(packet, tokens, source_id, current_bonus))
            results.extend(self._score_evidence(packet, tokens, source_id, current_bonus))
            results.extend(self._score_relations(packet, tokens, source_id, current_bonus))
        return results

    def _score_text(self, text: str, tokens: list[str]) -> float:
        haystack = text.lower()
        return float(sum(haystack.count(token) for token in tokens))

    def _source_result(
        self,
        source_type: str,
        title: str,
        snippet: str,
        score: float,
        source_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": f"{source_type}-{source_id}-{abs(hash(title + snippet))}",
            "type": source_type,
            "source_type": source_type,
            "title": title,
            "snippet": snippet[:800],
            "text": snippet[:800],
            "score": score,
            "metadata": {
                **metadata,
                "source_id": source_id,
            },
        }

    def _score_concepts(
        self,
        packet: dict[str, Any],
        tokens: list[str],
        source_id: str,
        current_bonus: float,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for concept in packet.get("concepts", []) or []:
            name = str(concept.get("name") or "").strip()
            description = str(concept.get("description") or "").strip()
            score = self._score_text(f"{name}\n{description}", tokens)
            if score <= 0:
                continue
            results.append(self._source_result(
                "wiki_concept",
                name or "Wiki 概念",
                description or name,
                score + current_bonus + 2.0,
                source_id,
                {"wiki_type": "concept", "name": name},
            ))
        return results

    def _score_entities(
        self,
        packet: dict[str, Any],
        tokens: list[str],
        source_id: str,
        current_bonus: float,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for entity in packet.get("entities", []) or []:
            name = str(entity.get("name") or "").strip()
            description = str(entity.get("description") or "").strip()
            score = self._score_text(f"{name}\n{description}", tokens)
            if score <= 0:
                continue
            results.append(self._source_result(
                "wiki_entity",
                name or "Wiki 实体",
                description or name,
                score + current_bonus + 2.0,
                source_id,
                {"wiki_type": "entity", "name": name},
            ))
        return results

    def _score_claims(
        self,
        packet: dict[str, Any],
        tokens: list[str],
        source_id: str,
        current_bonus: float,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for claim in packet.get("claims", []) or []:
            text = str(claim.get("claim") or "").strip()
            target = str(claim.get("target_name") or "").strip()
            score = self._score_text(f"{target}\n{text}", tokens)
            if score <= 0:
                continue
            results.append(self._source_result(
                "wiki_claim",
                target or "Wiki 观点",
                text,
                score + current_bonus + 1.5,
                source_id,
                {
                    "wiki_type": "claim",
                    "target_name": target,
                    "evidence_ids": claim.get("evidence_ids", []),
                },
            ))
        return results

    def _score_evidence(
        self,
        packet: dict[str, Any],
        tokens: list[str],
        source_id: str,
        current_bonus: float,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        linked_evidence_ids: set[str] = set()
        for claim in packet.get("claims", []) or []:
            claim_text = str(claim.get("claim") or "")
            target = str(claim.get("target_name") or "")
            if self._score_text(f"{target}\n{claim_text}", tokens) > 0:
                linked_evidence_ids.update(str(item) for item in claim.get("evidence_ids", []) or [])
        for evidence in packet.get("evidence", []) or []:
            text = str(evidence.get("text") or "").strip()
            evidence_id = str(evidence.get("evidence_id") or "")
            score = self._score_text(text, tokens)
            if evidence_id in linked_evidence_ids:
                score = max(score, 1.0)
            if score <= 0:
                continue
            results.append(self._source_result(
                "wiki_evidence",
                evidence_id or "Wiki 证据",
                text,
                score + current_bonus + 1.0,
                source_id,
                {"wiki_type": "evidence", "evidence_id": evidence_id},
            ))
        return results

    def _score_relations(
        self,
        packet: dict[str, Any],
        tokens: list[str],
        source_id: str,
        current_bonus: float,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for relation in packet.get("relations", []) or []:
            source = str(relation.get("source") or "").strip()
            target = str(relation.get("target") or "").strip()
            relation_type = str(relation.get("relation_type") or "").strip()
            text = f"{source} -> {relation_type} -> {target}"
            score = self._score_text(text, tokens)
            if score <= 0:
                continue
            results.append(self._source_result(
                "wiki_relation",
                f"{source} - {target}".strip(" -") or "Wiki 关系",
                text,
                score + current_bonus + 0.5,
                source_id,
                {
                    "wiki_type": "relation",
                    "source": source,
                    "target": target,
                    "relation_type": relation_type,
                },
            ))
        return results

    def _tokens(self, query: str) -> list[str]:
        raw = query.lower()
        latin = re.findall(r"[a-z0-9_\-]{2,}", raw)
        cjk_terms = re.findall(r"[\u4e00-\u9fff]{2,}", raw)
        cjk: list[str] = []
        for term in cjk_terms:
            cjk.append(term)
            for size in (2, 3, 4):
                cjk.extend(term[i:i + size] for i in range(0, max(len(term) - size + 1, 0)))
        return list(dict.fromkeys(latin + cjk))

    def _haystack(self, title: str, markdown: str, packet: dict[str, Any]) -> str:
        parts = [title, packet.get("summary", ""), markdown[:1200]]
        parts.extend(str(topic) for topic in packet.get("topics", []))
        for entity in packet.get("entities", []):
            parts.append(str(entity.get("name", "")))
        for concept in packet.get("concepts", []):
            parts.append(str(concept.get("name", "")))
        return "\n".join(parts).lower()

    def _snippet(self, markdown: str, packet: dict[str, Any]) -> str:
        summary = str(packet.get("summary") or "").strip()
        body = re.sub(r"\s+", " ", markdown).strip()
        text = f"{summary}\n{body}" if summary else body
        return text[:800]

    def _title_from_markdown(self, markdown: str) -> str:
        for line in markdown.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return ""
