"""§7.2 并行工具：并发执行 + 结果顺序不变 + tool_execution_end 按完成先后。"""
from __future__ import annotations

import asyncio
import time

from tests.agent_core._base import AgentCoreTestCase, FakeModel, FakeModels, build_agent_tool


def _sleep_tool(name: str, sleep_s: float):
    async def _exec(cid, params, signal, on_update):
        await asyncio.sleep(sleep_s)
        return {
            "content": [{"type": "text", "text": f"done:{name}:{sleep_s}s"}],
            "details": {"name": name, "slept": sleep_s},
        }
    return build_agent_tool(name=name, mode="parallel", execute=_exec)


class TestParallelTools(AgentCoreTestCase):

    def test_parallel_tools_elapsed_near_max(self):
        t_slow = _sleep_tool("slow", 0.200)
        t_fast = _sleep_tool("fast", 0.080)
        models = FakeModels(turns=[
            [self.make_tool_call("c1", "slow", {}), self.make_tool_call("c2", "fast", {})],
            "ok",
        ])
        from app.agent.core import Agent, AgentState
        rec = self.recorder()
        agent = Agent(
            initial_state=AgentState(model=FakeModel(), tools=[t_slow, t_fast]),
            max_turns=5,
            tool_execution="parallel",
            models=models,
        )
        agent.subscribe(rec)
        t0 = time.perf_counter()
        self._run(agent.prompt("go"))
        self._run(agent.wait_for_idle())
        elapsed = time.perf_counter() - t0
        # 串行 = 0.28s，并行 ≈ 0.21s；阈值宽松点
        self.assertLess(elapsed, 0.200 + 0.080 * 1.1 + 0.10,
                        f"并发执行耗时 {elapsed:.3f}s 过长")

    def test_parallel_tool_end_order_is_completion_order(self):
        t_slow = _sleep_tool("slow", 0.150)
        t_fast = _sleep_tool("fast", 0.040)
        models = FakeModels(turns=[
            [self.make_tool_call("c1", "slow", {}), self.make_tool_call("c2", "fast", {})],
            "done",
        ])
        from app.agent.core import Agent, AgentState
        from app.agent.core.events import AgentEventType
        rec = self.recorder()
        agent = Agent(
            initial_state=AgentState(model=FakeModel(), tools=[t_slow, t_fast]),
            max_turns=5, tool_execution="parallel", models=models,
        )
        agent.subscribe(rec)
        self._run(agent.prompt("go"))
        self._run(agent.wait_for_idle())
        # tool_execution_end 顺序必须是先 fast 后 slow
        tool_ends = [e for e in rec.events if e.type == AgentEventType.TOOL_EXECUTION_END]
        names = [(e.result.details or {}).get("name") for e in tool_ends]
        self.assertEqual(names, ["fast", "slow"], names)
        # 但 turn_end.toolResults 顺序必须与原文一致 = [slow, fast]
        turns = [e for e in rec.events if e.type == AgentEventType.TURN_END]
        first_turn_results = turns[0].tool_results or []
        order = [r.details.get("name") for r in first_turn_results]
        self.assertEqual(order, ["slow", "fast"], order)

    def test_serial_mode_is_serial(self):
        t_a = _sleep_tool("a", 0.100)
        t_b = _sleep_tool("b", 0.100)
        models = FakeModels(turns=[
            [self.make_tool_call("c1", "a", {}), self.make_tool_call("c2", "b", {})],
            "done",
        ])
        from app.agent.core import Agent, AgentState
        agent = Agent(
            initial_state=AgentState(model=FakeModel(), tools=[t_a, t_b]),
            max_turns=5, tool_execution="serial", models=models,
        )
        t0 = time.perf_counter()
        self._run(agent.prompt("go"))
        self._run(agent.wait_for_idle())
        elapsed = time.perf_counter() - t0
        self.assertGreaterEqual(elapsed, 0.190,
                                f"串行模式应耗时 >= 0.2s，实际 {elapsed:.3f}s")


if __name__ == "__main__":
    import unittest
    unittest.main()
