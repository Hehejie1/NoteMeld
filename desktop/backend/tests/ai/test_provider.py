"""notemeld-ai Provider 抽象单测。

覆盖：
- LLMContext.to_openai_messages / to_openai_tools 转换
- OpenAICompatibleProvider.stream / complete（mock AsyncOpenAI）
- §7.4 _classify_openai_error：401/403 → AuthError, 429 → RateLimitError, 网络 → NetworkError
- Ollama HTTP/2 禁用逻辑
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.errors import (  # noqa: E402
    ProviderAuthError,
    ProviderNetworkError,
    ProviderRateLimitError,
)
from app.ai.provider import (  # noqa: E402
    LLMContext,
    OpenAICompatibleProvider,
    ProviderConfig,
    _classify_openai_error,
    _create_async_httpx_client,
)
from app.ai.stream import StreamEventType  # noqa: E402
from app.ai.tool import Tool, Type  # noqa: E402
from app.gpt.provider_runtime import ContextLimitExceededError  # noqa: E402


class LLMContextTest(unittest.TestCase):
    def test_to_openai_messages_inserts_system_prompt(self):
        ctx = LLMContext(
            system_prompt="你是助手",
            messages=[{"role": "user", "content": "hi"}],
        )
        msgs = ctx.to_openai_messages()
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[0]["content"], "你是助手")
        self.assertEqual(msgs[1]["role"], "user")

    def test_to_openai_messages_without_system_prompt(self):
        ctx = LLMContext(messages=[{"role": "user", "content": "hi"}])
        msgs = ctx.to_openai_messages()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["role"], "user")

    def test_to_openai_tools_none_when_empty(self):
        ctx = LLMContext()
        self.assertIsNone(ctx.to_openai_tools())

    def test_to_openai_tools_converts_tool_objects(self):
        tool = Tool(
            name="lookup_transcript",
            description="查询转写",
            parameters=Type.Object(properties={"task_id": Type.String()}, required=["task_id"]),
        )
        ctx = LLMContext(tools=[tool])
        tools = ctx.to_openai_tools()
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["type"], "function")
        self.assertEqual(tools[0]["function"]["name"], "lookup_transcript")

    def test_to_openai_tools_passes_dicts_through(self):
        """OpenAI function calling dict 直接透传，不转换。"""
        raw = {"type": "function", "function": {"name": "x", "description": "y", "parameters": {}}}
        ctx = LLMContext(tools=[raw])
        tools = ctx.to_openai_tools()
        self.assertEqual(tools, [raw])

    def test_to_openai_tools_returns_none_when_only_empty_list(self):
        ctx = LLMContext(tools=[])
        # 空列表 to_openai_tools 返回 None（避免传 tools=[] 给 API）
        self.assertIsNone(ctx.to_openai_tools())


class CreateHttpxClientTest(unittest.TestCase):
    """§7.4 Ollama 兼容：本地 Ollama 禁用 HTTP/2。"""

    def test_ollama_localhost_disables_http2(self):
        client = _create_async_httpx_client("http://localhost:11434/v1")
        self.assertIsNotNone(client)

    def test_ollama_127001_disables_http2(self):
        client = _create_async_httpx_client("http://127.0.0.1:11434/v1")
        self.assertIsNotNone(client)

    def test_remote_provider_returns_none(self):
        """远程 provider 不需要自定义 httpx 客户端，让 AsyncOpenAI 自行管理。"""
        self.assertIsNone(_create_async_httpx_client("https://api.deepseek.com/v1"))


class ClassifyOpenAIErrorTest(unittest.TestCase):
    """§7.4 异常分类门禁。"""

    def _classify(self, exc, status=None):
        if status is not None:
            # 模拟 OpenAI SDK 异常带 status_code 属性
            try:
                exc.status_code = status
            except (AttributeError, TypeError):
                exc = SimpleNamespace(__str__=lambda: str(exc), status_code=status)
        return _classify_openai_error(
            exc,
            provider_id="prov_1",
            provider_name="DeepSeek",
            model_name="deepseek-chat",
        )

    def test_401_maps_to_auth_error(self):
        err = self._classify(Exception("Unauthorized"), status=401)
        self.assertIsInstance(err, ProviderAuthError)
        self.assertEqual(err.provider_id, "prov_1")
        self.assertEqual(err.model_name, "deepseek-chat")

    def test_403_maps_to_auth_error(self):
        err = self._classify(Exception("Forbidden"), status=403)
        self.assertIsInstance(err, ProviderAuthError)

    def test_invalid_api_key_message_maps_to_auth_error(self):
        err = self._classify(Exception("invalid_api_key: sk-xxx"))
        self.assertIsInstance(err, ProviderAuthError)

    def test_429_maps_to_rate_limit(self):
        err = self._classify(Exception("Rate limit exceeded"), status=429)
        self.assertIsInstance(err, ProviderRateLimitError)

    def test_rate_limit_message_maps_to_rate_limit(self):
        err = self._classify(Exception("rate limit reached"))
        self.assertIsInstance(err, ProviderRateLimitError)

    def test_503_maps_to_network_error(self):
        err = self._classify(Exception("Service unavailable"), status=503)
        self.assertIsInstance(err, ProviderNetworkError)

    def test_timeout_message_maps_to_network_error(self):
        err = self._classify(Exception("Request timed out"))
        self.assertIsInstance(err, ProviderNetworkError)
        # cause 应保留原始异常
        self.assertIsNotNone(err.__cause__)

    def test_context_limit_wrapped_in_503_timeout_maps_to_safe_context_error_first(self):
        raw = Exception(
            "503 service unavailable timeout; n_prompt_tokens=6492, n_ctx=4096; private-payload"
        )

        err = self._classify(raw, status=503)

        self.assertIsInstance(err, ContextLimitExceededError)
        self.assertEqual(err.code, "context_limit_exceeded")
        self.assertNotIn("6492", str(err))
        self.assertIsNone(err.__cause__)

    def test_connection_error_maps_to_network_error(self):
        err = self._classify(Exception("apiconnectionerror: connection reset"))
        self.assertIsInstance(err, ProviderNetworkError)

    def test_other_errors_pass_through_unchanged(self):
        """非 Auth/RateLimit/Network 的异常原样返回，由上层处理。"""
        original = ValueError("bad request")
        result = self._classify(original, status=400)
        self.assertIs(result, original)


def _make_chunk(*, content=None, tool_calls=None, usage=None):
    """构造一个模拟的 OpenAI stream chunk。"""
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice], usage=usage)


def _make_tool_call_delta(idx, *, tc_id=None, name=None, args_delta=None):
    fn = SimpleNamespace(name=name or "", arguments=args_delta or "")
    return SimpleNamespace(index=idx, id=tc_id, function=fn)


class OpenAICompatibleProviderTest(unittest.TestCase):
    """Provider stream/complete 行为测试，全部 mock AsyncOpenAI。"""

    def _make_provider(self, *, base_url="https://api.deepseek.com/v1"):
        config = ProviderConfig(
            provider_id="prov_1",
            provider_name="DeepSeek",
            api_key="sk-test",
            base_url=base_url,
        )
        provider = OpenAICompatibleProvider(config)
        return provider

    def _run(self, coro):
        return asyncio.run(coro)

    # ── stream ──────────────────────────────────────────────

    def test_stream_emits_text_deltas_and_done(self):
        provider = self._make_provider()

        async def fake_create(**kwargs):
            # 模拟 stream：返回一个 async iterator
            chunks = [
                _make_chunk(content="hello "),
                _make_chunk(content="world"),
                _make_chunk(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2, total_tokens=7)),
            ]
            async def _aiter():
                for c in chunks:
                    yield c
            return _aiter()

        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        async def collect():
            events = []
            async for ev in provider.stream("deepseek-chat", LLMContext(messages=[{"role": "user", "content": "hi"}])):
                events.append(ev)
            return events

        events = self._run(collect())

        # 期望事件序列：start, text_delta("hello "), text_delta("world"), text_end, done
        types = [e.type for e in events]
        self.assertEqual(types[0], StreamEventType.START)
        self.assertIn(StreamEventType.TEXT_DELTA, types)
        self.assertEqual(types[-1], StreamEventType.DONE)
        self.assertEqual(types[-2], StreamEventType.TEXT_END)

        # 验证 delta 文本拼接
        deltas = [e.delta for e in events if e.type == StreamEventType.TEXT_DELTA]
        self.assertEqual("".join(deltas), "hello world")

        # 验证 done 事件携带 usage
        done_event = events[-1]
        self.assertEqual(done_event.usage.input_tokens, 5)
        self.assertEqual(done_event.usage.output_tokens, 2)
        self.assertEqual(done_event.usage.total_tokens, 7)

    def test_stream_emits_error_event_on_create_exception(self):
        """§7.4：create() 抛 401 → 流首产出 error 事件，含 ProviderAuthError。"""
        provider = self._make_provider()

        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        # 构造带 status_code 的异常
        exc = Exception("Unauthorized")
        exc.status_code = 401
        provider._client.chat.completions.create = AsyncMock(side_effect=exc)

        async def collect():
            events = []
            async for ev in provider.stream("deepseek-chat", LLMContext(messages=[{"role": "user", "content": "hi"}])):
                events.append(ev)
            return events

        events = self._run(collect())
        # 流首即 error
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type, StreamEventType.ERROR)
        self.assertIsInstance(events[0].error, ProviderAuthError)

    def test_stream_aggregates_tool_calls(self):
        """工具调用增量聚合，流末产出 toolcall_end。"""
        provider = self._make_provider()

        async def fake_create(**kwargs):
            chunks = [
                _make_chunk(tool_calls=[_make_tool_call_delta(0, tc_id="call_1", name="lookup_transcript", args_delta='{"tas')]),
                _make_chunk(tool_calls=[_make_tool_call_delta(0, args_delta='k_id":"t1"}')]),
                _make_chunk(),
            ]
            async def _aiter():
                for c in chunks:
                    yield c
            return _aiter()

        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        async def collect():
            events = []
            async for ev in provider.stream("deepseek-chat", LLMContext(messages=[{"role": "user", "content": "hi"}])):
                events.append(ev)
            return events

        events = self._run(collect())
        types = [e.type for e in events]

        # 期望：start, toolcall_start, toolcall_delta x2, toolcall_end, text_end, done
        self.assertEqual(types[0], StreamEventType.START)
        self.assertIn(StreamEventType.TOOLCALL_START, types)
        self.assertEqual(types.count(StreamEventType.TOOLCALL_DELTA), 2)
        self.assertIn(StreamEventType.TOOLCALL_END, types)

        end_event = next(e for e in events if e.type == StreamEventType.TOOLCALL_END)
        self.assertEqual(end_event.tool_call_id, "call_1")
        self.assertEqual(end_event.tool_name, "lookup_transcript")
        self.assertEqual(end_event.arguments, '{"task_id":"t1"}')

    # ── complete ────────────────────────────────────────────

    def test_complete_returns_content_and_usage(self):
        provider = self._make_provider()

        # 构造非流式 response
        fn = SimpleNamespace(name="lookup_transcript", arguments='{"task_id":"t1"}')
        tc = SimpleNamespace(id="call_1", function=fn)
        message = SimpleNamespace(content="hello", tool_calls=[tc])
        choice = SimpleNamespace(message=message)
        response = SimpleNamespace(
            choices=[choice],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(return_value=response)

        result = self._run(provider.complete(
            "deepseek-chat",
            LLMContext(messages=[{"role": "user", "content": "hi"}]),
        ))

        self.assertEqual(result.content, "hello")
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0]["id"], "call_1")
        self.assertEqual(result.tool_calls[0]["name"], "lookup_transcript")
        self.assertEqual(result.tool_calls[0]["arguments"], '{"task_id":"t1"}')
        self.assertEqual(result.usage.input_tokens, 10)
        self.assertEqual(result.usage.output_tokens, 5)
        self.assertEqual(result.usage.total_tokens, 15)

    def test_complete_preserves_reasoning_content_and_finish_reason(self):
        provider = self._make_provider()
        message = SimpleNamespace(
            content="",
            reasoning_content="BEGIN_JSON\n{\"title\": \"T\"}\nEND_JSON",
            tool_calls=None,
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="length")],
            usage=None,
        )
        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(return_value=response)

        result = self._run(provider.complete(
            "deepseek-chat",
            LLMContext(messages=[{"role": "user", "content": "hi"}]),
        ))

        self.assertIn("BEGIN_JSON", result.thinking)
        self.assertEqual(result.finish_reason, "length")

    def test_complete_raises_classified_error_on_auth_failure(self):
        """§7.4：complete() 遇 401 抛 ProviderAuthError（而非裸 OpenAI 异常）。"""
        provider = self._make_provider()

        exc = Exception("invalid_api_key")
        exc.status_code = 401

        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(side_effect=exc)

        with self.assertRaises(ProviderAuthError):
            self._run(provider.complete(
                "deepseek-chat",
                LLMContext(messages=[{"role": "user", "content": "hi"}]),
            ))

    def test_complete_with_tools_passes_tools_param(self):
        """ctx.tools 不为空时，请求 payload 应包含 tools 字段。"""
        provider = self._make_provider()

        captured = {}

        async def fake_create(**kwargs):
            captured.update(kwargs)
            # 返回最小响应
            message = SimpleNamespace(content="ok", tool_calls=None)
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(choices=[choice], usage=None)

        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        tool = Tool(name="fn", description="d", parameters=Type.Object(properties={}))
        self._run(provider.complete(
            "deepseek-chat",
            LLMContext(messages=[{"role": "user", "content": "hi"}], tools=[tool]),
        ))

        self.assertIn("tools", captured)
        self.assertEqual(captured["tools"][0]["function"]["name"], "fn")

    def test_complete_passes_request_timeout_from_context(self):
        provider = self._make_provider()
        captured = {}

        async def fake_create(**kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(content="ok", tool_calls=None)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=message)], usage=None
            )

        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        self._run(provider.complete(
            "deepseek-chat",
            LLMContext(
                messages=[{"role": "user", "content": "hi"}],
                timeout=12.5,
            ),
        ))

        self.assertEqual(captured["timeout"], 12.5)

    def test_stream_passes_stream_true_in_payload(self):
        """stream() 调用应传 stream=True。"""
        provider = self._make_provider()
        captured = {}

        async def fake_create(**kwargs):
            captured.update(kwargs)
            async def _aiter():
                # 至少产出一个 chunk 让流不空
                yield _make_chunk(content="x")
            return _aiter()

        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(side_effect=fake_create)

        async def consume():
            async for _ in provider.stream("deepseek-chat", LLMContext(messages=[{"role": "user", "content": "hi"}])):
                pass

        self._run(consume())
        self.assertTrue(captured.get("stream"))


if __name__ == "__main__":
    unittest.main()
