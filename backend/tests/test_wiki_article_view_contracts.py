import pathlib
import sys
import tempfile
import types
import unittest
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
    KnowledgeEntity,
    KnowledgeEvidence,
    KnowledgePacket,
    KnowledgeRelation,
)
from app.services.wiki_store import WikiStore  # noqa: E402


class WikiArticleViewContractsTest(unittest.TestCase):
    def test_get_article_returns_only_selected_source_contribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = WikiStore(base_dir=pathlib.Path(tmp) / "wiki")
            with patch("app.services.wiki_store.WikiGraphAnalyzer.compute_and_persist_communities", return_value={}):
                store.persist_contribution(
                    KnowledgePacket(
                        packet_id="article-1:packet",
                        source_id="article-1",
                        source_type="note",
                        title="文章 1",
                        summary="文章 1 摘要",
                        entities=[KnowledgeEntity(name="实体 A", entity_type="person", description="实体 A 描述")],
                        concepts=[KnowledgeConcept(name="概念 A", description="概念 A 描述")],
                        claims=[
                            KnowledgeClaim(
                                claim="文章 1 的观点",
                                source="实体 A",
                                target_type="entity",
                                evidence_ids=["article-1:evidence:0"],
                                confidence=0.8,
                            )
                        ],
                        evidence=[
                            KnowledgeEvidence(
                                evidence_id="article-1:evidence:0",
                                source_id="article-1",
                                source_type="note",
                                text="文章 1 的证据",
                            )
                        ],
                        relations=[KnowledgeRelation(source="实体 A", target="概念 A", relation_type="mentions")],
                    ),
                    markdown="# 文章 1",
                )
                store.persist_contribution(
                    KnowledgePacket(
                        packet_id="article-2:packet",
                        source_id="article-2",
                        source_type="note",
                        title="文章 2",
                        summary="文章 2 摘要",
                        entities=[KnowledgeEntity(name="实体 B", entity_type="org")],
                        concepts=[KnowledgeConcept(name="概念 B")],
                    ),
                    markdown="# 文章 2",
                )

            article = store.get_article("article-1")

            self.assertIsNotNone(article)
            assert article is not None
            self.assertEqual(article["id"], "article-1")
            self.assertEqual(article["title"], "文章 1")
            self.assertEqual([item["name"] for item in article["entities"]], ["实体 A"])
            self.assertEqual([item["name"] for item in article["concepts"]], ["概念 A"])
            self.assertEqual([item["claim"] for item in article["claims"]], ["文章 1 的观点"])
            self.assertEqual([item["text"] for item in article["evidence"]], ["文章 1 的证据"])
            self.assertEqual([item["source"] for item in article["relations"]], ["实体 A"])


if __name__ == "__main__":
    unittest.main()
