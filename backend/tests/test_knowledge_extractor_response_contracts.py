import json
import importlib
import pathlib
import sys
import unittest
from types import SimpleNamespace


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

existing_extractor_module = sys.modules.get("app.services.knowledge_extractor")
if existing_extractor_module is not None and getattr(existing_extractor_module, "KnowledgeExtractor", None) is object:
    sys.modules.pop("app.services.knowledge_extractor", None)
KnowledgeExtractor = importlib.import_module(
    "app.services.knowledge_extractor"
).KnowledgeExtractor


def _summary_input():
    return SimpleNamespace(
        input_id="source-1",
        input_type="web",
        source_url="https://example.com/source",
        title="测试来源",
    )


def _payload():
    return {
        "title": "测试来源",
        "summary": "摘要",
        "entities": [],
        "concepts": [],
        "claims": [],
        "evidence": [],
        "relations": [],
        "topics": [],
    }


class _FakeGPT:
    model = "reasoning-model"
    usage_context = {"provider_id": "provider-1"}

    def __init__(self, response):
        self.response = response
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _response(*, content="", reasoning_content="", finish_reason="stop"):
    message = SimpleNamespace(content=content, reasoning_content=reasoning_content)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


class TestKnowledgeExtractorResponseContracts(unittest.TestCase):
    def test_recovers_verified_json_from_reasoning_when_final_content_is_empty(self):
        reasoning = f"BEGIN_JSON\n{json.dumps(_payload(), ensure_ascii=False)}\nEND_JSON"
        gpt = _FakeGPT(_response(reasoning_content=reasoning))

        result = KnowledgeExtractor()._request_prompt_json_payload(
            _summary_input(), "正文", gpt
        )

        self.assertEqual(result["title"], "测试来源")
        self.assertEqual(result["summary"], "摘要")

    def test_classifies_length_finish_as_truncated_without_exposing_reasoning(self):
        secret_reasoning = "正在分析用户隐私，但 JSON 尚未生成"
        gpt = _FakeGPT(_response(
            reasoning_content=secret_reasoning,
            finish_reason="length",
        ))

        with self.assertRaisesRegex(ValueError, "output truncated before final JSON") as ctx:
            KnowledgeExtractor()._request_prompt_json_payload(
                _summary_input(), "正文", gpt
            )

        self.assertNotIn(secret_reasoning, str(ctx.exception))

    def test_classifies_reasoning_without_final_json(self):
        gpt = _FakeGPT(_response(reasoning_content="只有分析过程"))

        with self.assertRaisesRegex(ValueError, "produced reasoning but no final JSON"):
            KnowledgeExtractor()._request_prompt_json_payload(
                _summary_input(), "正文", gpt
            )

    def test_default_output_budget_allows_reasoning_model_final_answer(self):
        self.assertGreaterEqual(KnowledgeExtractor.ANALYSIS_MAX_TOKENS, 3200)

    def test_normalization_enforces_structured_output_limits(self):
        payload = _payload()
        payload.update({
            "summary": "摘" * 300,
            "entities": [
                {"name": f"实体{i}", "description": "描" * 180}
                for i in range(10)
            ],
            "concepts": [
                {"name": f"概念{i}", "description": "描" * 180}
                for i in range(10)
            ],
            "evidence": [
                {"evidence_id": f"e{i}", "text": "证" * 180}
                for i in range(10)
            ],
            "claims": [
                {"claim": f"观点{i}", "target_type": "source", "evidence_ids": []}
                for i in range(10)
            ],
            "relations": [
                {"source": f"s{i}", "target": f"t{i}", "relation_type": "related"}
                for i in range(10)
            ],
        })

        result = KnowledgeExtractor()._normalize_analysis_payload(_summary_input(), payload)

        self.assertEqual(len(result["summary"]), 240)
        self.assertEqual(len(result["entities"]), 6)
        self.assertEqual(len(result["concepts"]), 6)
        self.assertEqual(len(result["claims"]), 8)
        self.assertEqual(len(result["evidence"]), 8)
        self.assertEqual(len(result["relations"]), 8)
        self.assertTrue(all(len(item["description"]) <= 120 for item in result["entities"]))
        self.assertTrue(all(len(item["text"]) <= 120 for item in result["evidence"]))


if __name__ == "__main__":
    unittest.main()
