"""T8 双写对比测试：GPTFactory/UniversalGPT vs notemeld-ai。

§7.1 §7.2 §7.5 验收门禁：
- 同 prompt 走两条路径，对比最终 ``insert_usage_record`` 的 payload
- 所有确定性字段必须逐字段相等（task_id/provider_id/model_name/phase/platform/
  video_id/video_title/prompt_tokens/completion_tokens/total_tokens/status/
  error_message/request_meta_json）
- §7.2 流式只写一条 usage

设计：
- 两条路径都最终调用 ``insert_usage_record(payload)`` 写入 DB
  - 旧路径：``UniversalGPT._record_usage`` → ``insert_usage_record``（直接调用）
  - 新路径：``UsageWriter.write`` → ``record_usage`` → ``insert_usage_record``
- 用同一份 canned OpenAI response 喂给两条路径
- patch 两个 import 点的 ``insert_usage_record``，捕获 payload 对比
"""
from __future__ import annotations

import asyncio
import json
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
from app.ai.provider import LLMContext, ProviderConfig  # noqa: E402
from app.ai.stream import CompleteResult, StreamEvent, StreamEventType  # noqa: E402
from app.ai.tool import Type, Tool  # noqa: E402
from app.ai.usage import Usage, UsageContext, UsageWriter  # noqa: E402
from app.gpt.universal_gpt import UniversalGPT  # noqa: E402
from app.gpt.notemeld_gpt import NotemeldGPT  # noqa: E402
from app.models.model_config import ModelConfig  # noqa: E402


# ── 公共测试夹具 ──────────────────────────────────────────────

PROVIDER_ID = "prov_test_001"
PROVIDER_NAME = "DeepSeek"
MODEL_NAME = "deepseek-chat"
TASK_ID = "task_compat_001"
PLATFORM = "douyin"
VIDEO_ID = "vid_compat_001"
VIDEO_TITLE = "双写对比测试视频"
PHASE = "summarize"
PROMPT_TOKENS = 123
COMPLETION_TOKENS = 45
TOTAL_TOKENS = PROMPT_TOKENS + COMPLETION_TOKENS

# 注意：刻意不包含 "stage" 键。旧路径 UniversalGPT 会用
# ``request_meta.stage`` 覆盖 ``phase`` 字段（见 create_chat_completion 中
# ``stage = request_meta.get("stage") or usage_context.phase or phase_label``），
# 而 notemeld-ai 直接用 ``usage_context.phase``。
# ``stage`` 字段的迁移处理由 T9-T11 调用点迁移负责（要么改传 usage_context.phase，
# 要么扩展 notemeld-ai 读 request_meta.stage）。这里验证基础等价性。
REQUEST_META = {"response_format": "default", "chunk_index": 0}


def make_canned_openai_response():
    """构造统一的 OpenAI 非流式响应，两条路径都看同一份。"""
    usage = SimpleNamespace(
        prompt_tokens=PROMPT_TOKENS,
        completion_tokens=COMPLETION_TOKENS,
        total_tokens=TOTAL_TOKENS,
    )
    message = SimpleNamespace(content="这是 AI 生成的笔记内容", tool_calls=None)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=usage)


def make_canned_stream_chunks():
    """构造统一的 OpenAI 流式 chunk 序列。"""
    usage = SimpleNamespace(
        prompt_tokens=PROMPT_TOKENS,
        completion_tokens=COMPLETION_TOKENS,
        total_tokens=TOTAL_TOKENS,
    )
    return [
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="这是 ", tool_calls=None))], usage=None),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="笔记", tool_calls=None))], usage=None),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="内容", tool_calls=None))], usage=usage),
    ]


# 旧路径 UniversalGPT 期望的 usage_context 字段
LEGACY_USAGE_CONTEXT = {
    "provider_id": PROVIDER_ID,
    "provider_name": PROVIDER_NAME,
    "phase": PHASE,
    "task_id": TASK_ID,
    "platform": PLATFORM,
    "video_id": VIDEO_ID,
    "video_title": VIDEO_TITLE,
    "request_meta": REQUEST_META,
}

# notemeld-ai 路径 options.usage_context 字段
NEW_USAGE_CONTEXT = {
    "phase": PHASE,
    "task_id": TASK_ID,
    "platform": PLATFORM,
    "video_id": VIDEO_ID,
    "video_title": VIDEO_TITLE,
    "request_meta": REQUEST_META,
}


# ── 旧路径：UniversalGPT.create_chat_completion ──────────────

class LegacyPathTest(unittest.TestCase):
    """通过 UniversalGPT 走旧路径，捕获 insert_usage_record payload。"""

    def _run_legacy_non_stream(self, response, request_meta=None):
        """跑一次旧路径非流式调用，返回 insert_usage_record 的 payload。"""
        fake_client = MagicMock()
        fake_client.with_options.return_value = fake_client
        fake_client.chat.completions.create = MagicMock(return_value=response)

        gpt = UniversalGPT(
            client=fake_client,
            model=MODEL_NAME,
            usage_context=dict(LEGACY_USAGE_CONTEXT),
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            base_url="https://api.deepseek.com/v1",
        )

        captured = []
        def capture(payload):
            captured.append(payload)

        messages = [{"role": "user", "content": "请生成笔记"}]
        with patch("app.gpt.universal_gpt.insert_usage_record", side_effect=capture):
            gpt.create_chat_completion(
                messages=messages,
                phase_label=PHASE,
                request_meta=request_meta or REQUEST_META,
            )

        self.assertEqual(len(captured), 1, "旧路径非流式应只写一条 usage")
        return captured[0]

    def test_legacy_non_stream_payload_has_all_required_fields(self):
        """§7.1 §7.5：旧路径 payload 必须包含 ModelUsageRecord 全部字段。"""
        payload = self._run_legacy_non_stream(make_canned_openai_response())

        # 全字段存在性检查（与 ModelUsageRecord ORM 字段对齐）
        required_fields = {
            "task_id", "provider_id", "provider_name", "model_name", "phase",
            "platform", "video_id", "video_title",
            "prompt_tokens", "completion_tokens", "total_tokens",
            "status", "error_message",
            "request_started_at", "request_finished_at", "duration_ms",
            "request_meta_json",
        }
        self.assertTrue(required_fields.issubset(payload.keys()), f"缺失字段: {required_fields - set(payload.keys())}")

        # 确定性字段值
        self.assertEqual(payload["task_id"], TASK_ID)
        self.assertEqual(payload["provider_id"], PROVIDER_ID)
        self.assertEqual(payload["provider_name"], PROVIDER_NAME)
        self.assertEqual(payload["model_name"], MODEL_NAME)
        self.assertEqual(payload["phase"], PHASE)
        self.assertEqual(payload["platform"], PLATFORM)
        self.assertEqual(payload["video_id"], VIDEO_ID)
        self.assertEqual(payload["video_title"], VIDEO_TITLE)
        self.assertEqual(payload["prompt_tokens"], PROMPT_TOKENS)
        self.assertEqual(payload["completion_tokens"], COMPLETION_TOKENS)
        self.assertEqual(payload["total_tokens"], TOTAL_TOKENS)
        self.assertEqual(payload["status"], "success")
        self.assertIsNone(payload["error_message"])

        # request_meta_json 是 JSON 字符串
        meta = json.loads(payload["request_meta_json"])
        self.assertEqual(meta["response_format"], REQUEST_META["response_format"])
        self.assertEqual(meta["chunk_index"], REQUEST_META["chunk_index"])

    def test_legacy_failed_payload_uses_status_failed(self):
        """旧路径请求失败时也应写一条 status=failed 的 usage。"""
        fake_client = MagicMock()
        fake_client.with_options.return_value = fake_client
        fake_client.chat.completions.create = MagicMock(side_effect=RuntimeError("network down"))

        gpt = UniversalGPT(
            client=fake_client,
            model=MODEL_NAME,
            usage_context=dict(LEGACY_USAGE_CONTEXT),
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            base_url="https://api.deepseek.com/v1",
        )

        captured = []
        with patch("app.gpt.universal_gpt.insert_usage_record", side_effect=lambda p: captured.append(p)):
            with self.assertRaises(RuntimeError):
                gpt.create_chat_completion(
                    messages=[{"role": "user", "content": "x"}],
                    phase_label=PHASE,
                )

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["status"], "failed")
        self.assertIsNone(captured[0]["prompt_tokens"])
        self.assertIsNone(captured[0]["completion_tokens"])
        self.assertIsNone(captured[0]["total_tokens"])


# ── 新路径：notemeld-ai Models.complete ──────────────────────

class NewPathTest(unittest.TestCase):
    """通过 notemeld-ai Models 走新路径，捕获 insert_usage_record payload。"""

    def _make_models_with_fake_provider(self, *, response, caps_tool_calling=True):
        """构造 Models 实例 + 注入 fake AsyncOpenAI provider。"""
        from app.ai.provider import OpenAICompatibleProvider

        config = ProviderConfig(
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
        )
        provider = OpenAICompatibleProvider(config)

        # 替换内部 AsyncOpenAI client
        fake_async_client = MagicMock()
        fake_async_client.chat = MagicMock()
        fake_async_client.chat.completions = MagicMock()
        fake_async_client.chat.completions.create = AsyncMock(return_value=response)
        provider._client = fake_async_client

        models = Models(model_service=MagicMock())
        model = Model(
            provider=provider,
            name=MODEL_NAME,
            capabilities=ModelCapabilities(supports_tool_calling=caps_tool_calling),
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
        )
        models._test_model = model
        return models, model

    def _run_new_non_stream(self, response):
        models, model = self._make_models_with_fake_provider(response=response)

        captured = []
        def capture(payload):
            captured.append(payload)

        with patch("app.services.usage_tracker.insert_usage_record", side_effect=capture):
            result = asyncio.run(models.complete(
                model,
                LLMContext(messages=[{"role": "user", "content": "请生成笔记"}]),
                options={"usage_context": dict(NEW_USAGE_CONTEXT)},
            ))

        self.assertEqual(len(captured), 1, "新路径非流式应只写一条 usage")
        return captured[0], result

    def test_new_non_stream_payload_has_all_required_fields(self):
        """§7.1 §7.5：新路径 payload 字段集合与 ORM 对齐。"""
        payload, _ = self._run_new_non_stream(make_canned_openai_response())

        required_fields = {
            "task_id", "provider_id", "provider_name", "model_name", "phase",
            "platform", "video_id", "video_title",
            "prompt_tokens", "completion_tokens", "total_tokens",
            "status", "error_message",
            "request_started_at", "request_finished_at", "duration_ms",
            "request_meta_json",
        }
        self.assertTrue(required_fields.issubset(payload.keys()), f"缺失字段: {required_fields - set(payload.keys())}")

        self.assertEqual(payload["task_id"], TASK_ID)
        self.assertEqual(payload["provider_id"], PROVIDER_ID)
        self.assertEqual(payload["provider_name"], PROVIDER_NAME)
        self.assertEqual(payload["model_name"], MODEL_NAME)
        self.assertEqual(payload["phase"], PHASE)
        self.assertEqual(payload["platform"], PLATFORM)
        self.assertEqual(payload["video_id"], VIDEO_ID)
        self.assertEqual(payload["video_title"], VIDEO_TITLE)
        self.assertEqual(payload["prompt_tokens"], PROMPT_TOKENS)
        self.assertEqual(payload["completion_tokens"], COMPLETION_TOKENS)
        self.assertEqual(payload["total_tokens"], TOTAL_TOKENS)
        self.assertEqual(payload["status"], "success")
        self.assertIsNone(payload["error_message"])

        meta = json.loads(payload["request_meta_json"])
        self.assertEqual(meta["response_format"], REQUEST_META["response_format"])
        self.assertEqual(meta["chunk_index"], REQUEST_META["chunk_index"])

    def test_new_failed_payload_uses_status_failed(self):
        """新路径请求失败时也应写一条 status=failed 的 usage。"""
        from app.ai.provider import OpenAICompatibleProvider

        config = ProviderConfig(
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
        )
        provider = OpenAICompatibleProvider(config)
        exc = RuntimeError("network down")
        fake_async_client = MagicMock()
        fake_async_client.chat = MagicMock()
        fake_async_client.chat.completions = MagicMock()
        fake_async_client.chat.completions.create = AsyncMock(side_effect=exc)
        provider._client = fake_async_client

        models = Models(model_service=MagicMock())
        model = Model(
            provider=provider,
            name=MODEL_NAME,
            capabilities=ModelCapabilities(supports_tool_calling=True),
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
        )
        models._test_model = model

        captured = []
        with patch("app.services.usage_tracker.insert_usage_record", side_effect=lambda p: captured.append(p)):
            with self.assertRaises(RuntimeError):
                asyncio.run(models.complete(
                    model,
                    LLMContext(messages=[{"role": "user", "content": "x"}]),
                    options={"usage_context": dict(NEW_USAGE_CONTEXT)},
                ))

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["status"], "failed")
        self.assertIsNone(captured[0]["prompt_tokens"])


# ── §7.2 流式只写一条 usage（新路径） ─────────────────────────

class StreamSingleUsageTest(unittest.TestCase):
    """§7.2：notemeld-ai 流式调用全程只写一条 usage（在 done 事件触发）。"""

    def test_stream_writes_exactly_one_usage_on_success(self):
        from app.ai.provider import OpenAICompatibleProvider

        config = ProviderConfig(
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
        )
        provider = OpenAICompatibleProvider(config)

        chunks = make_canned_stream_chunks()

        async def fake_create(**kwargs):
            async def _aiter():
                for c in chunks:
                    yield c
            return _aiter()

        fake_async_client = MagicMock()
        fake_async_client.chat = MagicMock()
        fake_async_client.chat.completions = MagicMock()
        fake_async_client.chat.completions.create = AsyncMock(side_effect=fake_create)
        provider._client = fake_async_client

        models = Models(model_service=MagicMock())
        model = Model(
            provider=provider,
            name=MODEL_NAME,
            capabilities=ModelCapabilities(supports_tool_calling=True),
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
        )

        captured = []
        with patch("app.services.usage_tracker.insert_usage_record", side_effect=lambda p: captured.append(p)):
            async def consume():
                async for _ in models.stream(
                    model,
                    LLMContext(messages=[{"role": "user", "content": "hi"}]),
                    options={"usage_context": dict(NEW_USAGE_CONTEXT)},
                ):
                    pass
            asyncio.run(consume())

        self.assertEqual(len(captured), 1, "§7.2 流式应只写一条 usage")
        payload = captured[0]
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["prompt_tokens"], PROMPT_TOKENS)
        self.assertEqual(payload["completion_tokens"], COMPLETION_TOKENS)
        self.assertEqual(payload["total_tokens"], TOTAL_TOKENS)


class RuntimeConfigPropagationTest(unittest.TestCase):
    """保存的运行配置必须经 ModelConfig 进入 UniversalGPT 编排层。"""

    def test_notemeld_gpt_from_config_preserves_runtime_fields(self):
        config = ModelConfig(
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
            model_name=MODEL_NAME,
            provider=PROVIDER_ID,
            name=PROVIDER_NAME,
            context_window_tokens=131072,
            supports_vision=True,
            supports_stream=False,
        )

        with patch("app.gpt.notemeld_gpt.OpenAICompatibleProvider") as provider_cls:
            provider_cls.return_value.get_client = MagicMock()
            gpt = NotemeldGPT.from_config(config)

        self.assertEqual(gpt.context_window_tokens, 131072)
        self.assertIs(gpt.supports_vision, True)
        self.assertIs(gpt.supports_stream, False)

    def test_note_generator_loads_saved_runtime_fields_into_model_config(self):
        from app.services.note import NoteGenerator

        provider = {
            "id": PROVIDER_ID,
            "name": PROVIDER_NAME,
            "api_key": "sk-test",
            "base_url": "https://api.deepseek.com/v1",
        }
        saved_model = {
            "provider_id": PROVIDER_ID,
            "model_name": MODEL_NAME,
            "context_window_tokens": 65536,
            "supports_vision": False,
            "supports_stream": False,
        }

        with patch("app.services.note.ProviderService.get_provider_by_id", return_value=provider), \
             patch("app.services.note.ModelService.get_saved_model", return_value=saved_model), \
             patch("app.services.note.NotemeldGPT.from_config", return_value=MagicMock()) as from_config:
            NoteGenerator.__new__(NoteGenerator)._get_gpt(MODEL_NAME, PROVIDER_ID)

        config = from_config.call_args.args[0]
        self.assertEqual(config.context_window_tokens, 65536)
        self.assertIs(config.supports_vision, False)
        self.assertIs(config.supports_stream, False)


# ── §7.1 §7.5 双写逐字段对比 ─────────────────────────────────

class DualWriteFieldEquivalenceTest(unittest.TestCase):
    """§7.1 §7.5 核心门禁：同 prompt 双路径，逐字段断言 payload 等价。"""

    DETERMINISTIC_FIELDS = [
        "task_id", "provider_id", "provider_name", "model_name", "phase",
        "platform", "video_id", "video_title",
        "prompt_tokens", "completion_tokens", "total_tokens",
        "status", "error_message",
    ]

    def test_non_stream_dual_write_field_equivalence(self):
        """非流式：同 prompt 走 GPTFactory 和 notemeld-ai，逐字段断言 usage 一致。"""
        canned = make_canned_openai_response()

        # ── 旧路径 ──
        legacy_client = MagicMock()
        legacy_client.with_options.return_value = legacy_client
        legacy_client.chat.completions.create = MagicMock(return_value=canned)
        legacy_gpt = UniversalGPT(
            client=legacy_client,
            model=MODEL_NAME,
            usage_context=dict(LEGACY_USAGE_CONTEXT),
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            base_url="https://api.deepseek.com/v1",
        )
        legacy_payloads = []
        with patch("app.gpt.universal_gpt.insert_usage_record", side_effect=lambda p: legacy_payloads.append(p)):
            legacy_gpt.create_chat_completion(
                messages=[{"role": "user", "content": "请生成笔记"}],
                phase_label=PHASE,
                request_meta=REQUEST_META,
            )

        # ── 新路径 ──
        from app.ai.provider import OpenAICompatibleProvider
        config = ProviderConfig(
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
        )
        new_provider = OpenAICompatibleProvider(config)
        fake_async_client = MagicMock()
        fake_async_client.chat = MagicMock()
        fake_async_client.chat.completions = MagicMock()
        # 注意：新路径拿到的是同一个 canned response 对象
        fake_async_client.chat.completions.create = AsyncMock(return_value=canned)
        new_provider._client = fake_async_client

        models = Models(model_service=MagicMock())
        model = Model(
            provider=new_provider,
            name=MODEL_NAME,
            capabilities=ModelCapabilities(supports_tool_calling=True),
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
        )

        new_payloads = []
        with patch("app.services.usage_tracker.insert_usage_record", side_effect=lambda p: new_payloads.append(p)):
            asyncio.run(models.complete(
                model,
                LLMContext(messages=[{"role": "user", "content": "请生成笔记"}]),
                options={"usage_context": dict(NEW_USAGE_CONTEXT)},
            ))

        # ── 逐字段断言 ──
        self.assertEqual(len(legacy_payloads), 1)
        self.assertEqual(len(new_payloads), 1)
        legacy = legacy_payloads[0]
        new = new_payloads[0]

        for field in self.DETERMINISTIC_FIELDS:
            self.assertEqual(
                legacy[field], new[field],
                f"字段 {field} 不一致: legacy={legacy[field]!r} new={new[field]!r}",
            )

        # request_meta_json：JSON 字符串解析后比对（key 顺序可能不同）
        legacy_meta = json.loads(legacy["request_meta_json"])
        new_meta = json.loads(new["request_meta_json"])
        self.assertEqual(legacy_meta, new_meta, "request_meta_json 解析后内容不一致")

        # 非确定性字段：类型与基本约束一致
        for field in ("request_started_at", "request_finished_at"):
            self.assertIsNotNone(legacy[field], f"legacy {field} 不应为 None")
            self.assertIsNotNone(new[field], f"new {field} 不应为 None")
            # 两条路径时间戳都应该是 datetime 实例
            from datetime import datetime
            self.assertIsInstance(legacy[field], datetime)
            self.assertIsInstance(new[field], datetime)

        for field in ("duration_ms",):
            self.assertIsInstance(legacy[field], int)
            self.assertIsInstance(new[field], int)
            self.assertGreaterEqual(legacy[field], 0)
            self.assertGreaterEqual(new[field], 0)

    def test_non_stream_dual_write_field_count_matches_orm(self):
        """§7.5：双路径 payload 字段集合必须与 ModelUsageRecord ORM 完全对齐。"""
        # ORM 期望的全部业务字段（不含 id 和 created_at，它们由 DB 自动生成）
        orm_fields = {
            "task_id", "provider_id", "provider_name", "model_name", "phase",
            "platform", "video_id", "video_title",
            "prompt_tokens", "completion_tokens", "total_tokens",
            "status", "error_message",
            "request_started_at", "request_finished_at", "duration_ms",
            "request_meta_json",
        }

        canned = make_canned_openai_response()

        # 旧路径
        legacy_client = MagicMock()
        legacy_client.with_options.return_value = legacy_client
        legacy_client.chat.completions.create = MagicMock(return_value=canned)
        legacy_gpt = UniversalGPT(
            client=legacy_client,
            model=MODEL_NAME,
            usage_context=dict(LEGACY_USAGE_CONTEXT),
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            base_url="https://api.deepseek.com/v1",
        )
        legacy_payloads = []
        with patch("app.gpt.universal_gpt.insert_usage_record", side_effect=lambda p: legacy_payloads.append(p)):
            legacy_gpt.create_chat_completion(
                messages=[{"role": "user", "content": "x"}],
                phase_label=PHASE,
                request_meta=REQUEST_META,
            )

        # 新路径
        from app.ai.provider import OpenAICompatibleProvider
        config = ProviderConfig(
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
        )
        new_provider = OpenAICompatibleProvider(config)
        fake_async_client = MagicMock()
        fake_async_client.chat = MagicMock()
        fake_async_client.chat.completions = MagicMock()
        fake_async_client.chat.completions.create = AsyncMock(return_value=canned)
        new_provider._client = fake_async_client

        models = Models(model_service=MagicMock())
        model = Model(
            provider=new_provider,
            name=MODEL_NAME,
            capabilities=ModelCapabilities(supports_tool_calling=True),
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
        )
        new_payloads = []
        with patch("app.services.usage_tracker.insert_usage_record", side_effect=lambda p: new_payloads.append(p)):
            asyncio.run(models.complete(
                model,
                LLMContext(messages=[{"role": "user", "content": "x"}]),
                options={"usage_context": dict(NEW_USAGE_CONTEXT)},
            ))

        self.assertEqual(set(legacy_payloads[0].keys()), orm_fields,
                         "旧路径 payload 字段集合与 ORM 不一致")
        self.assertEqual(set(new_payloads[0].keys()), orm_fields,
                         "新路径 payload 字段集合与 ORM 不一致")


# ── §7.3 双路径能力检查行为一致 ──────────────────────────────

class CapabilityCheckCompatTest(unittest.TestCase):
    """§7.3 兼容性：旧路径不检查能力（直接传给 LLM 由其报错），新路径主动检查。

    本测试明确记录这一行为差异是设计意图，避免被误判为回归。
    """

    def test_legacy_path_does_not_pre_check_tool_capability(self):
        """旧路径 UniversalGPT 不在请求前检查 tool 能力，直接发给 LLM。"""
        # 旧路径 UniversalGPT 没有任何 capability pre-check 逻辑
        # 这是设计意图：notemeld-ai 主动检查是新引入的能力，不是回归
        import inspect
        src = inspect.getsource(UniversalGPT)
        self.assertNotIn("supports_tool_calling", src)
        self.assertNotIn("ProviderCapabilityError", src)

    def test_new_path_pre_checks_tool_capability(self):
        """新路径 notemeld-ai 在请求前检查能力，避免浪费 API 调用。"""
        from app.ai.errors import ProviderCapabilityError

        # 构造一个不支持 tool calling 的 Model
        fake_provider = MagicMock()
        fake_provider.complete = AsyncMock(return_value=CompleteResult(content="ok"))

        models = Models(model_service=MagicMock())
        model = Model(
            provider=fake_provider,
            name=MODEL_NAME,
            capabilities=ModelCapabilities(supports_tool_calling=False),
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
        )

        ctx = LLMContext(
            messages=[{"role": "user", "content": "hi"}],
            tools=[Tool(name="fn", description="d", parameters=Type.Object(properties={}))],
        )

        with self.assertRaises(ProviderCapabilityError):
            asyncio.run(models.complete(model, ctx))
        # Provider 完全没被调用
        fake_provider.complete.assert_not_called()


# ── T9 迁移注意：legacy phase 优先级 ─────────────────────────

class LegacyPhasePrecedenceTest(unittest.TestCase):
    """记录旧路径 phase 字段的 3 级优先级，T9-T11 迁移调用点时必须处理。

    旧路径 ``UniversalGPT.create_chat_completion`` 中：
        stage = (request_meta or {}).get("stage") or usage_context.phase or phase_label
    即 ``request_meta.stage`` > ``usage_context.phase`` > ``phase_label``。

    notemeld-ai 当前只用 ``usage_context.phase``，不读 ``request_meta.stage``。

    T9-T11 迁移时二选一：
    A) 调用方把 ``stage`` 直接传 ``usage_context.phase``（推荐，最小改动）
    B) 扩展 ``Models._build_usage_context`` 读 ``request_meta.stage`` 做回退
    """

    def test_legacy_phase_uses_request_meta_stage_when_present(self):
        """旧路径：request_meta.stage 覆盖 usage_context.phase。"""
        canned = make_canned_openai_response()
        client = MagicMock()
        client.with_options.return_value = client
        client.chat.completions.create = MagicMock(return_value=canned)

        gpt = UniversalGPT(
            client=client,
            model=MODEL_NAME,
            usage_context={**LEGACY_USAGE_CONTEXT, "phase": "summarize"},
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            base_url="https://api.deepseek.com/v1",
        )

        captured = []
        with patch("app.gpt.universal_gpt.insert_usage_record", side_effect=lambda p: captured.append(p)):
            gpt.create_chat_completion(
                messages=[{"role": "user", "content": "x"}],
                phase_label="fallback_label",
                request_meta={"stage": "chunk_1"},
            )

        self.assertEqual(captured[0]["phase"], "chunk_1")

    def test_legacy_phase_falls_back_to_usage_context_phase(self):
        """旧路径：request_meta 无 stage 时用 usage_context.phase。"""
        canned = make_canned_openai_response()
        client = MagicMock()
        client.with_options.return_value = client
        client.chat.completions.create = MagicMock(return_value=canned)

        gpt = UniversalGPT(
            client=client,
            model=MODEL_NAME,
            usage_context={**LEGACY_USAGE_CONTEXT, "phase": "summarize"},
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            base_url="https://api.deepseek.com/v1",
        )

        captured = []
        with patch("app.gpt.universal_gpt.insert_usage_record", side_effect=lambda p: captured.append(p)):
            gpt.create_chat_completion(
                messages=[{"role": "user", "content": "x"}],
                phase_label="fallback_label",
                request_meta={"chunk_index": 0},  # 无 stage
            )

        self.assertEqual(captured[0]["phase"], "summarize")

    def test_legacy_phase_falls_back_to_phase_label(self):
        """旧路径：request_meta 无 stage 且 usage_context 无 phase 时用 phase_label。"""
        canned = make_canned_openai_response()
        client = MagicMock()
        client.with_options.return_value = client
        client.chat.completions.create = MagicMock(return_value=canned)

        gpt = UniversalGPT(
            client=client,
            model=MODEL_NAME,
            usage_context={"provider_id": PROVIDER_ID, "provider_name": PROVIDER_NAME},  # 无 phase
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            base_url="https://api.deepseek.com/v1",
        )

        captured = []
        with patch("app.gpt.universal_gpt.insert_usage_record", side_effect=lambda p: captured.append(p)):
            gpt.create_chat_completion(
                messages=[{"role": "user", "content": "x"}],
                phase_label="merge",
                request_meta={"chunk_index": 0},
            )

        self.assertEqual(captured[0]["phase"], "merge")


if __name__ == "__main__":
    unittest.main()
