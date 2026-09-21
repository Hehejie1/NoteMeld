import json
import threading
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional, Union

from app.models.knowledge_packet import (
    GraphCluster,
    GraphEdge,
    GraphNode,
    GraphPayload,
    KnowledgeClaim,
    KnowledgeConcept,
    KnowledgeEntity,
    KnowledgeEvidence,
    KnowledgePacket,
    KnowledgeRelation,
)
from app.services.wiki_page_merger import WikiPageMerger
from app.services.wiki_graph_analyzer import WikiGraphAnalyzer

_WIKI_WRITE_LOCK = threading.RLock()


class WikiStore:
    def __init__(
        self,
        base_dir: Union[str, Path] = "wiki",
        *,
        vector_store: Any = None,
        semantic_resolver: Any = None,
    ):
        self.base_dir = Path(base_dir)
        self.sources_dir = self.base_dir / "sources"
        self.entities_dir = self.base_dir / "entities"
        self.concepts_dir = self.base_dir / "concepts"
        self.contributions_dir = self.base_dir / "contributions"
        self.vector_store = vector_store
        self.semantic_resolver = semantic_resolver

    def read_graph(self) -> dict:
        graph_path = self.base_dir / "graph.json"
        if not graph_path.exists():
            return {"nodes": [], "edges": [], "clusters": []}
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        if self._needs_community_repair(graph):
            WikiGraphAnalyzer(self.base_dir).compute_and_persist_communities()
            graph = json.loads(graph_path.read_text(encoding="utf-8"))
        return graph

    def read_community_index(self) -> dict:
        return WikiGraphAnalyzer(self.base_dir).read_index()

    def list_pages(self) -> list[dict]:
        if not self.sources_dir.exists():
            return []
        pages = []
        for page_path in sorted(self.sources_dir.glob("*.md")):
            page_id = page_path.stem
            contribution = self._read_contribution(page_id)
            pages.append(
                {
                    "id": page_id,
                    "title": self._page_title(page_id, page_path, contribution),
                    "source_type": contribution.get("source_type") if contribution else None,
                    "summary": contribution.get("summary") if contribution else "",
                    "topics": contribution.get("topics", []) if contribution else [],
                }
            )
        return pages

    def get_page(self, page_id: str) -> Union[dict, None]:
        safe_id = self._safe_id(page_id)
        source_page_path = self.sources_dir / f"{safe_id}.md"
        if not source_page_path.exists():
            return None

        contribution = self._read_contribution(safe_id)
        return {
            "id": safe_id,
            "title": self._page_title(safe_id, source_page_path, contribution),
            "markdown": source_page_path.read_text(encoding="utf-8"),
            "contribution": contribution,
        }

    def get_article(self, source_id: str) -> Union[dict, None]:
        safe_id = self._safe_id(source_id)
        contribution = self._read_contribution(safe_id)
        if contribution is None:
            return None

        source_page_path = self.sources_dir / f"{safe_id}.md"
        markdown = source_page_path.read_text(encoding="utf-8") if source_page_path.exists() else ""
        return {
            "id": safe_id,
            "title": contribution.get("title") or safe_id,
            "source_type": contribution.get("source_type", ""),
            "summary": contribution.get("summary", ""),
            "topics": contribution.get("topics", []),
            "entities": contribution.get("entities", []),
            "concepts": contribution.get("concepts", []),
            "claims": contribution.get("claims", []),
            "evidence": contribution.get("evidence", []),
            "relations": contribution.get("relations", []),
            "markdown": markdown,
            "contribution": contribution,
        }

    def list_file_pages(self) -> list[dict]:
        pages = []
        for page_type, directory in (
            ("source", self.sources_dir),
            ("entity", self.entities_dir),
            ("concept", self.concepts_dir),
        ):
            if not directory.exists():
                continue
            for page_path in sorted(directory.glob("*.md")):
                pages.append(
                    {
                        "type": page_type,
                        "id": page_path.stem,
                        "title": self._markdown_title(page_path, page_path.stem),
                    }
                )
        return pages

    def get_file_page(self, page_type: str, page_id: str) -> Union[dict, None]:
        directories = {
            "source": self.sources_dir,
            "entity": self.entities_dir,
            "concept": self.concepts_dir,
        }
        directory = directories.get(page_type)
        if directory is None:
            return None

        safe_id = self._safe_id(page_id)
        page_path = directory / f"{safe_id}.md"
        if not page_path.exists():
            return None

        markdown = page_path.read_text(encoding="utf-8")
        return {
            "type": page_type,
            "id": safe_id,
            "title": self._markdown_title(page_path, safe_id),
            "markdown": markdown,
        }

    def persist(self, packet: KnowledgePacket, markdown: str, gpt=None) -> dict:
        with _WIKI_WRITE_LOCK:
            normalized_packet = self._normalize_packet_semantics(packet)
            safe_id = self._safe_id(normalized_packet.source_id)
            source_path = self.sources_dir / f"{safe_id}.md"
            contribution_path = self.contributions_dir / f"{safe_id}.json"
            graph_path = self.base_dir / "graph.json"
            previous_contribution = self._read_contribution(safe_id) or {}
            next_contribution = self._render_contribution(normalized_packet)
            touched_entity_ids = self._collect_entity_ids(previous_contribution) | self._collect_entity_ids(next_contribution)
            touched_concept_ids = self._collect_concept_ids(previous_contribution) | self._collect_concept_ids(next_contribution)

            normalized_packet.markdown_path = str(source_path)
            self._atomic_write_text(source_path, self._render_source_page(normalized_packet))
            self._atomic_write_json(contribution_path, next_contribution)
            packets = self._load_all_contribution_packets(normalize_semantics=True, persist_registry=False)
            touched_concept_ids |= {path.stem for path in self.concepts_dir.glob("*.md")}
            self._rebuild_target_pages(
                packets,
                entity_ids=touched_entity_ids,
                concept_ids=touched_concept_ids,
                gpt=gpt,
            )
            self._write_graph_snapshot(packets)

            return {
                "source_path": source_path,
                "contribution_path": contribution_path,
                "graph_path": graph_path,
            }

    def persist_contribution(self, packet: KnowledgePacket, markdown: str) -> dict:
        normalized_packet = self._normalize_packet_semantics(packet)
        safe_id = self._safe_id(normalized_packet.source_id)
        source_path = self.sources_dir / f"{safe_id}.md"
        contribution_path = self.contributions_dir / f"{safe_id}.json"

        normalized_packet.markdown_path = str(source_path)
        self._atomic_write_text(source_path, self._render_source_page(normalized_packet))
        self._atomic_write_json(contribution_path, self._render_contribution(normalized_packet))

        return {
            "source_path": source_path,
            "contribution_path": contribution_path,
        }

    def remove_source(self, source_id: str) -> dict:
        with _WIKI_WRITE_LOCK:
            safe_id = self._safe_id(source_id)
            source_path = self.sources_dir / f"{safe_id}.md"
            graph_path = self.base_dir / "graph.json"
            contribution_path = self.contributions_dir / f"{safe_id}.json"
            previous_contribution = self._read_contribution(safe_id) or {}
            touched_entity_ids = self._collect_entity_ids(previous_contribution)
            touched_concept_ids = self._collect_concept_ids(previous_contribution)

            source_path.unlink(missing_ok=True)
            contribution_path.unlink(missing_ok=True)
            packets = self._load_all_contribution_packets(normalize_semantics=True, persist_registry=False)
            self._rebuild_target_pages(
                packets,
                entity_ids=touched_entity_ids,
                concept_ids=touched_concept_ids,
                gpt=None,
            )
            self._write_graph_snapshot(packets)
            return {"source_path": source_path, "graph_path": graph_path}

    def rebuild_from_contributions(self, gpt=None, cancel_check=None) -> dict:
        packets = self._load_all_contribution_packets(normalize_semantics=True, persist_registry=False)
        self._materialize_from_packets(packets, gpt=gpt, cancel_check=cancel_check)
        if cancel_check and cancel_check():
            return self.read_graph()
        return self.read_graph()

    def _reset_file_wiki_dirs(self) -> None:
        for directory in (self.sources_dir, self.entities_dir, self.concepts_dir, self.contributions_dir):
            directory.mkdir(parents=True, exist_ok=True)
            for path in [*directory.glob("*.md"), *directory.glob("*.json")]:
                path.unlink(missing_ok=True)

    def _reset_materialized_wiki_dirs(self) -> None:
        for directory in (self.sources_dir, self.entities_dir, self.concepts_dir):
            directory.mkdir(parents=True, exist_ok=True)
            for path in [*directory.glob("*.md"), *directory.glob("*.json")]:
                path.unlink(missing_ok=True)

    def _atomic_write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)

    def _atomic_write_json(self, path: Path, payload: dict) -> None:
        self._atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))

    def _load_all_contribution_packets(
        self,
        *,
        normalize_semantics: bool = False,
        persist_registry: bool = False,
    ) -> list[KnowledgePacket]:
        if not self.contributions_dir.exists():
            return []
        packets = []
        for path in sorted(self.contributions_dir.glob("*.json")):
            packet = self._packet_from_contribution(json.loads(path.read_text(encoding="utf-8")))
            if normalize_semantics:
                packet = self._normalize_packet_semantics(packet, persist_registry=persist_registry)
            packets.append(packet)
        return packets

    def _collect_entity_ids(self, contribution: dict) -> set[str]:
        return {
            self._safe_id(entity.get("name", ""))
            for entity in contribution.get("entities", [])
            if entity.get("name")
        }

    def _collect_concept_ids(self, contribution: dict) -> set[str]:
        return {
            self._safe_id(concept.get("name", ""))
            for concept in contribution.get("concepts", [])
            if concept.get("name")
        }

    def _packet_from_contribution(self, data: dict) -> KnowledgePacket:
        entities = []
        concepts = []
        claims = []
        evidence = []
        relations = []
        seen_evidence_ids = set()

        for entity in data.get("entities", []):
            entity_item = KnowledgeEntity(
                name=entity.get("name", ""),
                entity_type=entity.get("entity_type", "unknown"),
                aliases=entity.get("aliases", []),
                description=entity.get("description") or None,
                confidence=entity.get("confidence", 0.0),
            )
            setattr(entity_item, "semantic_related", entity.get("semantic_related", []))
            entities.append(entity_item)

        for concept in data.get("concepts", []):
            concept_item = KnowledgeConcept(
                name=concept.get("name", ""),
                aliases=concept.get("aliases", []),
                description=concept.get("description", ""),
                parent=concept.get("parent"),
                related=concept.get("related", []),
                confidence=concept.get("confidence", 0.0),
            )
            setattr(concept_item, "semantic_related", concept.get("semantic_related", []))
            concepts.append(concept_item)

        evidence_payload = data.get("evidence", [])
        if not evidence_payload:
            evidence_payload = [
                *[item for entity in data.get("entities", []) for item in entity.get("evidence", [])],
                *[item for concept in data.get("concepts", []) for item in concept.get("evidence", [])],
            ]

        for item in evidence_payload:
            evidence_id = item.get("evidence_id") or f"{data.get('source_id')}:evidence:{len(seen_evidence_ids)}"
            if evidence_id in seen_evidence_ids:
                continue
            seen_evidence_ids.add(evidence_id)
            evidence.append(
                KnowledgeEvidence(
                    evidence_id=evidence_id,
                    source_id=item.get("source_id", data.get("source_id", "")),
                    source_type=item.get("source_type", data.get("source_type", "")),
                    text=item.get("text", ""),
                    timestamp=item.get("timestamp"),
                    url=item.get("url"),
                )
            )

        if data.get("claims"):
            claims.extend(
                [
                    KnowledgeClaim(
                        claim=item.get("claim", ""),
                        source=item.get("target_name", ""),
                        target_type=item.get("target_type", "unknown"),
                        evidence_ids=item.get("evidence_ids", []),
                        confidence=item.get("confidence", 0.0),
                    )
                    for item in data.get("claims", [])
                    if item.get("claim") and item.get("target_name")
                ]
            )
        else:
            for entity in data.get("entities", []):
                evidence_ids = [item.get("evidence_id") for item in entity.get("evidence", []) if item.get("evidence_id")]
                claims.extend(
                    [
                        KnowledgeClaim(
                            claim=claim_text,
                            source=entity.get("name", ""),
                            target_type="entity",
                            evidence_ids=evidence_ids,
                            confidence=entity.get("confidence", 0.0),
                        )
                        for claim_text in entity.get("claims", [])
                    ]
                )
            for concept in data.get("concepts", []):
                evidence_ids = [item.get("evidence_id") for item in concept.get("evidence", []) if item.get("evidence_id")]
                claims.extend(
                    [
                        KnowledgeClaim(
                            claim=claim_text,
                            source=concept.get("name", ""),
                            target_type="concept",
                            evidence_ids=evidence_ids,
                            confidence=concept.get("confidence", 0.0),
                        )
                        for claim_text in concept.get("claims", [])
                    ]
                )

        relations.extend(
            [
                KnowledgeRelation(
                    source=item.get("source", ""),
                    target=item.get("target", ""),
                    relation_type=item.get("relation_type", ""),
                    weight=item.get("weight", 1.0),
                )
                for item in data.get("relations", [])
                if item.get("source") and item.get("target") and item.get("relation_type")
            ]
        )

        return KnowledgePacket(
            packet_id=f"{data.get('source_id', '')}:packet",
            source_id=data.get("source_id", ""),
            source_type=data.get("source_type", ""),
            title=data.get("title", data.get("source_id", "")),
            summary=data.get("summary", ""),
            entities=entities,
            concepts=concepts,
            claims=claims,
            evidence=evidence,
            relations=relations,
            topics=data.get("topics", []),
        )

    def _render_source_page(self, packet: KnowledgePacket) -> str:
        entity_links = [
            f"[[entities/{self._safe_id(entity.name)}|{entity.name}]]"
            for entity in packet.entities
        ]
        concept_links = [
            f"[[concepts/{self._safe_id(concept.name)}|{concept.name}]]"
            for concept in packet.concepts
        ]
        return "\n".join(
            [
                "---",
                "type: source",
                f"source_id: {packet.source_id}",
                f"source_type: {packet.source_type}",
                "---",
                "",
                f"# {packet.title}",
                "",
                "## 摘要",
                "",
                packet.summary or "",
                "",
                "## 实体",
                "",
                *(f"- {link}" for link in entity_links),
                "",
                "## 概念",
                "",
                *(f"- {link}" for link in concept_links),
                "",
                "## 观点",
                "",
                *(f"- {claim.claim}" for claim in packet.claims),
                "",
                "## 证据",
                "",
                *(f"- {item.text}" for item in packet.evidence),
                "",
            ]
        )

    def _render_entity_page(self, items: list[tuple[KnowledgePacket, KnowledgeEntity]]) -> str:
        entity = items[0][1]
        descriptions = self._dedupe_texts([item.description for _, item in items])
        claims = self._dedupe_claims_for_target(items, entity.name)
        evidence = self._dedupe_evidence_for_claims(items, entity.name)
        return "\n".join(
            [
                "---",
                "type: entity",
                f"entity_type: {entity.entity_type}",
                "---",
                "",
                f"# {entity.name}",
                "",
                "## 描述",
                "",
                *(f"- {description}" for description in descriptions),
                "",
                "## 观点",
                "",
                *(f"- {claim.claim}" for _, claim in claims),
                "",
                "## 证据",
                "",
                *(
                    f"- {item.text} ([[sources/{self._safe_id(packet.source_id)}|{packet.title}]])"
                    for packet, item in evidence
                ),
                "",
                "## 来源",
                "",
                *(
                    f"- [[sources/{self._safe_id(packet.source_id)}|{packet.title}]]"
                    for packet, _ in items
                ),
                "",
            ]
        )

    def _render_concept_page(self, items: list[tuple[KnowledgePacket, KnowledgeConcept]]) -> str:
        concept = items[0][1]
        descriptions = self._dedupe_texts([item.description for _, item in items])
        claims = self._dedupe_claims_for_target(items, concept.name)
        evidence = self._dedupe_evidence_for_claims(items, concept.name)
        return "\n".join(
            [
                "---",
                "type: concept",
                "---",
                "",
                f"# {concept.name}",
                "",
                "## 描述",
                "",
                *(f"- {description}" for description in descriptions),
                "",
                "## 观点",
                "",
                *(f"- {claim.claim}" for _, claim in claims),
                "",
                "## 证据",
                "",
                *(
                    f"- {item.text} ([[sources/{self._safe_id(packet.source_id)}|{packet.title}]])"
                    for packet, item in evidence
                ),
                "",
                "## 来源",
                "",
                *(
                    f"- [[sources/{self._safe_id(packet.source_id)}|{packet.title}]]"
                    for packet, _ in items
                ),
                "",
            ]
        )

    def _render_contribution(self, packet: KnowledgePacket) -> dict:
        return {
            "source_id": packet.source_id,
            "title": packet.title,
            "source_type": packet.source_type,
            "summary": packet.summary,
            "topics": packet.topics,
            "claims": [
                {
                    "claim": claim.claim,
                    "target_name": claim.source,
                    "target_type": claim.target_type,
                    "evidence_ids": claim.evidence_ids,
                    "confidence": claim.confidence,
                }
                for claim in packet.claims
            ],
            "evidence": [asdict(item) for item in packet.evidence],
            "relations": [asdict(item) for item in packet.relations],
            "entities": [
                {
                    "name": entity.name,
                    "entity_type": entity.entity_type,
                    "aliases": entity.aliases,
                    "description": entity.description or "",
                    "semantic_related": list(getattr(entity, "semantic_related", [])),
                    "claims": [claim.claim for claim in self._claims_for_target(packet, entity.name)],
                    "evidence": [asdict(item) for item in self._evidence_for_target(packet, entity.name)],
                    "confidence": entity.confidence,
                }
                for entity in packet.entities
            ],
            "concepts": [
                {
                    "name": concept.name,
                    "aliases": concept.aliases,
                    "description": concept.description or "",
                    "parent": concept.parent,
                    "related": concept.related,
                    "semantic_related": list(getattr(concept, "semantic_related", [])),
                    "claims": [claim.claim for claim in self._claims_for_target(packet, concept.name)],
                    "evidence": [asdict(item) for item in self._evidence_for_target(packet, concept.name)],
                    "confidence": concept.confidence,
                }
                for concept in packet.concepts
            ],
        }

    def _claims_for_target(self, packet: KnowledgePacket, target_name: str) -> list[KnowledgeClaim]:
        normalized_target = self._normalize_text(target_name)
        return [
            claim
            for claim in packet.claims
            if self._normalize_text(claim.source) == normalized_target
        ]

    def _evidence_for_target(self, packet: KnowledgePacket, target_name: str) -> list[KnowledgeEvidence]:
        evidence_by_id = {item.evidence_id: item for item in packet.evidence}
        evidence_ids = {
            evidence_id
            for claim in self._claims_for_target(packet, target_name)
            for evidence_id in claim.evidence_ids
        }
        return [evidence_by_id[evidence_id] for evidence_id in evidence_ids if evidence_id in evidence_by_id]

    def _dedupe_texts(self, values: list[Optional[str]]) -> list[str]:
        result = []
        seen = set()
        for value in values:
            text = (value or "").strip()
            key = self._normalize_text(text)
            if not text or key in seen:
                continue
            seen.add(key)
            result.append(text)
        return result

    def _dedupe_claims_for_target(self, items: list[tuple[KnowledgePacket, object]], target_name: str) -> list[tuple[KnowledgePacket, KnowledgeClaim]]:
        result = []
        seen = set()
        for packet, _ in items:
            for claim in self._claims_for_target(packet, target_name):
                key = self._normalize_text(claim.claim)
                if not key or key in seen:
                    continue
                seen.add(key)
                result.append((packet, claim))
        return result

    def _dedupe_evidence_for_claims(self, items: list[tuple[KnowledgePacket, object]], target_name: str) -> list[tuple[KnowledgePacket, KnowledgeEvidence]]:
        result = []
        seen = set()
        for packet, _ in items:
            for evidence in self._evidence_for_target(packet, target_name):
                key = self._normalize_text(evidence.text)
                if not key or key in seen:
                    continue
                seen.add(key)
                result.append((packet, evidence))
        return result

    def _normalize_packet_semantics(
        self,
        packet: KnowledgePacket,
        *,
        persist_registry: bool = True,
    ) -> KnowledgePacket:
        if not self.semantic_resolver or not self.vector_store:
            return packet

        normalized_packet = deepcopy(packet)
        entity_rename_map: dict[str, str] = {}
        concept_rename_map: dict[str, str] = {}
        entity_resolution_by_name: dict[str, dict] = {}
        concept_resolution_by_name: dict[str, dict] = {}

        for entity in normalized_packet.entities:
            resolution = self.semantic_resolver.resolve_entity(
                entity,
                vector_store=self.vector_store,
            )
            entity_resolution_by_name[self._normalize_text(entity.name)] = resolution
            canonical_name = (resolution.get("canonical_name") or entity.name).strip() or entity.name

            if resolution.get("action") == "merge":
                original_name = entity.name
                entity.name = canonical_name
                entity.aliases = self._dedupe_texts(
                    [*entity.aliases, original_name, *resolution.get("matched_aliases", [])]
                )
                setattr(entity, "semantic_related", list(getattr(entity, "semantic_related", [])))
                entity_rename_map[self._normalize_text(original_name)] = canonical_name
            elif resolution.get("action") == "semantic_related":
                setattr(
                    entity,
                    "semantic_related",
                    self._dedupe_texts(
                        [*getattr(entity, "semantic_related", []), *resolution.get("semantic_related", []), canonical_name]
                    ),
                )
                self._append_semantic_relation(
                    normalized_packet,
                    source_name=entity.name,
                    target_name=canonical_name,
                )
            else:
                setattr(entity, "semantic_related", list(getattr(entity, "semantic_related", [])))

        for concept in normalized_packet.concepts:
            resolution = self.semantic_resolver.resolve_concept(
                concept,
                vector_store=self.vector_store,
            )
            concept_resolution_by_name[self._normalize_text(concept.name)] = resolution
            canonical_name = (resolution.get("canonical_name") or concept.name).strip() or concept.name

            if resolution.get("action") == "merge":
                original_name = concept.name
                concept.name = canonical_name
                concept.aliases = self._dedupe_texts(
                    [*concept.aliases, original_name, *resolution.get("matched_aliases", [])]
                )
                concept_rename_map[self._normalize_text(original_name)] = canonical_name
            elif resolution.get("action") == "semantic_related":
                related_names = self._dedupe_texts(
                    [*concept.related, *resolution.get("semantic_related", []), canonical_name]
                )
                concept.related = related_names
                setattr(concept, "semantic_related", related_names)
                self._append_semantic_relation(
                    normalized_packet,
                    source_name=concept.name,
                    target_name=canonical_name,
                )
            else:
                setattr(concept, "semantic_related", list(getattr(concept, "semantic_related", [])))

        if entity_rename_map or concept_rename_map:
            for claim in normalized_packet.claims:
                if claim.target_type == "entity":
                    claim.source = self._rewrite_name(claim.source, entity_rename_map)
                elif claim.target_type == "concept":
                    claim.source = self._rewrite_name(claim.source, concept_rename_map)
                else:
                    claim.source = self._rewrite_name(claim.source, entity_rename_map, concept_rename_map)
            for relation in normalized_packet.relations:
                relation.source = self._rewrite_name(relation.source, entity_rename_map, concept_rename_map)
                relation.target = self._rewrite_name(relation.target, entity_rename_map, concept_rename_map)

        normalized_packet.entities = self._merge_entities(normalized_packet.entities)
        normalized_packet.concepts = self._merge_concepts(normalized_packet.concepts)
        if persist_registry:
            for entity in normalized_packet.entities:
                resolution = entity_resolution_by_name.get(self._normalize_text(entity.name)) or {
                    "canonical_name": entity.name,
                    "matched_aliases": [],
                    "semantic_related": list(getattr(entity, "semantic_related", [])),
                }
                if resolution.get("action") == "merge":
                    resolution = {
                        **resolution,
                        "canonical_name": entity.name,
                        "semantic_related": list(getattr(entity, "semantic_related", [])),
                    }
                self.semantic_resolver.persist_entity(
                    entity,
                    vector_store=self.vector_store,
                    resolution=resolution,
                )
            for concept in normalized_packet.concepts:
                resolution = concept_resolution_by_name.get(self._normalize_text(concept.name)) or {
                    "canonical_name": concept.name,
                    "matched_aliases": [],
                    "semantic_related": list(getattr(concept, "semantic_related", [])),
                }
                if resolution.get("action") == "merge":
                    resolution = {
                        **resolution,
                        "canonical_name": concept.name,
                        "semantic_related": list(getattr(concept, "semantic_related", [])),
                    }
                self.semantic_resolver.persist_concept(
                    concept,
                    vector_store=self.vector_store,
                    resolution=resolution,
                )
        return normalized_packet

    def _rewrite_name(self, value: str, *rename_maps: dict[str, str]) -> str:
        normalized_value = self._normalize_text(value)
        for rename_map in rename_maps:
            if normalized_value in rename_map:
                return rename_map[normalized_value]
        return value

    def _append_semantic_relation(
        self,
        packet: KnowledgePacket,
        *,
        source_name: str,
        target_name: str,
        weight: float = 0.85,
    ) -> None:
        if not source_name or not target_name:
            return
        source_key = self._normalize_text(source_name)
        target_key = self._normalize_text(target_name)
        if source_key == target_key:
            return
        for relation in packet.relations:
            if (
                relation.relation_type == "semantic_related"
                and self._normalize_text(relation.source) == source_key
                and self._normalize_text(relation.target) == target_key
            ):
                relation.weight = max(relation.weight or 0.0, weight)
                return
        packet.relations.append(
            KnowledgeRelation(
                source=source_name,
                target=target_name,
                relation_type="semantic_related",
                weight=weight,
            )
        )

    def _merge_entities(self, entities: list[KnowledgeEntity]) -> list[KnowledgeEntity]:
        merged: dict[str, KnowledgeEntity] = {}
        for entity in entities:
            key = self._normalize_text(entity.name)
            current = merged.get(key)
            if current is None:
                merged[key] = entity
                continue
            current.aliases = self._dedupe_texts([*current.aliases, *entity.aliases])
            semantic_related = self._dedupe_texts(
                [
                    *getattr(current, "semantic_related", []),
                    *getattr(entity, "semantic_related", []),
                ]
            )
            setattr(current, "semantic_related", semantic_related)
            if (current.entity_type == "unknown" or not current.entity_type) and entity.entity_type:
                current.entity_type = entity.entity_type
            if not current.description and entity.description:
                current.description = entity.description
            current.confidence = max(current.confidence, entity.confidence)
        return list(merged.values())

    def _merge_concepts(self, concepts: list[KnowledgeConcept]) -> list[KnowledgeConcept]:
        merged: dict[str, KnowledgeConcept] = {}
        for concept in concepts:
            key = self._normalize_text(concept.name)
            current = merged.get(key)
            if current is None:
                merged[key] = concept
                continue
            current.aliases = self._dedupe_texts([*current.aliases, *concept.aliases])
            current.related = self._dedupe_texts([*current.related, *concept.related])
            semantic_related = self._dedupe_texts(
                [
                    *getattr(current, "semantic_related", []),
                    *getattr(concept, "semantic_related", []),
                ]
            )
            setattr(current, "semantic_related", semantic_related)
            if not current.description and concept.description:
                current.description = concept.description
            current.confidence = max(current.confidence, concept.confidence)
        return list(merged.values())

    def _normalize_text(self, value: str) -> str:
        return " ".join((value or "").strip().lower().split())

    def _build_graph_from_packet_list(self, packets: list[KnowledgePacket]) -> GraphPayload:
        graph = GraphPayload()
        graph_path = self.base_dir / "graph.json"
        for packet in packets:
            self._atomic_write_json(graph_path, asdict(graph))
            graph = self._build_graph(packet, graph_path)
        return graph

    def _write_graph_snapshot(self, packets: list[KnowledgePacket]) -> None:
        graph = self._build_graph_from_packet_list(packets)
        graph_path = self.base_dir / "graph.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write_json(graph_path, asdict(graph))
        WikiGraphAnalyzer(self.base_dir).compute_and_persist_communities()

    def _index_target_sources(
        self,
        packets: list[KnowledgePacket],
    ) -> tuple[dict[str, list[tuple[KnowledgePacket, KnowledgeEntity]]], dict[str, list[tuple[KnowledgePacket, KnowledgeConcept]]]]:
        entity_sources: dict[str, list[tuple[KnowledgePacket, KnowledgeEntity]]] = {}
        concept_sources: dict[str, list[tuple[KnowledgePacket, KnowledgeConcept]]] = {}
        for packet in packets:
            for entity in packet.entities:
                entity_sources.setdefault(self._safe_id(entity.name), []).append((packet, entity))
            for concept in packet.concepts:
                concept_sources.setdefault(self._safe_id(concept.name), []).append((packet, concept))
        return entity_sources, concept_sources

    def _rebuild_target_pages(
        self,
        packets: list[KnowledgePacket],
        *,
        entity_ids: set[str],
        concept_ids: set[str],
        gpt=None,
        cancel_check=None,
    ) -> None:
        entity_sources, concept_sources = self._index_target_sources(packets)
        for safe_name in entity_ids:
            if cancel_check and cancel_check():
                return
            page_path = self.entities_dir / f"{safe_name}.md"
            items = entity_sources.get(safe_name, [])
            if not items:
                page_path.unlink(missing_ok=True)
                continue
            fallback_markdown = self._render_entity_page(items)
            merged_markdown = WikiPageMerger().merge(
                page_type="entity",
                page_title=items[0][1].name,
                current_markdown=page_path.read_text(encoding="utf-8") if page_path.exists() else "",
                contribution_payload=[self._render_contribution(packet) for packet, _ in items],
                gpt=gpt,
                fallback_markdown=fallback_markdown,
            )
            if cancel_check and cancel_check():
                return
            self._atomic_write_text(page_path, merged_markdown)

        for safe_name in concept_ids:
            if cancel_check and cancel_check():
                return
            page_path = self.concepts_dir / f"{safe_name}.md"
            items = concept_sources.get(safe_name, [])
            if not items:
                page_path.unlink(missing_ok=True)
                continue
            fallback_markdown = self._render_concept_page(items)
            merged_markdown = WikiPageMerger().merge(
                page_type="concept",
                page_title=items[0][1].name,
                current_markdown=page_path.read_text(encoding="utf-8") if page_path.exists() else "",
                contribution_payload=[self._render_contribution(packet) for packet, _ in items],
                gpt=gpt,
                fallback_markdown=fallback_markdown,
            )
            if cancel_check and cancel_check():
                return
            self._atomic_write_text(page_path, merged_markdown)

    def _materialize_from_packets(self, packets: list[KnowledgePacket], gpt=None, cancel_check=None) -> None:
        self._reset_materialized_wiki_dirs()
        for packet in packets:
            if cancel_check and cancel_check():
                return
            source_path = self.sources_dir / f"{self._safe_id(packet.source_id)}.md"
            self._atomic_write_text(source_path, self._render_source_page(packet))
            contribution_path = self.contributions_dir / f"{self._safe_id(packet.source_id)}.json"
            self._atomic_write_json(contribution_path, self._render_contribution(packet))
        entity_sources, concept_sources = self._index_target_sources(packets)
        self._rebuild_target_pages(
            packets,
            entity_ids=set(entity_sources.keys()),
            concept_ids=set(concept_sources.keys()),
            gpt=gpt,
            cancel_check=cancel_check,
        )
        if cancel_check and cancel_check():
            return
        self._write_graph_snapshot(packets)

    def _build_graph(self, packet: KnowledgePacket, graph_path: Path) -> GraphPayload:
        graph = self._load_graph(graph_path)
        source_id = f"source:{packet.source_id}"
        nodes_by_id = {node.id: node for node in graph.nodes}
        edge_weights = {
            (edge.source, edge.target, edge.type): edge.weight
            for edge in graph.edges
        }

        nodes_by_id[source_id] = GraphNode(id=source_id, label=packet.title, type="source", size=10, weight=1.0)

        for entity in packet.entities:
            entity_id = f"entity:{self._safe_id(entity.name)}"
            nodes_by_id.setdefault(
                entity_id,
                GraphNode(id=entity_id, label=entity.name, type="entity", size=8, weight=entity.confidence or 0.7),
            )
            edge_weights[(source_id, entity_id, "mentions")] = 0.7

        for concept in packet.concepts:
            concept_id = f"concept:{self._safe_id(concept.name)}"
            nodes_by_id.setdefault(
                concept_id,
                GraphNode(id=concept_id, label=concept.name, type="concept", size=8, weight=concept.confidence or 0.7),
            )
            edge_weights[(source_id, concept_id, "mentions")] = 0.7

        for relation in packet.relations:
            source_ref = self._resolve_graph_node_ref(packet, relation.source, source_id, nodes_by_id)
            target_ref = self._resolve_graph_node_ref(packet, relation.target, source_id, nodes_by_id)
            if relation.relation_type == "semantic_related":
                if source_ref and not target_ref:
                    target_ref = self._build_semantic_placeholder_ref(relation.target, source_ref[1].type)
                elif target_ref and not source_ref:
                    source_ref = self._build_semantic_placeholder_ref(relation.source, target_ref[1].type)
            if not source_ref or not target_ref:
                continue
            source_node_id, source_node = source_ref
            target_node_id, target_node = target_ref
            nodes_by_id.setdefault(source_node_id, source_node)
            nodes_by_id.setdefault(target_node_id, target_node)
            edge_weights[(source_node_id, target_node_id, relation.relation_type)] = relation.weight or 1.0

        type_order = {"source": 0, "entity": 1, "concept": 2}
        nodes = sorted(nodes_by_id.values(), key=lambda node: (type_order.get(node.type, 99), node.id))
        edges = [
            GraphEdge(source=source, target=target, type=edge_type, weight=weight)
            for (source, target, edge_type), weight in sorted(edge_weights.items())
        ]
        return GraphPayload(nodes=nodes, edges=edges, clusters=self._build_clusters(nodes))

    def _resolve_graph_node_ref(
        self,
        packet: KnowledgePacket,
        name: str,
        source_node_id: str,
        nodes_by_id: Optional[dict[str, GraphNode]] = None,
    ) -> Optional[tuple[str, GraphNode]]:
        normalized_name = self._normalize_text(name)
        if normalized_name in {self._normalize_text(packet.title), self._normalize_text(packet.source_id)}:
            return source_node_id, GraphNode(id=source_node_id, label=packet.title, type="source", size=10, weight=1.0)

        for entity in packet.entities:
            if self._normalize_text(entity.name) == normalized_name:
                entity_id = f"entity:{self._safe_id(entity.name)}"
                return entity_id, GraphNode(
                    id=entity_id,
                    label=entity.name,
                    type="entity",
                    size=8,
                    weight=entity.confidence or 0.7,
                )

        for concept in packet.concepts:
            if self._normalize_text(concept.name) == normalized_name:
                concept_id = f"concept:{self._safe_id(concept.name)}"
                return concept_id, GraphNode(
                    id=concept_id,
                    label=concept.name,
                    type="concept",
                    size=8,
                    weight=concept.confidence or 0.7,
                )
        if nodes_by_id:
            for node_id, node in nodes_by_id.items():
                if self._normalize_text(node.label) == normalized_name:
                    return node_id, node
        return None

    def _build_semantic_placeholder_ref(
        self,
        name: str,
        node_type: str,
    ) -> tuple[str, GraphNode]:
        node_id = f"{node_type}:{self._safe_id(name)}"
        return node_id, GraphNode(
            id=node_id,
            label=name,
            type=node_type,
            size=8,
            weight=0.75,
        )

    def _load_graph(self, graph_path: Path) -> GraphPayload:
        if not graph_path.exists():
            return GraphPayload()
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        return GraphPayload(
            nodes=[GraphNode(**node) for node in data.get("nodes", [])],
            edges=[GraphEdge(**edge) for edge in data.get("edges", [])],
            clusters=[GraphCluster(**cluster) for cluster in data.get("clusters", [])],
        )

    def _build_clusters(self, nodes: list[GraphNode]) -> list[GraphCluster]:
        labels = {"source": "来源", "entity": "实体", "concept": "概念"}
        clusters = []
        for node_type in ("source", "entity", "concept"):
            node_ids = [node.id for node in nodes if node.type == node_type]
            if node_ids:
                clusters.append(GraphCluster(id=f"cluster:{node_type}", label=labels[node_type], node_ids=node_ids))
        return clusters

    def _needs_community_repair(self, graph: dict) -> bool:
        nodes = graph.get("nodes", [])
        if not nodes:
            return False
        if not graph.get("communities"):
            return True
        return any(
            "community_id" not in node
            or "community_color" not in node
            or str(node.get("community_label") or "").startswith("Community ")
            for node in nodes
        )

    def _safe_id(self, value: str) -> str:
        return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)

    def _read_contribution(self, page_id: str) -> Union[dict, None]:
        contribution_path = self.contributions_dir / f"{page_id}.json"
        if not contribution_path.exists():
            return None
        return json.loads(contribution_path.read_text(encoding="utf-8"))

    def _page_title(self, page_id: str, page_path: Path, packet: Union[dict, None]) -> str:
        if packet and packet.get("title"):
            return packet["title"]
        return self._markdown_title(page_path, page_id)

    def _markdown_title(self, page_path: Path, fallback: str) -> str:
        for line in page_path.read_text(encoding="utf-8").splitlines():
            title = line.strip()
            if title.startswith("# "):
                return title[2:].strip()
        return fallback
