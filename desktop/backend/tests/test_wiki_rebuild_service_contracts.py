import json
import pathlib
import sys
import tempfile
import threading
import time
import types
import unittest
from dataclasses import dataclass, field
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

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

if "kombu" not in sys.modules:
    kombu_module = types.ModuleType("kombu")
    kombu_module.uuid = lambda: "stub-uuid"
    sys.modules["kombu"] = kombu_module

from app.models.knowledge_packet import KnowledgeEntity, KnowledgePacket  # noqa: E402
from app.models.wiki_analysis import WikiAnalysis  # noqa: E402
from app.services.wiki_pipeline import WikiPipeline  # noqa: E402


@dataclass
class _SummaryInput:
    input_id: str = "source-1"
    input_type: str = "note"
    title: str = "Source 1"
    platform: str = "note"
    user_options: dict = field(default_factory=dict)


class WikiRebuildServiceContractsTest(unittest.TestCase):
    def test_extract_contribution_stops_before_materialize_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = pathlib.Path(tmp)
            summary_input = _SummaryInput(user_options={})
            analysis = WikiAnalysis(
                source_id="source-1",
                source_type="note",
                title="Source 1",
                summary="summary",
            )
            packet = KnowledgePacket(
                packet_id="source-1:packet",
                source_id="source-1",
                source_type="note",
                title="Source 1",
                summary="summary",
                entities=[KnowledgeEntity(name="Entity A", entity_type="person")],
            )

            with patch("app.services.wiki_pipeline.KnowledgeExtractor") as extractor_cls:
                extractor = extractor_cls.return_value
                extractor.analyze.return_value = analysis
                extractor.build_packet.return_value = packet

                payload = WikiPipeline(output_dir=output_dir).extract_contribution(
                    summary_input,
                    "# Source 1",
                    gpt=object(),
                )

            self.assertEqual(payload["status"], "success")
            self.assertTrue((output_dir / "source-1_knowledge_analysis.json").exists())
            self.assertTrue((output_dir / "wiki" / "contributions" / "source-1.json").exists())
            self.assertTrue((output_dir / "wiki" / "sources" / "source-1.md").exists())
            self.assertFalse((output_dir / "wiki" / "entities" / "entity_a.md").exists())
            self.assertFalse((output_dir / "wiki" / "graph.json").exists())

    def test_rebuild_service_cancels_running_rebuild_and_runs_latest_request(self):
        from app.services.wiki_rebuild_service import WikiRebuildService

        first_started = threading.Event()
        release_first = threading.Event()
        run_generations: list[int] = []
        canceled_seen: list[bool] = []

        def fake_rebuild(self, gpt=None, cancel_check=None):
            run_generations.append(self.current_generation)
            if len(run_generations) == 1:
                first_started.set()
                while not release_first.wait(0.01):
                    if cancel_check and cancel_check():
                        canceled_seen.append(True)
                        return {"nodes": [], "edges": [], "clusters": []}
            return {"nodes": [{"id": f"gen-{self.current_generation}"}], "edges": [], "clusters": []}

        with tempfile.TemporaryDirectory() as tmp:
            service = WikiRebuildService(output_dir=pathlib.Path(tmp), worker_name_prefix="test-wiki-rebuild")
            with patch("app.services.wiki_rebuild_service.WikiStore.rebuild_from_contributions", fake_rebuild):
                service.request_rebuild(gpt="old")
                self.assertTrue(first_started.wait(1))
                service.request_rebuild(gpt="new")
                service.wait_idle(timeout=2)

            status_path = pathlib.Path(tmp) / "wiki_rebuild_job.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "success")
            self.assertEqual(run_generations, [1, 2])
            self.assertEqual(canceled_seen, [True])


if __name__ == "__main__":
    unittest.main()
