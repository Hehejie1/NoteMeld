import json
import pathlib
import sys
import tempfile
import types
import unittest
from typing import Optional
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

if "chromadb" not in sys.modules:
    chromadb_module = types.ModuleType("chromadb")
    chromadb_module.PersistentClient = object
    chromadb_config_module = types.ModuleType("chromadb.config")

    class _StubSettings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    chromadb_config_module.Settings = _StubSettings
    chromadb_module.config = chromadb_config_module
    sys.modules["chromadb"] = chromadb_module
    sys.modules["chromadb.config"] = chromadb_config_module

from app.models.knowledge_packet import (  # noqa: E402
    KnowledgeClaim,
    KnowledgeConcept,
    KnowledgeEvidence,
    KnowledgeEntity,
    KnowledgePacket,
)
from app.services.wiki_semantic_resolver import WikiSemanticResolver  # noqa: E402
from app.services.vector_store import VectorStoreManager  # noqa: E402
from app.services.wiki_store import WikiStore  # noqa: E402


class _FakeVectorStore:
    pass


class _FakeWikiTermCollection:
    def __init__(self):
        self._rows = {}

    def upsert(self, *, documents, metadatas, ids):
        for doc, metadata, row_id in zip(documents, metadatas, ids):
            self._rows[row_id] = {
                "id": row_id,
                "document": doc,
                "metadata": dict(metadata or {}),
            }

    def query(self, *, query_texts, n_results, where=None):
        query_text = (query_texts or [""])[0]
        normalized_query = _normalize_text(query_text)
        query_tokens = set(normalized_query.split())
        matches = []
        for row in self._rows.values():
            if not _match_metadata(row["metadata"], where):
                continue
            metadata = row["metadata"]
            normalized_name = _normalize_text(metadata.get("name", ""))
            aliases = {_normalize_text(alias) for alias in _split_csv(metadata.get("aliases"))}
            document_tokens = set(_normalize_text(row["document"]).split())

            explicit_distance = _query_distance(metadata, normalized_query)
            has_explicit_distance = explicit_distance is not None
            score = explicit_distance if explicit_distance is not None else 1.0
            if normalized_query and normalized_query == normalized_name:
                score = 0.0
            elif normalized_query and normalized_query in aliases:
                score = 0.0
            elif (not has_explicit_distance) and query_tokens and query_tokens & ({normalized_name} | aliases | document_tokens):
                score = min(score, 0.2)
            matches.append((score, row))

        matches.sort(key=lambda item: (item[0], item[1]["id"]))
        selected_pairs = matches[:n_results]
        selected = [row for _, row in selected_pairs]
        return {
            "ids": [[row["id"] for row in selected]],
            "documents": [[row["document"] for row in selected]],
            "metadatas": [[row["metadata"] for row in selected]],
            "distances": [[score for score, _ in selected_pairs]],
        }

    def delete(self, *, ids):
        for row_id in ids:
            self._rows.pop(row_id, None)


class _FakeVectorClient:
    def __init__(self):
        self._collections = {}

    def get_or_create_collection(self, name, metadata=None):
        self._collections.setdefault(name, _FakeWikiTermCollection())
        return self._collections[name]

    def get_collection(self, name):
        if name not in self._collections:
            raise KeyError(name)
        return self._collections[name]


def _normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _split_csv(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _query_distance(metadata: dict, normalized_query: str) -> Optional[float]:
    query_distances = metadata.get("query_distances")
    if isinstance(query_distances, dict) and normalized_query in query_distances:
        return float(query_distances[normalized_query])
    if "vector_distance" in metadata:
        return float(metadata["vector_distance"])
    return None


def _match_metadata(metadata: dict, where: Optional[dict]) -> bool:
    if not where:
        return True
    if "$and" in where:
        return all(_match_metadata(metadata, item) for item in where["$and"])
    for key, value in where.items():
        if metadata.get(key) != value:
            return False
    return True


class _StubSemanticResolver:
    def canonicalize_concept(self, concept: KnowledgeConcept, *, vector_store):
        if concept.name == "LLM":
            return {
                "canonical_name": "Large Language Model",
                "matched_aliases": ["LLM"],
            }
        return {
            "canonical_name": concept.name,
            "matched_aliases": list(concept.aliases),
        }


class TestWikiSemanticIncrementalMerge(unittest.TestCase):
    def test_init_accepts_injected_semantic_components(self):
        vector_store = _FakeVectorStore()
        semantic_resolver = _StubSemanticResolver()

        store = WikiStore(
            base_dir=pathlib.Path("/tmp/not-used"),
            vector_store=vector_store,
            semantic_resolver=semantic_resolver,
        )

        self.assertIs(store.vector_store, vector_store)
        self.assertIs(store.semantic_resolver, semantic_resolver)

    def test_incremental_persist_merges_semantic_equivalents_into_single_concept_page(self):
        vector_store = self._make_vector_store()
        semantic_resolver = WikiSemanticResolver()

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = pathlib.Path(tmp_dir) / "wiki"
            store = self._make_store(base_dir, vector_store=vector_store, semantic_resolver=semantic_resolver)

            packet_alias = self._build_concept_packet(
                source_id="note-llm",
                title="LLM Note",
                concept_name="LLM",
                aliases=["Large Language Model"],
                claim_text="LLM 可以帮助完成复杂推理。",
                evidence_text="LLM 可以帮助完成复杂推理。",
            )
            packet_canonical = self._build_concept_packet(
                source_id="note-large-language-model",
                title="Large Language Model Note",
                concept_name="Large Language Model",
                aliases=["LLM"],
                claim_text="Large Language Model 需要高质量训练数据。",
                evidence_text="Large Language Model 需要高质量训练数据。",
            )

            self._persist_packets(
                store,
                (packet_alias, "# LLM"),
                (packet_canonical, "# Large Language Model"),
            )

            canonical_page = base_dir / "concepts" / "Large_Language_Model.md"
            alias_page = base_dir / "concepts" / "LLM.md"

            self.assertTrue(canonical_page.exists())
            canonical_markdown = canonical_page.read_text(encoding="utf-8")

            self.assertIn("[[sources/note-llm|LLM Note]]", canonical_markdown)
            self.assertIn(
                "[[sources/note-large-language-model|Large Language Model Note]]",
                canonical_markdown,
            )
            self.assertFalse(
                alias_page.exists(),
                "语义等价概念应收敛到统一概念页面，而不是保留别名页。",
            )

    def test_incremental_persist_keeps_middle_band_concept_and_records_related(self):
        vector_store = self._make_vector_store()
        semantic_resolver = WikiSemanticResolver(merge_threshold=0.12, related_threshold=0.35)

        vector_store.upsert_wiki_term(
            term_id="concept:autonomous_agent",
            term_type="concept",
            name="Autonomous Agent",
            aliases=["Agentic System"],
            description="A system that can plan and act with autonomy.",
            metadata={"query_distances": {"ai agent": 0.24}, "source_count": 3},
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = pathlib.Path(tmp_dir) / "wiki"
            store = self._make_store(base_dir, vector_store=vector_store, semantic_resolver=semantic_resolver)

            packet = self._build_concept_packet(
                source_id="note-ai-agent",
                title="AI Agent Note",
                concept_name="AI Agent",
                aliases=["Autonomous Software Agent"],
                claim_text="AI Agent 需要任务规划与工具调用能力。",
                evidence_text="AI Agent 需要任务规划与工具调用能力。",
            )

            self._persist_packets(store, (packet, "# AI Agent"))

            concept_page = base_dir / "concepts" / "AI_Agent.md"
            canonical_page = base_dir / "concepts" / "Autonomous_Agent.md"
            contribution_path = base_dir / "contributions" / "note-ai-agent.json"

            self.assertTrue(concept_page.exists())
            self.assertFalse(canonical_page.exists(), "中间带命中不应直接收敛到 canonical 页。")

            contribution = self._read_json(contribution_path)
            stored_concept = contribution["concepts"][0]
            self.assertEqual(stored_concept["name"], "AI Agent")
            self.assertIn("Autonomous Agent", stored_concept["related"])
            self.assertIn("Autonomous Agent", stored_concept["semantic_related"])

            self._assert_graph_has_edge(
                store.read_graph(),
                source="concept:AI_Agent",
                target="concept:Autonomous_Agent",
                edge_type="semantic_related",
            )

    def test_incremental_persist_merges_semantic_equivalents_into_single_entity_page(self):
        vector_store = self._make_vector_store()
        semantic_resolver = WikiSemanticResolver()

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = pathlib.Path(tmp_dir) / "wiki"
            store = self._make_store(base_dir, vector_store=vector_store, semantic_resolver=semantic_resolver)

            packet_alias = self._build_entity_packet(
                source_id="note-openai-inc",
                title="OpenAI Inc. Note",
                entity_name="OpenAI Inc.",
                aliases=["OpenAI"],
                claim_text="OpenAI Inc. 发布了新的多模态模型。",
                evidence_text="OpenAI Inc. 发布了新的多模态模型。",
            )
            packet_canonical = self._build_entity_packet(
                source_id="note-openai",
                title="OpenAI Note",
                entity_name="OpenAI",
                aliases=["OpenAI Inc."],
                claim_text="OpenAI 推动了推理模型的工程化落地。",
                evidence_text="OpenAI 推动了推理模型的工程化落地。",
            )

            self._persist_packets(
                store,
                (packet_alias, "# OpenAI Inc."),
                (packet_canonical, "# OpenAI"),
            )

            canonical_page = base_dir / "entities" / "OpenAI_Inc_.md"
            alias_page = base_dir / "entities" / "OpenAI.md"

            self.assertTrue(canonical_page.exists())
            canonical_markdown = canonical_page.read_text(encoding="utf-8")

            self.assertIn("[[sources/note-openai-inc|OpenAI Inc. Note]]", canonical_markdown)
            self.assertIn("[[sources/note-openai|OpenAI Note]]", canonical_markdown)
            self.assertFalse(
                alias_page.exists(),
                "语义等价实体应收敛到统一实体页面，而不是保留别名页。",
            )

    def test_incremental_persist_keeps_middle_band_entity_and_records_related(self):
        vector_store = self._make_vector_store()
        semantic_resolver = WikiSemanticResolver(merge_threshold=0.12, related_threshold=0.35)

        vector_store.upsert_wiki_term(
            term_id="entity:deepmind",
            term_type="entity",
            name="DeepMind",
            aliases=["Google DeepMind"],
            description="An AI research lab.",
            metadata={"query_distances": {"google ai lab": 0.24}, "source_count": 3},
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = pathlib.Path(tmp_dir) / "wiki"
            store = self._make_store(base_dir, vector_store=vector_store, semantic_resolver=semantic_resolver)

            packet = self._build_entity_packet(
                source_id="note-google-ai-lab",
                title="Google AI Lab Note",
                entity_name="Google AI Lab",
                aliases=["Alphabet AI Research Lab"],
                claim_text="Google AI Lab 在强化学习和模型系统方面持续投入。",
                evidence_text="Google AI Lab 在强化学习和模型系统方面持续投入。",
            )

            self._persist_packets(store, (packet, "# Google AI Lab"))

            entity_page = base_dir / "entities" / "Google_AI_Lab.md"
            canonical_page = base_dir / "entities" / "DeepMind.md"
            contribution_path = base_dir / "contributions" / "note-google-ai-lab.json"

            self.assertTrue(entity_page.exists())
            self.assertFalse(canonical_page.exists(), "中间带命中不应直接收敛到 canonical entity 页。")

            contribution = self._read_json(contribution_path)
            stored_entity = contribution["entities"][0]
            self.assertEqual(stored_entity["name"], "Google AI Lab")
            self.assertIn("DeepMind", stored_entity["semantic_related"])

            self._assert_graph_has_edge(
                store.read_graph(),
                source="entity:Google_AI_Lab",
                target="entity:DeepMind",
                edge_type="semantic_related",
            )

    def test_vector_store_global_wiki_term_helpers_upsert_query_and_delete(self):
        store = VectorStoreManager.__new__(VectorStoreManager)
        store._client = _FakeVectorClient()

        store.upsert_wiki_term(
            term_id="concept:large_language_model",
            term_type="concept",
            name="Large Language Model",
            aliases=["LLM"],
            description="A language model that supports complex reasoning tasks.",
            metadata={"canonical_name": "Large Language Model", "source_count": 2},
        )
        store.upsert_wiki_term(
            term_id="concept:prompt_engineering",
            term_type="concept",
            name="Prompt Engineering",
            aliases=["Prompt Design"],
            description="A practice for improving prompt quality.",
        )
        store.upsert_wiki_term(
            term_id="entity:openai",
            term_type="entity",
            name="OpenAI",
            aliases=["OpenAI Inc."],
            description="An AI research and product company.",
        )

        concept_results = store.query_wiki_terms(
            term_type="concept",
            query_text="How do LLM systems reason?",
            n_results=5,
        )

        self.assertEqual(concept_results[0]["term_id"], "concept:large_language_model")
        self.assertEqual(concept_results[0]["term_type"], "concept")
        self.assertEqual(concept_results[0]["name"], "Large Language Model")
        self.assertEqual(concept_results[0]["aliases"], ["LLM"])
        self.assertEqual(concept_results[0]["metadata"]["source_count"], 2)
        self.assertTrue(all(item["term_type"] == "concept" for item in concept_results))

        store.delete_wiki_term("concept:large_language_model")
        remaining_results = store.query_wiki_terms(
            term_type="concept",
            query_text="LLM",
            n_results=5,
        )
        remaining_ids = [item["term_id"] for item in remaining_results]
        self.assertNotIn("concept:large_language_model", remaining_ids)

    def test_semantic_resolver_exact_alias_and_vector_middle_band(self):
        vector_store = self._make_vector_store()
        resolver = WikiSemanticResolver(merge_threshold=0.12, related_threshold=0.35)

        vector_store.upsert_wiki_term(
            term_id="concept:large_language_model",
            term_type="concept",
            name="Large Language Model",
            aliases=["LLM"],
            description="A language model that supports complex reasoning tasks.",
            metadata={"query_distances": {"reasoning model": 0.05, "ai agent": 0.9}, "source_count": 2},
        )
        vector_store.upsert_wiki_term(
            term_id="concept:autonomous_agent",
            term_type="concept",
            name="Autonomous Agent",
            aliases=["Agentic System"],
            description="A system that can plan and act with autonomy.",
            metadata={"query_distances": {"reasoning model": 0.45, "ai agent": 0.24}, "source_count": 3},
        )

        exact_result = resolver.resolve_concept(
            KnowledgeConcept(name="Large Language Model", aliases=[]),
            vector_store=vector_store,
        )
        alias_result = resolver.resolve_concept(
            KnowledgeConcept(name="LLM", aliases=[]),
            vector_store=vector_store,
        )
        vector_merge_result = resolver.resolve_concept(
            KnowledgeConcept(name="Reasoning Model", aliases=[]),
            vector_store=vector_store,
        )
        vector_middle_result = resolver.resolve_concept(
            KnowledgeConcept(name="AI Agent", aliases=[]),
            vector_store=vector_store,
        )

        self.assertEqual(exact_result["action"], "merge")
        self.assertEqual(exact_result["canonical_name"], "Large Language Model")
        self.assertEqual(alias_result["action"], "merge")
        self.assertEqual(alias_result["canonical_name"], "Large Language Model")
        self.assertEqual(alias_result["matched_aliases"], ["LLM"])
        self.assertEqual(vector_merge_result["action"], "merge")
        self.assertEqual(vector_merge_result["canonical_name"], "Large Language Model")
        self.assertEqual(vector_middle_result["action"], "semantic_related")
        self.assertEqual(vector_middle_result["canonical_name"], "Autonomous Agent")

    def _make_vector_store(self) -> VectorStoreManager:
        vector_store = VectorStoreManager.__new__(VectorStoreManager)
        vector_store._client = _FakeVectorClient()
        return vector_store

    def _make_store(
        self,
        base_dir: pathlib.Path,
        *,
        vector_store,
        semantic_resolver,
    ) -> WikiStore:
        return WikiStore(
            base_dir=base_dir,
            vector_store=vector_store,
            semantic_resolver=semantic_resolver,
        )

    def _persist_packets(self, store: WikiStore, *items: tuple[KnowledgePacket, str]) -> None:
        with patch("app.services.wiki_store.WikiGraphAnalyzer.compute_and_persist_communities", return_value={}):
            for packet, markdown in items:
                store.persist(packet, markdown=markdown)

    def _read_json(self, path: pathlib.Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _assert_graph_has_edge(
        self,
        graph: dict,
        *,
        source: str,
        target: str,
        edge_type: str,
    ) -> None:
        self.assertTrue(
            any(
                edge["type"] == edge_type and edge["source"] == source and edge["target"] == target
                for edge in graph["edges"]
            ),
            f"图谱必须包含 {edge_type}: {source} -> {target}",
        )

    def _build_concept_packet(
        self,
        *,
        source_id: str,
        title: str,
        concept_name: str,
        aliases: list[str],
        claim_text: str,
        evidence_text: str,
    ) -> KnowledgePacket:
        evidence_id = f"{source_id}:evidence:0"
        return KnowledgePacket(
            packet_id=f"{source_id}:packet",
            source_id=source_id,
            source_type="note",
            title=title,
            summary="",
            concepts=[
                KnowledgeConcept(
                    name=concept_name,
                    aliases=aliases,
                    description=f"{concept_name} 的概念定义",
                    confidence=0.95,
                )
            ],
            claims=[
                KnowledgeClaim(
                    claim=claim_text,
                    source=concept_name,
                    target_type="concept",
                    evidence_ids=[evidence_id],
                    confidence=0.95,
                )
            ],
            evidence=[
                KnowledgeEvidence(
                    evidence_id=evidence_id,
                    source_id=source_id,
                    source_type="note",
                    text=evidence_text,
                )
            ],
        )

    def _build_entity_packet(
        self,
        *,
        source_id: str,
        title: str,
        entity_name: str,
        aliases: list[str],
        claim_text: str,
        evidence_text: str,
    ) -> KnowledgePacket:
        evidence_id = f"{source_id}:evidence:0"
        return KnowledgePacket(
            packet_id=f"{source_id}:packet",
            source_id=source_id,
            source_type="note",
            title=title,
            summary="",
            entities=[
                KnowledgeEntity(
                    name=entity_name,
                    entity_type="organization",
                    aliases=aliases,
                    description=f"{entity_name} 的实体定义",
                    confidence=0.95,
                )
            ],
            claims=[
                KnowledgeClaim(
                    claim=claim_text,
                    source=entity_name,
                    target_type="entity",
                    evidence_ids=[evidence_id],
                    confidence=0.95,
                )
            ],
            evidence=[
                KnowledgeEvidence(
                    evidence_id=evidence_id,
                    source_id=source_id,
                    source_type="note",
                    text=evidence_text,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
