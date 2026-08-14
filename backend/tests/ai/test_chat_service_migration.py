"""T9 迁移测试：chat_service.py → notemeld-ai。

验收标准覆盖：
- §7.1 free_chat / chat 迁移后 usage payload 字段与旧路径逐字段等价
- §7.2 free_chat_stream 流式只写一条 usage
- §7.5 /api/usage/* 4 接口 0 字段差异（通过 payload 字段集合对齐间接验证）

设计：
- patch ``create_models`` 返回注入了 fake AsyncOpenAI 的 Models 实例
- patch ``insert_usage_record`` 捕获 payload
- patch 上下文准备函数避免真实 vector store / wiki 检索
"""
from __future__ import annotations

import asyncio
import copy
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


# ── 公共常量 ──────────────────────────────────────────────────

PROVIDER_ID = "prov_chat_001"
PROVIDER_NAME = "DeepSeek"
MODEL_NAME = "deepseek-chat"
TASK_ID = "task_chat_001"
LINKED_TASK_ID = "task_free_001"
PROMPT_TOKENS = 100
COMPLETION_TOKENS = 50
TOTAL_TOKENS = 150


def make_usage():
    return SimpleNamespace(
        prompt_tokens=PROMPT_TOKENS,
        completion_tokens=COMPLETION_TOKENS,
        total_tokens=TOTAL_TOKENS,
    )


def make_canned_response(content="回答内容", tool_calls=None):
    """构造 OpenAI 非流式响应。"""
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=make_usage())


def make_canned_stream_chunks():
    """构造 OpenAI 流式 chunk 序列。"""
    return [
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="你好", tool_calls=None))],
            usage=None,
        ),
        SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="世界", tool_calls=None))],
            usage=make_usage(),
        ),
    ]


def make_fake_models(response=None, *, caps_tool_calling=True, stream_chunks=None):
    """构造 Models 实例，内部 provider 注入 fake AsyncOpenAI client。"""
    from app.ai.provider import OpenAICompatibleProvider

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

    if stream_chunks is not None:
        async def fake_create_stream(**kwargs):
            async def _aiter():
                for c in stream_chunks:
                    yield c
            return _aiter()
        fake_async_client.chat.completions.create = AsyncMock(side_effect=fake_create_stream)
    else:
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
    # 注入 get_model 返回值
    models.get_model = MagicMock(return_value=model)
    return models, model


class SavedContextBudgetTest(unittest.TestCase):
    """Provider 前按保存窗口裁剪副本，不改变 chat/Agent 持久消息。"""

    def test_complete_trims_a_context_copy_using_saved_model_window(self):
        canned = make_canned_response(content="回答")
        models, model = make_fake_models(canned)
        model.context_window_tokens = 512
        messages = [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "x" * 900},
            {"role": "assistant", "content": "y" * 900},
            {"role": "user", "content": "latest"},
        ]
        original = copy.deepcopy(messages)
        ctx = LLMContext(messages=messages)

        with patch("app.services.usage_tracker.insert_usage_record"):
            asyncio.run(models.complete(model, ctx))

        sent = model.provider._client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(ctx.messages, original)
        self.assertEqual(sent, [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "latest"},
        ])


def make_canned_tool_call_response():
    """构造带 tool_calls 的 OpenAI 响应。"""
    tc = SimpleNamespace(
        id="call_abc",
        type="function",
        function=SimpleNamespace(name="get_video_info", arguments="{}"),
    )
    message = SimpleNamespace(content=None, tool_calls=[tc])
    choice = SimpleNamespace(message=message, finish_reason="tool_calls")
    return SimpleNamespace(choices=[choice], usage=make_usage())


# ── §7.1 free_chat 迁移：usage 字段等价 ─────────────────────

class FreeChatMigrationTest(unittest.TestCase):
    """free_chat() 迁移到 notemeld-ai 后 usage payload 字段等价。"""

    def test_free_chat_writes_one_usage_with_correct_fields(self):
        """§7.1：free_chat 迁移后写一条 usage，phase=free_chat，字段齐全。"""
        canned = make_canned_response(content="这是回答")
        models, _ = make_fake_models(canned)

        captured = []
        with patch("app.services.chat_service.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append), \
             patch("app.services.chat_service._prepare_free_chat_context") as mock_ctx, \
             patch("app.services.chat_service._resolve_asset_context", return_value=""):
            mock_ctx.return_value = MagicMock(context_text="ctx", sources=[])

            from app.services.chat_service import free_chat
            result = asyncio.run(free_chat(
                question="你好",
                history=[],
                provider_id=PROVIDER_ID,
                model_name=MODEL_NAME,
                linked_task_id=LINKED_TASK_ID,
            ))

        self.assertEqual(len(captured), 1, "free_chat 应只写一条 usage")
        payload = captured[0]
        self.assertEqual(payload["phase"], "free_chat")
        self.assertEqual(payload["task_id"], LINKED_TASK_ID)
        self.assertEqual(payload["provider_id"], PROVIDER_ID)
        self.assertEqual(payload["provider_name"], PROVIDER_NAME)
        self.assertEqual(payload["model_name"], MODEL_NAME)
        self.assertEqual(payload["prompt_tokens"], PROMPT_TOKENS)
        self.assertEqual(payload["completion_tokens"], COMPLETION_TOKENS)
        self.assertEqual(payload["total_tokens"], TOTAL_TOKENS)
        self.assertEqual(payload["status"], "success")
        self.assertIsNone(payload["error_message"])

        # 返回值结构不变
        self.assertEqual(result["answer"], "这是回答")
        self.assertEqual(result["sources"], [])

    def test_free_chat_failed_writes_status_failed(self):
        """§7.1：free_chat 请求失败时写一条 status=failed usage。"""
        models, _ = make_fake_models(response=None)
        # 替换为抛异常
        models.get_model.return_value.provider._client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("network down")
        )

        captured = []
        with patch("app.services.chat_service.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append), \
             patch("app.services.chat_service._prepare_free_chat_context") as mock_ctx, \
             patch("app.services.chat_service._resolve_asset_context", return_value=""):
            mock_ctx.return_value = MagicMock(context_text="ctx", sources=[])

            from app.services.chat_service import free_chat
            with self.assertRaises(RuntimeError):
                asyncio.run(free_chat(
                    question="x",
                    history=[],
                    provider_id=PROVIDER_ID,
                    model_name=MODEL_NAME,
                ))

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["status"], "failed")
        self.assertIsNone(captured[0]["prompt_tokens"])


# ── §7.2 free_chat_stream 迁移：流式只写一条 usage ───────────

class FreeChatStreamMigrationTest(unittest.TestCase):
    """free_chat_stream() 迁移到 notemeld-ai 后流式只写一条 usage。"""

    def test_stream_writes_exactly_one_usage_on_success(self):
        """§7.2：free_chat_stream 成功时只写一条 usage，phase=free_chat_stream。"""
        chunks = make_canned_stream_chunks()
        models, _ = make_fake_models(stream_chunks=chunks)

        captured = []
        with patch("app.services.chat_service.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append), \
             patch("app.services.chat_service._prepare_free_chat_context") as mock_ctx, \
             patch("app.services.chat_service._resolve_asset_context", return_value=""):
            mock_ctx.return_value = MagicMock(context_text="ctx", sources=["src"])

            from app.services.chat_service import free_chat_stream

            async def consume():
                events = []
                async for event in free_chat_stream(
                    question="你好",
                    history=[],
                    provider_id=PROVIDER_ID,
                    model_name=MODEL_NAME,
                    linked_task_id=LINKED_TASK_ID,
                ):
                    events.append(event)
                return events

            events = asyncio.run(consume())

        # §7.2 只写一条 usage
        self.assertEqual(len(captured), 1, "§7.2 流式应只写一条 usage")
        payload = captured[0]
        self.assertEqual(payload["phase"], "free_chat_stream")
        self.assertEqual(payload["task_id"], LINKED_TASK_ID)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["prompt_tokens"], PROMPT_TOKENS)

        # SSE 事件结构不变：delta * N + done
        deltas = [e for e in events if e["type"] == "delta"]
        dones = [e for e in events if e["type"] == "done"]
        self.assertEqual(len(deltas), 2)
        self.assertEqual(len(dones), 1)
        self.assertEqual(dones[0]["answer"], "你好世界")
        self.assertEqual(dones[0]["sources"], ["src"])

    def test_stream_writes_one_failed_usage_on_error(self):
        """§7.2：free_chat_stream 流中出错时写一条 status=failed usage。"""
        models, _ = make_fake_models(response=None)
        # 让 stream 创建时抛异常
        models.get_model.return_value.provider._client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("stream broken")
        )

        captured = []
        with patch("app.services.chat_service.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append), \
             patch("app.services.chat_service._prepare_free_chat_context") as mock_ctx, \
             patch("app.services.chat_service._resolve_asset_context", return_value=""):
            mock_ctx.return_value = MagicMock(context_text="ctx", sources=[])

            from app.services.chat_service import free_chat_stream

            async def consume():
                async for _ in free_chat_stream(
                    question="x",
                    history=[],
                    provider_id=PROVIDER_ID,
                    model_name=MODEL_NAME,
                ):
                    pass

            with self.assertRaises(RuntimeError):
                asyncio.run(consume())

        self.assertEqual(len(captured), 1, "流式失败应只写一条 failed usage")
        self.assertEqual(captured[0]["status"], "failed")
        self.assertEqual(captured[0]["phase"], "free_chat_stream")


# ── §7.1 chat 迁移：tool calling 循环 usage 字段等价 ─────────

class ChatMigrationTest(unittest.TestCase):
    """chat() 迁移到 notemeld-ai 后 tool calling 循环 usage 等价。"""

    def test_chat_no_tool_call_writes_one_usage(self):
        """chat() 无工具调用时只写一条 usage，phase=chat_tool_call。"""
        canned = make_canned_response(content="最终回答")
        models, _ = make_fake_models(canned)

        captured = []
        with patch("app.services.chat_service.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append), \
             patch("app.services.chat_service.VectorStoreManager") as mock_vs:
            mock_vs.return_value.query.return_value = []

            from app.services.chat_service import chat
            result = asyncio.run(chat(
                task_id=TASK_ID,
                question="视频讲什么",
                history=[],
                provider_id=PROVIDER_ID,
                model_name=MODEL_NAME,
            ))

        self.assertEqual(len(captured), 1, "无工具调用应只写一条 usage")
        payload = captured[0]
        self.assertEqual(payload["phase"], "chat_tool_call")
        self.assertEqual(payload["task_id"], TASK_ID)
        self.assertEqual(payload["status"], "success")
        # request_meta 包含 round 和 has_tools
        meta = json.loads(payload["request_meta_json"])
        self.assertEqual(meta["round"], 1)
        self.assertTrue(meta["has_tools"])

        self.assertEqual(result["answer"], "最终回答")

    def test_chat_with_tool_call_writes_usage_per_round(self):
        """chat() 工具调用循环：每轮写一条 usage，最后写一条 chat_final。"""
        # 第 1 轮：返回 tool_call
        # 第 2 轮：返回 tool_call
        # 第 3 轮：返回 tool_call
        # 最终（不带 tools）：返回最终回答
        tool_response = make_canned_tool_call_response()
        final_response = make_canned_response(content="最终回答")

        models, _ = make_fake_models(response=None)
        # 按调用顺序返回不同响应
        models.get_model.return_value.provider._client.chat.completions.create = AsyncMock(
            side_effect=[tool_response, tool_response, tool_response, final_response]
        )

        captured = []
        with patch("app.services.chat_service.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append), \
             patch("app.services.chat_service.VectorStoreManager") as mock_vs, \
             patch("app.services.chat_service.execute_tool", return_value='{"info":"ok"}'):
            mock_vs.return_value.query.return_value = []

            from app.services.chat_service import chat
            result = asyncio.run(chat(
                task_id=TASK_ID,
                question="视频讲什么",
                history=[],
                provider_id=PROVIDER_ID,
                model_name=MODEL_NAME,
            ))

        # 3 轮 tool_call + 1 轮 final = 4 条 usage
        self.assertEqual(len(captured), 4, "3 轮 tool_call + 1 final = 4 条 usage")

        # 前 3 条 phase=chat_tool_call
        for i in range(3):
            self.assertEqual(captured[i]["phase"], "chat_tool_call")
            meta = json.loads(captured[i]["request_meta_json"])
            self.assertEqual(meta["round"], i + 1)
            self.assertTrue(meta["has_tools"])

        # 第 4 条 phase=chat_final
        self.assertEqual(captured[3]["phase"], "chat_final")
        final_meta = json.loads(captured[3]["request_meta_json"])
        # chat_final 不传 request_meta，默认为空 dict
        self.assertEqual(final_meta, {})

        self.assertEqual(result["answer"], "最终回答")

    def test_chat_tool_calls_format_correct(self):
        """chat() 工具调用：CompleteResult.tool_calls 正确转为 OpenAI message 格式。"""
        tool_response = make_canned_tool_call_response()
        final_response = make_canned_response(content="done")

        models, _ = make_fake_models(response=None)
        models.get_model.return_value.provider._client.chat.completions.create = AsyncMock(
            side_effect=[tool_response, final_response]
        )

        # 捕获传给 OpenAI API 的 messages 参数
        create_calls = models.get_model.return_value.provider._client.chat.completions.create

        with patch("app.services.chat_service.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record"), \
             patch("app.services.chat_service.VectorStoreManager") as mock_vs, \
             patch("app.services.chat_service.execute_tool", return_value='{"info":"ok"}') as mock_exec:
            mock_vs.return_value.query.return_value = []

            from app.services.chat_service import chat
            asyncio.run(chat(
                task_id=TASK_ID,
                question="x",
                history=[],
                provider_id=PROVIDER_ID,
                model_name=MODEL_NAME,
            ))

        # 第 2 次调用的 messages 应包含 assistant + tool 消息
        self.assertEqual(create_calls.call_count, 2)
        second_call_messages = create_calls.call_args_list[1].kwargs["messages"]

        # 找到 assistant 消息（带 tool_calls）
        assistant_msgs = [m for m in second_call_messages if m.get("role") == "assistant"]
        self.assertEqual(len(assistant_msgs), 1)
        asst = assistant_msgs[0]
        self.assertEqual(asst["tool_calls"][0]["id"], "call_abc")
        self.assertEqual(asst["tool_calls"][0]["type"], "function")
        self.assertEqual(asst["tool_calls"][0]["function"]["name"], "get_video_info")

        # 找到 tool 消息
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        self.assertEqual(len(tool_msgs), 1)
        self.assertEqual(tool_msgs[0]["tool_call_id"], "call_abc")
        self.assertEqual(tool_msgs[0]["content"], '{"info":"ok"}')

        # execute_tool 被调用了一次
        mock_exec.assert_called_once()


# ── §7.5 payload 字段集合与 ORM 对齐 ─────────────────────────

class ChatServicePayloadFieldsTest(unittest.TestCase):
    """§7.5：迁移后所有 usage payload 字段集合与 ModelUsageRecord ORM 对齐。"""

    ORM_FIELDS = {
        "task_id", "provider_id", "provider_name", "model_name", "phase",
        "platform", "video_id", "video_title",
        "prompt_tokens", "completion_tokens", "total_tokens",
        "status", "error_message",
        "request_started_at", "request_finished_at", "duration_ms",
        "request_meta_json",
    }

    def test_free_chat_payload_fields_match_orm(self):
        canned = make_canned_response()
        models, _ = make_fake_models(canned)

        captured = []
        with patch("app.services.chat_service.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append), \
             patch("app.services.chat_service._prepare_free_chat_context") as mock_ctx, \
             patch("app.services.chat_service._resolve_asset_context", return_value=""):
            mock_ctx.return_value = MagicMock(context_text="ctx", sources=[])

            from app.services.chat_service import free_chat
            asyncio.run(free_chat(
                question="x",
                history=[],
                provider_id=PROVIDER_ID,
                model_name=MODEL_NAME,
            ))

        self.assertEqual(set(captured[0].keys()), self.ORM_FIELDS,
                         "free_chat payload 字段集合与 ORM 不一致")

    def test_chat_payload_fields_match_orm(self):
        canned = make_canned_response()
        models, _ = make_fake_models(canned)

        captured = []
        with patch("app.services.chat_service.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append), \
             patch("app.services.chat_service.VectorStoreManager") as mock_vs:
            mock_vs.return_value.query.return_value = []

            from app.services.chat_service import chat
            asyncio.run(chat(
                task_id=TASK_ID,
                question="x",
                history=[],
                provider_id=PROVIDER_ID,
                model_name=MODEL_NAME,
            ))

        self.assertEqual(set(captured[0].keys()), self.ORM_FIELDS,
                         "chat payload 字段集合与 ORM 不一致")


if __name__ == "__main__":
    unittest.main()
