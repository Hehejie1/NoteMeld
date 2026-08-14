"""P2-T7: chat_compat 单测 — Agent 路径与旧路径响应结构逐字段等价。

验收 §1：
- run_free_chat 返回 {answer, sources}（与旧 free_chat 结构一致）
- run_free_chat_stream yield delta/done dict（与旧 free_chat_stream 结构一致）
- run_chat 返回 {answer, sources}（与旧 chat 结构一致）
- run_chat 支持 tool calling（Agent 多轮）
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.agent_core._base import FakeModel, FakeModels, build_agent_tool, build_tool_call


# ---------------------------------------------------------------------------
# 辅助：构造 mock hooks 和 models，避免真实 vector store / DB
# ---------------------------------------------------------------------------

def _make_mock_hooks(system_prompt="sys", sources=None):
    """构造 mock ChatContextHooks。"""
    from app.agent.chat_adapter import ChatContextHooks

    return ChatContextHooks(system_prompt=system_prompt, sources=sources or [])


def _patch_context(mocker, sources=None):
    """patch build_free_chat_hooks / build_chat_hooks 返回 mock hooks。"""
    hooks = _make_mock_hooks(sources=sources)
    mocker.patch("app.agent.agent_service.build_free_chat_hooks", return_value=hooks)
    mocker.patch("app.agent.agent_service.build_chat_hooks", return_value=hooks)
    return hooks


class RunFreeChatTest(unittest.TestCase):
    """run_free_chat：返回结构与旧 free_chat 等价。"""

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def test_returns_answer_and_sources(self):
        """run_free_chat 返回 {answer, sources}。"""
        from app.agent.agent_service import run_free_chat

        models = FakeModels(turns=["这是回答"])
        hooks = _make_mock_hooks(sources=[{"text": "src"}])

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_free_chat_hooks", return_value=hooks):
            result = self._run(run_free_chat(
                question="你好",
                history=[],
                provider_id="prov",
                model_name="model",
            ))

        self.assertIsInstance(result, dict)
        self.assertIn("answer", result)
        self.assertIn("sources", result)
        self.assertEqual(result["answer"], "这是回答")
        self.assertEqual(result["sources"], [{"text": "src"}])

    def test_history_passed_to_agent(self):
        """history 被转为 AgentMessage 并传入 Agent。"""
        from app.agent.agent_service import run_free_chat

        models = FakeModels(turns=["回答"])
        hooks = _make_mock_hooks()

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_free_chat_hooks", return_value=hooks):
            result = self._run(run_free_chat(
                question="继续",
                history=[
                    {"role": "user", "content": "之前的问题"},
                    {"role": "assistant", "content": "之前的回答"},
                ],
                provider_id="prov",
                model_name="model",
            ))

        self.assertEqual(result["answer"], "回答")


class RunFreeChatStreamTest(unittest.TestCase):
    """run_free_chat_stream：yield 旧 SSE delta/done dict。"""

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def test_yields_delta_then_done(self):
        """run_free_chat_stream yield delta * N + done。"""
        from app.agent.agent_service import run_free_chat_stream

        models = FakeModels(turns=["你好世界测试"])
        hooks = _make_mock_hooks(sources=[{"text": "s1"}])

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_free_chat_hooks", return_value=hooks):
            async def consume():
                events = []
                async for evt in run_free_chat_stream(
                    question="hi",
                    history=[],
                    provider_id="prov",
                    model_name="model",
                ):
                    events.append(evt)
                return events

            events = self._run(consume())

        deltas = [e for e in events if e["type"] == "delta"]
        dones = [e for e in events if e["type"] == "done"]
        self.assertGreaterEqual(len(deltas), 1)
        self.assertEqual(len(dones), 1)
        self.assertEqual(dones[0]["answer"], "你好世界测试")
        self.assertEqual(dones[0]["sources"], [{"text": "s1"}])

    def test_error_yields_error_event(self):
        """run_free_chat_stream LLM 出错 → yield error 事件。"""
        from app.agent.agent_service import run_free_chat_stream

        def _raise(i, ctx):  # noqa: ARG001
            raise RuntimeError("stream broken")

        models = FakeModels(turns=[_raise])
        hooks = _make_mock_hooks()

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_free_chat_hooks", return_value=hooks):
            async def consume():
                events = []
                async for evt in run_free_chat_stream(
                    question="x",
                    history=[],
                    provider_id="prov",
                    model_name="model",
                ):
                    events.append(evt)
                return events

            events = self._run(consume())

        errors = [e for e in events if e["type"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("stream broken", errors[0]["message"])


class RunChatTest(unittest.TestCase):
    """run_chat：返回 {answer, sources}，支持 tool calling。"""

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def test_no_tool_call_returns_answer(self):
        """run_chat 无工具调用 → 返回 {answer, sources}。"""
        from app.agent.agent_service import run_chat

        models = FakeModels(turns=["最终回答"])
        hooks = _make_mock_hooks(sources=[{"text": "src"}])

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_chat_hooks", return_value=hooks), \
             patch("app.agent.agent_service.create_builtin_tools", return_value=[]):
            result = self._run(run_chat(
                task_id="task-1",
                question="问",
                history=[],
                provider_id="prov",
                model_name="model",
            ))

        self.assertEqual(result["answer"], "最终回答")
        self.assertEqual(result["sources"], [{"text": "src"}])

    def test_tool_call_then_answer(self):
        """run_chat 工具调用一轮后给出最终回答。"""
        from app.agent.agent_service import run_chat

        async def echo(cid, params, signal, on_update):
            return {"content": [{"type": "text", "text": "tool_result"}]}

        tool = build_agent_tool("echo", mode="parallel", execute=echo)
        models = FakeModels(turns=[
            [build_tool_call("c1", "echo", {})],
            "基于工具结果的回答",
        ])
        hooks = _make_mock_hooks()

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_chat_hooks", return_value=hooks), \
             patch("app.agent.agent_service.create_builtin_tools", return_value=[tool]):
            result = self._run(run_chat(
                task_id="task-1",
                question="用工具回答",
                history=[],
                provider_id="prov",
                model_name="model",
            ))

        self.assertEqual(result["answer"], "基于工具结果的回答")


class ChatServiceRedirectTest(unittest.TestCase):
    """feature flag redirect：AGENT_CHAT_ENABLED 控制路径切换。"""

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def test_flag_off_uses_legacy_path(self):
        """flag off：chat_service 走旧实现（不调 agent_service）。"""
        from app.services import chat_service

        # 确认 flag 默认 False
        self.assertFalse(chat_service._AGENT_CHAT_ENABLED)

        # patch 旧路径的 create_models，确认走旧路径
        models = FakeModels(turns=["旧路径回答"])
        with patch("app.services.chat_service.create_models", return_value=models), \
             patch("app.services.chat_service._prepare_free_chat_context") as mock_ctx, \
             patch("app.services.chat_service._resolve_asset_context", return_value=""):
            mock_ctx.return_value = MagicMock(context_text="ctx", sources=[])
            result = self._run(chat_service.free_chat(
                question="hi",
                history=[],
                provider_id="prov",
                model_name="model",
            ))

        self.assertEqual(result["answer"], "旧路径回答")

    def test_flag_on_redirects_to_agent(self):
        """flag on：chat_service.free_chat 调用 run_free_chat。"""
        from app.services import chat_service

        with patch.object(chat_service, "_AGENT_CHAT_ENABLED", True):
            with patch("app.agent.agent_service.run_free_chat", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = {"answer": "agent回答", "sources": []}

                async def _call():
                    return await chat_service.free_chat(
                        question="hi",
                        history=[],
                        provider_id="prov",
                        model_name="model",
                    )

                result = self._run(_call())

        self.assertEqual(result["answer"], "agent回答")
        mock_run.assert_called_once()

    def test_flag_off_stream_yields_only_delta_done(self):
        """P3 阶段二回归：flag=false 时 free_chat_stream 只产 delta/done，不产 task_card。"""
        from app.services import chat_service

        self.assertFalse(chat_service._AGENT_CHAT_ENABLED)

        models = FakeModels(turns=["旧路径流式回答"])
        with patch("app.services.chat_service.create_models", return_value=models), \
             patch("app.services.chat_service._prepare_free_chat_context") as mock_ctx, \
             patch("app.services.chat_service._resolve_asset_context", return_value=""):
            mock_ctx.return_value = MagicMock(context_text="ctx", sources=[])

            async def consume():
                events = []
                async for evt in chat_service.free_chat_stream(
                    question="hi",
                    history=[],
                    provider_id="prov",
                    model_name="model",
                ):
                    events.append(evt)
                return events

            events = self._run(consume())

        types = {e["type"] for e in events}
        # 旧路径只产 delta / done，不应出现 task_card / task_card_progress / parameter_request
        self.assertIn("delta", types)
        self.assertIn("done", types)
        self.assertNotIn("task_card", types)
        self.assertNotIn("task_card_progress", types)
        self.assertNotIn("parameter_request", types)


if __name__ == "__main__":
    unittest.main()
