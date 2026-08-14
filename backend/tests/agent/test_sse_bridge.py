"""P2-T7: sse_bridge 单测 — Agent 事件 → 旧 SSE delta/done/error 映射。

验收映射：
- MESSAGE_UPDATE(delta) → {"type":"delta","content":delta}
- AGENT_END(error=None) → {"type":"done","answer":full_answer,"sources":[...]}
- AGENT_END(error=...) → {"type":"error","message":...}
- 其他 8 类事件 → 忽略

同时测试 collect_agent_result 非流式收集。
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.core import Agent, AgentState
from app.agent.core.events import (
    AgentEndEvent,
    AgentEventType,
    AgentStartEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from app.agent.sse_bridge import agent_events_to_sse_dict, collect_agent_result
from tests.agent_core._base import FakeModel, FakeModels


class SseBridgeStreamTest(unittest.TestCase):
    """agent_events_to_sse_dict：Agent 事件 → 旧 SSE dict 序列。"""

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def test_single_turn_text_yields_delta_then_done(self):
        """单轮文本：delta * N + done（含 full_answer + sources）。"""
        # FakeModels 按 4 字符切块，"你好世界测试" = 6 字符 → 2 deltas
        models = FakeModels(turns=["你好世界测试"])
        agent = Agent(
            initial_state=AgentState(model=FakeModel()),
            max_turns=1,
            models=models,
        )
        sources = [{"text": "src1", "source_type": "note"}]

        async def consume():
            events = []
            async for evt in agent_events_to_sse_dict(agent, "hi", sources):
                events.append(evt)
            return events

        events = self._run(consume())

        deltas = [e for e in events if e["type"] == "delta"]
        dones = [e for e in events if e["type"] == "done"]
        errors = [e for e in events if e["type"] == "error"]

        self.assertGreaterEqual(len(deltas), 1, f"expected >=1 deltas, got {deltas}")
        self.assertEqual(len(dones), 1)
        self.assertEqual(len(errors), 0)

        # full_answer 是所有 delta 的拼接
        full = "".join(d["content"] for d in deltas)
        self.assertEqual(full, "你好世界测试")
        self.assertEqual(dones[0]["answer"], "你好世界测试")
        self.assertEqual(dones[0]["sources"], sources)

    def test_agent_error_yields_error_event(self):
        """Agent error → {"type":"error","message":...}。"""
        # 用 callable 让 FakeModels.stream 直接抛异常（loop 会捕获并设 state.error）
        def _raise(i, ctx):  # noqa: ARG001
            raise RuntimeError("llm down")

        models = FakeModels(turns=[_raise])
        agent = Agent(
            initial_state=AgentState(model=FakeModel()),
            max_turns=1,
            models=models,
        )

        async def consume():
            events = []
            async for evt in agent_events_to_sse_dict(agent, "hi", []):
                events.append(evt)
            return events

        events = self._run(consume())

        errors = [e for e in events if e["type"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("llm down", errors[0]["message"])

    def test_other_event_types_ignored(self):
        """10 类事件中只有 MESSAGE_UPDATE / AGENT_END 产出 SSE dict。"""
        # 用 FakeModels 单轮文本，验证只产出 delta + done
        models = FakeModels(turns=["OK"])
        agent = Agent(
            initial_state=AgentState(model=FakeModel()),
            max_turns=1,
            models=models,
        )

        async def consume():
            events = []
            async for evt in agent_events_to_sse_dict(agent, "hi", []):
                events.append(evt)
            return events

        events = self._run(consume())

        # 只能有 delta / done / error 三种 type
        valid_types = {"delta", "done", "error"}
        for e in events:
            self.assertIn(e["type"], valid_types)


class CollectAgentResultTest(unittest.TestCase):
    """collect_agent_result：非流式收集最终回答。"""

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def test_returns_answer_and_sources(self):
        """正常完成：返回 {answer, sources}。"""
        models = FakeModels(turns=["最终回答"])
        agent = Agent(
            initial_state=AgentState(model=FakeModel()),
            max_turns=1,
            models=models,
        )
        sources = [{"text": "s1"}]
        result = self._run(collect_agent_result(agent, "q", sources))
        self.assertEqual(result["answer"], "最终回答")
        self.assertEqual(result["sources"], sources)

    def test_multi_turn_keeps_last_answer(self):
        """多轮（含工具）时：answer 只保留最后一轮 assistant 文本。"""
        from tests.agent_core._base import build_agent_tool, build_tool_call

        async def echo(cid, params, signal, on_update):
            return {"content": [{"type": "text", "text": "tool_result"}]}

        tool = build_agent_tool("echo", mode="parallel", execute=echo)
        models = FakeModels(turns=[
            [build_tool_call("c1", "echo", {})],
            "最终总结",
        ])
        agent = Agent(
            initial_state=AgentState(model=FakeModel(), tools=[tool]),
            max_turns=5,
            models=models,
        )
        result = self._run(collect_agent_result(agent, "q", []))
        self.assertEqual(result["answer"], "最终总结")

    def test_agent_error_raises(self):
        """Agent 出错时 raise RuntimeError。"""
        def _raise(i, ctx):  # noqa: ARG001
            raise RuntimeError("boom")

        models = FakeModels(turns=[_raise])
        agent = Agent(
            initial_state=AgentState(model=FakeModel()),
            max_turns=1,
            models=models,
        )
        with self.assertRaises(RuntimeError) as ctx:
            self._run(collect_agent_result(agent, "q", []))
        self.assertIn("boom", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
