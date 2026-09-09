"""notemeld-ai Models 集成层单测。

覆盖 §7.1 §7.2 §7.3 §7.4：
- get_model：从 DB 读取 provider 配置，缓存 Provider 实例
- §7.3 能力检查：不支持 tools 的模型传 tools → ProviderCapabilityError
- §7.1 §7.2 stream/complete 自动写 usage（成功/失败各一条）
"""
from __future__ import annotations

import asyncio
import copy
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.errors import ProviderCapabilityError  # noqa: E402
from app.ai.models import Model, Models  # noqa: E402
from app.ai.provider import LLMContext  # noqa: E402
from app.ai.stream import CompleteResult, StreamEvent, StreamEventType  # noqa: E402
from app.ai.tool import Tool, Type  # noqa: E402
from app.ai.usage import Usage, UsageCost  # noqa: E402


class FakeProvider:
    """模拟 Provider，可控制 stream/complete 行为。"""

    def __init__(self, *, stream_events=None, complete_result=None, stream_exc=None, complete_exc=None):
        self.provider_id = "prov_1"
        self.provider_name = "DeepSeek"
        self._stream_events = stream_events or []
        self._complete_result = complete_result
        self._stream_exc = stream_exc
        self._complete_exc = complete_exc
        self.stream_calls = 0
        self.complete_calls = 0
        self.last_stream_context = None
        self.last_complete_context = None

    async def stream(self, model, ctx, signal=None):
        self.stream_calls += 1
        self.last_stream_context = ctx
        if self._stream_exc:
            raise self._stream_exc
        for ev in self._stream_events:
            yield ev

    async def complete(self, model, ctx, signal=None):
        self.complete_calls += 1
        self.last_complete_context = ctx
        if self._complete_exc:
            raise self._complete_exc
        return self._complete_result


def _make_models_with_provider(provider: FakeProvider, *, caps=None) -> Models:
    """构造 Models 实例，跳过 DB 调用，直接注入 Provider 与能力。"""
    models = Models(model_service=MagicMock())
    # 跳过 get_model 的 DB 读取，直接构造 Model
    model = Model(
        provider=provider,
        name="deepseek-chat",
        capabilities=caps if caps is not None else _caps(tool_calling=True),
        provider_id="prov_1",
        provider_name="DeepSeek",
        context_window_tokens=131072,
        supports_vision=False,
        supports_stream=True,
    )
    # 把 model 暴露给测试用
    models._test_model = model
    return models


def _caps(*, json_mode=None, vision=None, tool_calling=None):
    from app.ai.catalog import ModelCapabilities
    return ModelCapabilities(
        supports_json_mode=json_mode,
        supports_vision=vision,
        supports_tool_calling=tool_calling,
    )


def _run(coro):
    return asyncio.run(coro)


class ModelsGetModelTest(unittest.TestCase):
    def test_get_model_returns_none_when_model_is_not_saved(self):
        model_service = MagicMock()
        model_service.get_saved_model.return_value = None
        models = Models(model_service=model_service)
        with patch("app.ai.models.ProviderService.get_provider_by_id") as get_provider:
            result = models.get_model("missing", "m")
        self.assertIsNone(result)
        get_provider.assert_not_called()

    def test_get_model_returns_none_when_provider_missing(self):
        model_service = MagicMock()
        model_service.get_saved_model.return_value = {
            "provider_id": "missing",
            "model_name": "m",
            "context_window_tokens": 8192,
            "supports_vision": False,
            "supports_stream": True,
        }
        models = Models(model_service=model_service)
        with patch("app.ai.models.ProviderService.get_provider_by_id", return_value=None):
            result = models.get_model("missing", "m")
        self.assertIsNone(result)

    def test_get_model_loads_saved_runtime_fields_and_saved_vision_is_authoritative(self):
        model_service = MagicMock()
        model_service.get_saved_model.return_value = {
            "provider_id": "prov_1",
            "model_name": "deepseek-chat",
            "context_window_tokens": 131072,
            "supports_vision": False,
            "supports_stream": False,
        }
        models = Models(model_service=model_service)
        provider_row = {
            "id": "prov_1",
            "name": "DeepSeek",
            "api_key": "sk-xxx",
            "base_url": "https://api.deepseek.com/v1",
        }

        with patch.object(models, "_get_or_create_provider", return_value=MagicMock()), \
             patch("app.ai.models.ProviderService.get_provider_by_id", return_value=provider_row), \
             patch(
                 "app.ai.models.CapabilityCatalog.get",
                 return_value=_caps(json_mode=True, vision=True, tool_calling=True),
             ):
            model = models.get_model("prov_1", "deepseek-chat")

        self.assertIsNotNone(model)
        self.assertEqual(model.context_window_tokens, 131072)
        self.assertIs(model.supports_vision, False)
        self.assertIs(model.supports_stream, False)
        self.assertIs(model.capabilities.supports_vision, False)

    def test_get_model_caches_provider_instance(self):
        """同 provider_id 第二次调用应复用缓存的 Provider 实例。"""
        model_service = MagicMock()
        model_service.get_saved_model.return_value = {
            "provider_id": "prov_1",
            "model_name": "deepseek-chat",
            "context_window_tokens": 65536,
            "supports_vision": False,
            "supports_stream": True,
        }
        models = Models(model_service=model_service)
        provider_row = {
            "id": "prov_1",
            "name": "DeepSeek",
            "api_key": "sk-xxx",
            "base_url": "https://api.deepseek.com/v1",
        }

        created_clients = []

        # 用一个 fake OpenAICompatibleProvider 类替换
        with patch("app.ai.models.OpenAICompatibleProvider") as MockProvider, \
             patch("app.ai.models.ProviderService.get_provider_by_id", return_value=provider_row), \
             patch("app.ai.models.ModelService._resolve_api_key", return_value="sk-xxx"), \
             patch("app.ai.models.CapabilityCatalog.get", return_value=_caps()):
            def ctor(config):
                inst = MagicMock()
                inst.provider_id = config.provider_id
                inst.provider_name = config.provider_name
                created_clients.append(inst)
                return inst
            MockProvider.side_effect = ctor

            m1 = models.get_model("prov_1", "deepseek-chat")
            m2 = models.get_model("prov_1", "deepseek-chat")

        self.assertIsNotNone(m1)
        self.assertIsNotNone(m2)
        # Provider 实例只创建一次（缓存生效）
        self.assertEqual(len(created_clients), 1)
        # 两个 Model 共享同一 Provider 实例
        self.assertIs(m1.provider, m2.provider)


class ModelsCapabilityCheckTest(unittest.TestCase):
    """§7.3：不支持 tool calling 的模型传 tools → ProviderCapabilityError。"""

    def test_capability_check_blocks_tools_when_not_supported(self):
        provider = FakeProvider(complete_result=CompleteResult(content="ok"))
        models = _make_models_with_provider(provider, caps=_caps(tool_calling=False))
        model = models._test_model

        ctx = LLMContext(
            messages=[{"role": "user", "content": "hi"}],
            tools=[Tool(name="fn", description="d", parameters=Type.Object(properties={}))],
        )

        with self.assertRaises(ProviderCapabilityError) as cm:
            _run(models.complete(model, ctx))
        self.assertEqual(cm.exception.capability, "tool_calling")
        # Provider 不应被调用
        self.assertEqual(provider.complete_calls, 0)

    def test_capability_check_allows_tools_when_supported(self):
        provider = FakeProvider(complete_result=CompleteResult(content="ok"))
        models = _make_models_with_provider(provider, caps=_caps(tool_calling=True))
        model = models._test_model

        ctx = LLMContext(
            messages=[{"role": "user", "content": "hi"}],
            tools=[Tool(name="fn", description="d", parameters=Type.Object(properties={}))],
        )

        result = _run(models.complete(model, ctx))
        self.assertEqual(result.content, "ok")
        self.assertEqual(provider.complete_calls, 1)

    def test_capability_check_allows_tools_when_unknown(self):
        """能力未知（None）时不阻断，由 LLM 自行决定是否调用。"""
        provider = FakeProvider(complete_result=CompleteResult(content="ok"))
        models = _make_models_with_provider(provider, caps=_caps(tool_calling=None))
        model = models._test_model

        ctx = LLMContext(
            messages=[{"role": "user", "content": "hi"}],
            tools=[Tool(name="fn", description="d", parameters=Type.Object(properties={}))],
        )
        result = _run(models.complete(model, ctx))
        self.assertEqual(provider.complete_calls, 1)

    def test_capability_check_skipped_when_no_tools(self):
        """没传 tools 时不做能力检查，即使模型不支持 tools 也能调用。"""
        provider = FakeProvider(complete_result=CompleteResult(content="ok"))
        models = _make_models_with_provider(provider, caps=_caps(tool_calling=False))
        model = models._test_model

        ctx = LLMContext(messages=[{"role": "user", "content": "hi"}])
        result = _run(models.complete(model, ctx))
        self.assertEqual(provider.complete_calls, 1)


class ModelsCompleteUsageTest(unittest.TestCase):
    """§7.1：complete() 成功/失败都自动写一条 usage 记录。"""

    def test_complete_success_writes_usage(self):
        usage = Usage(input_tokens=10, output_tokens=5, total_tokens=15)
        provider = FakeProvider(complete_result=CompleteResult(content="ok", usage=usage))
        models = _make_models_with_provider(provider)
        model = models._test_model

        captured = []
        with patch("app.ai.models.UsageWriter.write", side_effect=lambda *a, **kw: captured.append((a, kw))) as m_write:
            result = _run(models.complete(model, LLMContext(messages=[{"role": "user", "content": "hi"}])))

        self.assertEqual(result.content, "ok")
        # 写一次 usage，status=success
        self.assertEqual(m_write.call_count, 1)
        args, kwargs = captured[0]
        self.assertEqual(kwargs.get("status"), "success")
        # usage 对象正确传递
        self.assertEqual(args[0].input_tokens, 10)

    def test_complete_removes_old_images_before_applying_image_reserve(self):
        provider = FakeProvider(complete_result=CompleteResult(content="ok"))
        models = _make_models_with_provider(provider)
        model = models._test_model
        model.context_window_tokens = 4096
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "a" * 1500},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,old1"}},
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "b" * 1500},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,old2"}},
                ],
            },
            {"role": "user", "content": "n" * 3000},
        ]

        with patch("app.ai.models.UsageWriter.write"):
            _run(models.complete(model, LLMContext(messages=messages)))

        self.assertEqual(provider.last_complete_context.messages, [
            {"role": "user", "content": "n" * 3000},
        ])

    def test_complete_failure_writes_failed_usage(self):
        exc = RuntimeError("provider down")
        provider = FakeProvider(complete_exc=exc)
        models = _make_models_with_provider(provider)
        model = models._test_model

        with patch("app.ai.models.UsageWriter.write") as m_write:
            with self.assertRaises(RuntimeError):
                _run(models.complete(model, LLMContext(messages=[{"role": "user", "content": "hi"}])))

        m_write.assert_called_once()
        _, kwargs = m_write.call_args
        self.assertEqual(kwargs.get("status"), "failed")
        self.assertIn("provider down", kwargs.get("error_message", ""))

    def test_complete_passes_usage_context_fields(self):
        """§7.5：usage_context 中的字段必须完整传递到 UsageContext。"""
        provider = FakeProvider(complete_result=CompleteResult(content="ok"))
        models = _make_models_with_provider(provider)
        model = models._test_model

        captured_ctx = []

        def capture_write(usage, ctx, **kw):
            captured_ctx.append(ctx)

        with patch("app.ai.models.UsageWriter.write", side_effect=capture_write):
            _run(models.complete(
                model,
                LLMContext(messages=[{"role": "user", "content": "hi"}]),
                options={
                    "usage_context": {
                        "phase": "summarize",
                        "task_id": "t1",
                        "platform": "douyin",
                        "video_id": "v1",
                        "video_title": "测试",
                        "request_meta": {"stage": "merge"},
                    }
                },
            ))

        ctx = captured_ctx[0]
        self.assertEqual(ctx.provider_id, "prov_1")
        self.assertEqual(ctx.provider_name, "DeepSeek")
        self.assertEqual(ctx.model_name, "deepseek-chat")
        self.assertEqual(ctx.phase, "summarize")
        self.assertEqual(ctx.task_id, "t1")
        self.assertEqual(ctx.platform, "douyin")
        self.assertEqual(ctx.video_id, "v1")
        self.assertEqual(ctx.video_title, "测试")
        self.assertEqual(ctx.request_meta, {"stage": "merge"})


class ModelsStreamUsageTest(unittest.TestCase):
    """§7.2：stream() 成功只写一条 usage（done 事件触发），失败写一条 failed。"""

    def test_stream_success_writes_single_usage_on_done(self):
        """§7.2 关键：流式成功只写一条 usage（在 done 事件时），不重复。"""
        usage = Usage(input_tokens=5, output_tokens=3, total_tokens=8)
        events = [
            StreamEvent.start(),
            StreamEvent.text_delta("hi"),
            StreamEvent.text_end(),
            StreamEvent.done(usage=usage),
        ]
        provider = FakeProvider(stream_events=events)
        models = _make_models_with_provider(provider)
        model = models._test_model

        with patch("app.ai.models.UsageWriter.write") as m_write:
            async def consume():
                async for _ in models.stream(model, LLMContext(messages=[{"role": "user", "content": "hi"}])):
                    pass
            _run(consume())

        # 只写一条 usage（done 触发）
        self.assertEqual(m_write.call_count, 1)
        _, kwargs = m_write.call_args
        self.assertEqual(kwargs.get("status"), "success")

    def test_stream_trims_a_context_copy_using_saved_model_window(self):
        provider = FakeProvider(stream_events=[StreamEvent.done()])
        models = _make_models_with_provider(provider)
        model = models._test_model
        model.context_window_tokens = 512
        messages = [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "x" * 900},
            {"role": "assistant", "content": "y" * 900},
            {"role": "user", "content": "latest"},
        ]
        original = copy.deepcopy(messages)

        async def consume():
            async for _ in models.stream(model, LLMContext(messages=messages)):
                pass

        with patch("app.ai.models.UsageWriter.write"):
            _run(consume())

        self.assertEqual(messages, original)
        self.assertEqual(provider.last_stream_context.messages, [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "latest"},
        ])

    def test_stream_error_event_writes_failed_usage(self):
        """流中出现 error 事件 → 写 failed usage，不写 success。"""
        from app.ai.errors import ProviderAuthError
        events = [
            StreamEvent.error(ProviderAuthError("401", provider_id="p", model_name="m")),
        ]
        provider = FakeProvider(stream_events=events)
        models = _make_models_with_provider(provider)
        model = models._test_model

        with patch("app.ai.models.UsageWriter.write") as m_write:
            async def consume():
                async for _ in models.stream(model, LLMContext(messages=[{"role": "user", "content": "hi"}])):
                    pass
            _run(consume())

        m_write.assert_called_once()
        _, kwargs = m_write.call_args
        self.assertEqual(kwargs.get("status"), "failed")

    def test_stream_provider_exception_writes_failed_usage(self):
        """provider.stream() 抛异常 → 写 failed usage，重新抛出。"""
        provider = FakeProvider(stream_exc=RuntimeError("connection reset"))
        models = _make_models_with_provider(provider)
        model = models._test_model

        with patch("app.ai.models.UsageWriter.write") as m_write:
            async def consume():
                async for _ in models.stream(model, LLMContext(messages=[{"role": "user", "content": "hi"}])):
                    pass
            with self.assertRaises(RuntimeError):
                _run(consume())

        m_write.assert_called_once()
        _, kwargs = m_write.call_args
        self.assertEqual(kwargs.get("status"), "failed")

    def test_non_stream_model_uses_complete_and_emits_text_events_with_single_usage(self):
        usage = Usage(input_tokens=7, output_tokens=2, total_tokens=9)
        provider = FakeProvider(
            complete_result=CompleteResult(content="fallback text", usage=usage),
        )
        models = _make_models_with_provider(provider)
        model = models._test_model
        model.supports_stream = False

        async def collect():
            return [
                event
                async for event in models.stream(
                    model,
                    LLMContext(messages=[{"role": "user", "content": "hi"}]),
                )
            ]

        with patch("app.ai.models.UsageWriter.write") as write_usage:
            events = _run(collect())

        self.assertEqual(provider.stream_calls, 0)
        self.assertEqual(provider.complete_calls, 1)
        types = [event.type for event in events]
        self.assertIn(StreamEventType.TEXT_DELTA, types)
        self.assertEqual(types[-1], StreamEventType.DONE)
        self.assertEqual(
            "".join(event.delta or "" for event in events if event.type == StreamEventType.TEXT_DELTA),
            "fallback text",
        )
        write_usage.assert_called_once()
        written_usage = write_usage.call_args.args[0]
        self.assertEqual(written_usage.total_tokens, 9)

    def test_non_stream_model_normalizes_complete_tool_calls_before_done(self):
        provider = FakeProvider(
            complete_result=CompleteResult(
                tool_calls=[{
                    "id": "call_1",
                    "name": "lookup_transcript",
                    "arguments": '{"task_id":"t1"}',
                }],
                usage=Usage(input_tokens=4, output_tokens=3, total_tokens=7),
            ),
        )
        models = _make_models_with_provider(provider)
        model = models._test_model
        model.supports_stream = False

        async def collect():
            return [
                event
                async for event in models.stream(
                    model,
                    LLMContext(messages=[{"role": "user", "content": "use tool"}]),
                )
            ]

        with patch("app.ai.models.UsageWriter.write") as write_usage:
            events = _run(collect())

        types = [event.type for event in events]
        self.assertLess(types.index(StreamEventType.TOOLCALL_START), types.index(StreamEventType.TOOLCALL_END))
        self.assertLess(types.index(StreamEventType.TOOLCALL_END), types.index(StreamEventType.DONE))
        end = next(event for event in events if event.type == StreamEventType.TOOLCALL_END)
        self.assertEqual(end.tool_call_id, "call_1")
        self.assertEqual(end.tool_name, "lookup_transcript")
        self.assertEqual(end.arguments, '{"task_id":"t1"}')
        self.assertEqual(provider.stream_calls, 0)
        self.assertEqual(provider.complete_calls, 1)
        write_usage.assert_called_once()

    def test_non_stream_model_emits_complete_order_for_thinking_text_and_tools(self):
        provider = FakeProvider(
            complete_result=CompleteResult(
                content="final",
                thinking="reasoning",
                tool_calls=[{
                    "id": "call_1",
                    "name": "lookup",
                    "arguments": '{"id":"1"}',
                }],
                usage=Usage(input_tokens=6, output_tokens=4, total_tokens=10),
            ),
        )
        models = _make_models_with_provider(provider)
        model = models._test_model
        model.supports_stream = False

        async def collect():
            return [event async for event in models.stream(model, LLMContext(messages=[]))]

        with patch("app.ai.models.UsageWriter.write"):
            events = _run(collect())

        self.assertEqual(
            [event.type for event in events],
            [
                StreamEventType.START,
                StreamEventType.THINKING_START,
                StreamEventType.THINKING_DELTA,
                StreamEventType.THINKING_END,
                StreamEventType.TEXT_START,
                StreamEventType.TEXT_DELTA,
                StreamEventType.TOOLCALL_START,
                StreamEventType.TOOLCALL_END,
                StreamEventType.TEXT_END,
                StreamEventType.DONE,
            ],
        )

    def test_non_stream_model_with_no_text_does_not_emit_text_boundaries(self):
        provider = FakeProvider(
            complete_result=CompleteResult(
                tool_calls=[{"id": "call_1", "name": "lookup", "arguments": "{}"}],
            ),
        )
        models = _make_models_with_provider(provider)
        model = models._test_model
        model.supports_stream = False

        async def collect():
            return [event async for event in models.stream(model, LLMContext(messages=[]))]

        with patch("app.ai.models.UsageWriter.write"):
            events = _run(collect())

        types = [event.type for event in events]
        self.assertNotIn(StreamEventType.TEXT_START, types)
        self.assertNotIn(StreamEventType.TEXT_DELTA, types)
        self.assertNotIn(StreamEventType.TEXT_END, types)

    def test_non_stream_model_complete_failure_writes_failed_usage_once(self):
        provider = FakeProvider(complete_exc=RuntimeError("complete unavailable"))
        models = _make_models_with_provider(provider)
        model = models._test_model
        model.supports_stream = False

        async def consume():
            async for _ in models.stream(
                model,
                LLMContext(messages=[{"role": "user", "content": "hi"}]),
            ):
                pass

        with patch("app.ai.models.UsageWriter.write") as write_usage:
            with self.assertRaisesRegex(RuntimeError, "complete unavailable"):
                _run(consume())

        self.assertEqual(provider.stream_calls, 0)
        self.assertEqual(provider.complete_calls, 1)
        write_usage.assert_called_once()
        self.assertEqual(write_usage.call_args.kwargs["status"], "failed")


class ModelsBuildUsageContextTest(unittest.TestCase):
    def test_default_phase_is_chat(self):
        models = _make_models_with_provider(FakeProvider())
        model = models._test_model
        ctx = models._build_usage_context(model, options=None)
        self.assertEqual(ctx.phase, "chat")

    def test_empty_options_uses_defaults(self):
        models = _make_models_with_provider(FakeProvider())
        model = models._test_model
        ctx = models._build_usage_context(model, options={})
        self.assertEqual(ctx.phase, "chat")
        self.assertIsNone(ctx.task_id)


if __name__ == "__main__":
    unittest.main()
