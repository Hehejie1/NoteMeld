"""T11 迁移测试：wiki_page_merger / summary_refine_engine / web_note /
template_extraction / style_service 走 notemeld-ai 适配器。

验收标准覆盖：
- §T11.1 wiki_page_merger.merge() 走 gpt.create_chat_completion（不再用 gpt.client）
- §T11.2 web_note._get_gpt 用 NotemeldGPT.from_config
- §T11.3 routers/note.py::retry_wiki_extraction 用 NotemeldGPT.from_config
- §T11.4 summary_refine_engine 用 gpt.summarize（继承自 UniversalGPT，自动走 override）
- §T11.5 note_style 模板提取 / image_vlm_analyzer 走 NoteGenerator()._get_gpt（T10 已切 NotemeldGPT）
- §T11.6 services/ 下无残留 gpt.client.chat.completions.create 调用（chat 路径全走适配器）

设计：
- 源码级验证：读取 .py 源文件，确认 import / 调用点已切到 NotemeldGPT / create_chat_completion
- 运行时验证：wiki_page_merger.merge() 用注入 fake notemeld-ai 的 NotemeldGPT，确认走适配器
- 运行时验证：summary_refine_engine.run() 用 mock gpt，确认走 gpt.summarize（非 gpt.client）
"""
from __future__ import annotations

import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.catalog import ModelCapabilities  # noqa: E402
from app.ai.models import Model, Models  # noqa: E402
from app.ai.provider import LLMContext, OpenAICompatibleProvider, ProviderConfig  # noqa: E402
from app.gpt.notemeld_gpt import NotemeldGPT  # noqa: E402
from app.models.model_config import ModelConfig  # noqa: E402
from app.models.summary_plan import SummaryPlan  # noqa: E402
from app.models.transcriber_model import TranscriptSegment  # noqa: E402
from app.services.summary_refine_engine import SummaryRefineEngine  # noqa: E402
from app.services.wiki_page_merger import WikiPageMerger  # noqa: E402


# ── 公共常量 ──────────────────────────────────────────────────

PROVIDER_ID = "prov_t11_001"
PROVIDER_NAME = "DeepSeek"
MODEL_NAME = "deepseek-chat"
TASK_ID = "task_t11_001"
PROMPT_TOKENS = 100
COMPLETION_TOKENS = 40
TOTAL_TOKENS = PROMPT_TOKENS + COMPLETION_TOKENS


def make_canned_openai_response(content="合并后的 Markdown"):
    """构造 OpenAI 形状响应（provider.complete() 内部会转为 CompleteResult）。"""
    usage = SimpleNamespace(
        prompt_tokens=PROMPT_TOKENS,
        completion_tokens=COMPLETION_TOKENS,
        total_tokens=TOTAL_TOKENS,
    )
    message = SimpleNamespace(content=content, tool_calls=None)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=usage)


def make_fake_models(response=None, *, exc=None):
    """构造 Models 实例，内部 provider 注入 fake AsyncOpenAI client。"""
    config = ProviderConfig(
        provider_id=PROVIDER_ID,
        provider_name=PROVIDER_NAME,
        api_key="sk-test",
        base_url="https://api.deepseek.com/v1",
    )
    provider = OpenAICompatibleProvider(config)

    fake_async_client = MagicMock()
    fake_async_client.chat = MagicMock()
    fake_async_client.chat.completions = MagicMock()
    if exc is not None:
        fake_async_client.chat.completions.create = AsyncMock(side_effect=exc)
    else:
        fake_async_client.chat.completions.create = AsyncMock(return_value=response)
    provider._client = fake_async_client

    models = Models(model_service=MagicMock())
    model = Model(
        provider=provider,
        name=MODEL_NAME,
        capabilities=ModelCapabilities(supports_tool_calling=True),
        provider_id=PROVIDER_ID,
        provider_name=PROVIDER_NAME,
    )
    models.get_model = MagicMock(return_value=model)
    return models, model


def make_usage_context(phase="wiki_merge"):
    return {
        "task_id": TASK_ID,
        "provider_id": PROVIDER_ID,
        "provider_name": PROVIDER_NAME,
        "phase": phase,
        "platform": "web_link",
        "video_id": TASK_ID,
        "video_title": "T11 测试",
        "request_meta": {},
    }


def make_gpt(usage_context=None):
    return NotemeldGPT(
        client=MagicMock(),
        model=MODEL_NAME,
        usage_context=usage_context or make_usage_context(),
        provider_id=PROVIDER_ID,
        provider_name=PROVIDER_NAME,
        base_url="https://api.deepseek.com/v1",
    )


# ── §T11.1 wiki_page_merger 运行时验证 ────────────────────────

class WikiPageMergerMigrationTest(unittest.TestCase):
    """wiki_page_merger.merge() 走 gpt.create_chat_completion，不走 gpt.client。"""

    def test_merge_calls_create_chat_completion_not_self_client(self):
        """merge() 调 gpt.create_chat_completion（走 notemeld-ai），不调 gpt.client。"""
        canned = make_canned_openai_response("# 合并页面\n\n内容")
        models, _ = make_fake_models(response=canned)
        gpt = make_gpt()

        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record"):
            result = WikiPageMerger().merge(
                page_type="concept",
                page_title="测试页",
                current_markdown="# 旧内容",
                contribution_payload=[{"claim": "新事实"}],
                gpt=gpt,
                fallback_markdown="FALLBACK",
            )

        # notemeld-ai provider 的 AsyncOpenAI client 被调（走适配器）
        model_provider = models.get_model.return_value.provider
        model_provider._client.chat.completions.create.assert_called_once()
        # self.client（旧 OpenAI sync client）没被调
        gpt.client.chat.completions.create.assert_not_called()
        # 返回 LLM 内容（非 fallback）
        self.assertEqual(result, "# 合并页面\n\n内容")

    def test_merge_fallback_on_llm_failure(self):
        """LLM 失败时返回 fallback_markdown，不抛出。"""
        models, _ = make_fake_models(exc=RuntimeError("non-retryable"))
        gpt = make_gpt()

        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record"):
            result = WikiPageMerger().merge(
                page_type="concept",
                page_title="测试页",
                current_markdown="",
                contribution_payload=[],
                gpt=gpt,
                fallback_markdown="FALLBACK",
            )

        self.assertEqual(result, "FALLBACK")

    def test_merge_no_gpt_returns_fallback(self):
        """无 gpt 或 gpt 无 model 时直接返回 fallback。"""
        result = WikiPageMerger().merge(
            page_type="concept",
            page_title="测试页",
            current_markdown="",
            contribution_payload=[],
            gpt=None,
            fallback_markdown="FALLBACK",
        )
        self.assertEqual(result, "FALLBACK")


# ── §T11.4 summary_refine_engine 路由验证 ────────────────────

class SummaryRefineEngineRoutingTest(unittest.TestCase):
    """summary_refine_engine.run() 走 gpt.summarize（继承自 UniversalGPT，自动走 override）。"""

    def test_run_calls_gpt_summarize_not_self_client(self):
        """run() 调 gpt.summarize（非 gpt.client），map + final 各至少一次。"""
        # 用 mock gpt，记录 summarize 调用，确认路由路径
        mock_gpt = MagicMock()
        mock_gpt.summarize = MagicMock(return_value="片段摘要")
        mock_gpt.client = MagicMock()  # 旧 client，不应被调

        segments = [TranscriptSegment(start=0.0, end=5.0, text="第一段内容")]
        plan = SummaryPlan(
            input_id=TASK_ID,
            output_type="note_markdown",
            strategy="single",
            chunk_policy={"max_segments_per_chunk": 80},
        )

        result = SummaryRefineEngine().run(
            task_id=TASK_ID,
            title="测试视频",
            segments=segments,
            gpt=mock_gpt,
            plan=plan,
            video_img_urls=[],
        )

        # gpt.summarize 被调（map 阶段 1 次 + final 阶段 1 次 = 至少 2 次）
        self.assertGreaterEqual(mock_gpt.summarize.call_count, 2)
        # gpt.client 没被调（确认不走旧路径）
        mock_gpt.client.chat.completions.create.assert_not_called()
        # 返回 RefineResult
        self.assertEqual(result.task_id, TASK_ID)
        self.assertEqual(result.markdown, "片段摘要")

    def test_run_multi_chunk_summarize_count(self):
        """多 chunk 场景：map 阶段 summarize 次数 = chunk 数，final 阶段 1 次。"""
        mock_gpt = MagicMock()
        mock_gpt.summarize = MagicMock(return_value="摘要")

        # 3 段，每 chunk 最多 1 段 → 3 个 chunk
        segments = [
            TranscriptSegment(start=float(i), end=float(i + 1), text=f"第{i + 1}段")
            for i in range(3)
        ]
        plan = SummaryPlan(
            input_id=TASK_ID,
            output_type="note_markdown",
            strategy="map_reduce",
            chunk_policy={"max_segments_per_chunk": 1},
        )

        SummaryRefineEngine().run(
            task_id=TASK_ID,
            title="测试",
            segments=segments,
            gpt=mock_gpt,
            plan=plan,
            video_img_urls=[],
        )

        # 3 次 map + 1 次 final = 4 次
        self.assertEqual(mock_gpt.summarize.call_count, 4)


# ── §T11.2 / §T11.3 / §T11.5 源码级验证 ──────────────────────

class SourceLevelMigrationTest(unittest.TestCase):
    """源码级验证：5 个 T11 模块的调用点已切到 NotemeldGPT / create_chat_completion。"""

    def _read(self, *parts: str) -> str:
        return (ROOT / "app" / pathlib.Path(*parts)).read_text(encoding="utf-8")

    def test_wiki_page_merger_uses_create_chat_completion(self):
        """§T11.1 wiki_page_merger.py 用 gpt.create_chat_completion，无 gpt.client 调用。"""
        src = self._read("services", "wiki_page_merger.py")
        self.assertIn("gpt.create_chat_completion(", src)
        # 不应有 gpt.client.chat.completions.create 调用（注释里的描述除外）
        for line in src.splitlines():
            stripped = line.split("#", 1)[0]  # 去掉注释
            self.assertNotIn("gpt.client.chat.completions.create", stripped)

    def test_web_note_get_gpt_uses_notemeld_gpt(self):
        """§T11.2 web_note.py._get_gpt 用 NotemeldGPT.from_config。"""
        src = self._read("services", "web_note.py")
        self.assertIn("from app.gpt.notemeld_gpt import NotemeldGPT", src)
        self.assertIn("NotemeldGPT.from_config(config)", src)

    def test_retry_wiki_extraction_uses_notemeld_gpt(self):
        """§T11.3 routers/note.py::retry_wiki_extraction 用 NotemeldGPT.from_config。"""
        src = self._read("routers", "note.py")
        # retry_wiki_extraction 函数内用 NotemeldGPT
        self.assertIn("from app.gpt.notemeld_gpt import NotemeldGPT", src)
        self.assertIn("NotemeldGPT.from_config(config)", src)
        # 不应在该函数的 GPT 创建处用 GPTFactory（回滚注释除外）
        for line in src.splitlines():
            stripped = line.split("#", 1)[0]
            if "GPTFactory().from_config" in stripped:
                self.fail(f"routers/note.py 仍有 GPTFactory().from_config 调用: {line.strip()}")

    def test_summary_refine_engine_uses_summarize(self):
        """§T11.4 summary_refine_engine.py 用 gpt.summarize，无 gpt.client 调用。"""
        src = self._read("services", "summary_refine_engine.py")
        self.assertIn("gpt.summarize(", src)
        for line in src.splitlines():
            stripped = line.split("#", 1)[0]
            self.assertNotIn("gpt.client.chat.completions.create", stripped)
            self.assertNotIn("GPTFactory", stripped)

    def test_note_style_template_extraction_routes_via_get_gpt(self):
        """§T11.5 routers/note_style.py 模板提取走 NoteGenerator()._get_gpt + create_chat_completion。"""
        src = self._read("routers", "note_style.py")
        self.assertIn("NoteGenerator()._get_gpt(", src)
        self.assertIn("gpt.create_chat_completion(", src)
        # 不应用 GPTFactory 创建 gpt
        for line in src.splitlines():
            stripped = line.split("#", 1)[0]
            self.assertNotIn("GPTFactory().from_config", stripped)

    def test_note_style_image_vlm_analyzer_routes_via_get_gpt(self):
        """§T11.5 note_style_image_vlm_analyzer.py 走 NoteGenerator()._get_gpt + create_chat_completion。"""
        src = self._read("services", "note_style_image_vlm_analyzer.py")
        self.assertIn("NoteGenerator()._get_gpt(", src)
        self.assertIn("gpt.create_chat_completion(", src)
        for line in src.splitlines():
            stripped = line.split("#", 1)[0]
            self.assertNotIn("GPTFactory().from_config", stripped)
            self.assertNotIn("gpt.client.chat.completions.create", stripped)


# ── §T11.6 services/ 无残留 gpt.client.chat 调用 ─────────────

class NoResidualGptClientUsageTest(unittest.TestCase):
    """services/ 下所有 chat 路径走 create_chat_completion，无 gpt.client.chat.completions.create。"""

    def test_no_gpt_client_chat_in_services(self):
        """扫描 services/ 目录，确认无 gpt.client.chat.completions.create 调用（注释除外）。"""
        services_dir = ROOT / "app" / "services"
        offenders = []
        for py_file in services_dir.glob("*.py"):
            src = py_file.read_text(encoding="utf-8")
            for lineno, line in enumerate(src.splitlines(), start=1):
                stripped = line.split("#", 1)[0]
                if "gpt.client.chat.completions.create" in stripped:
                    offenders.append(f"{py_file.name}:{lineno}: {line.strip()}")
        self.assertFalse(offenders, "services/ 下仍有 gpt.client.chat.completions.create 调用:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
