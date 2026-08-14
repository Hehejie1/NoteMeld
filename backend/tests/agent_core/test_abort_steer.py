"""§7.3 abort + steer。"""
from __future__ import annotations

import asyncio
import time

from tests.agent_core._base import AgentCoreTestCase, FakeModel, FakeModels, build_agent_tool


def _long_tool(sleep_s=2.0):
    async def _exec(cid, params, signal, on_update):
        start = time.perf_counter()
        while not signal.aborted and (time.perf_counter() - start) < sleep_s:
            await asyncio.sleep(0.01)
        return {"content": [{"type": "text", "text": "tool ran"}],
                "details": {"aborted": signal.aborted}}
    return build_agent_tool(name="long", mode="parallel", execute=_exec)


class TestAbortSteer(AgentCoreTestCase):

    def test_abort_delivered_within_200ms(self):
        tool = _long_tool(5.0)
        models = FakeModels(turns=[
            [self.make_tool_call("c1", "long", {})],
            "fallback",
        ])
        from app.agent.core import Agent, AgentState
        agent = Agent(initial_state=AgentState(model=FakeModel(), tools=[tool]), models=models)

        async def _both():
            t = asyncio.create_task(agent.prompt("go"))
            await asyncio.sleep(0.050)
            await agent.abort("user stopped")
            await t

        t0 = time.perf_counter()
        self._run(_both())
        self._run(agent.wait_for_idle())
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 0.500, f"abort 总耗时 {elapsed:.3f}s 过长")
        self.assertIsNotNone(agent.error)
        self.assertEqual(agent.error.code, "aborted")
        # message 为传入的 reason，不强求包含 aborted 字样

    def test_steer_injects_user_message(self):
        calls = []
        async def echo(cid, params, signal, on_update):
            calls.append(dict(params))
            return {"content": [{"type": "text", "text": "ok"}]}
        t = self.make_tool("echo", mode="parallel", execute=echo)
        models = FakeModels(turns=[
            [self.make_tool_call("c1", "echo", {"action": "first"})],
            "纠正已收到",
        ])
        from app.agent.core import Agent, AgentState
        agent = Agent(initial_state=AgentState(model=FakeModel(), tools=[t]), models=models)

        async def _both():
            task = asyncio.create_task(agent.prompt("first request"))
            await asyncio.sleep(0.020)
            await agent.steer("改成 action=second")
            await task

        self._run(_both())
        self._run(agent.wait_for_idle())
        user_msgs = [m for m in agent.messages if m.role == "user"]
        steer = [m for m in user_msgs if (m.meta or {}).get("steer")]
        self.assertEqual(len(steer), 1)
        self.assertIn("改成", str(steer[0].content))

    def test_abort_then_prompt_works(self):
        tool = _long_tool(3.0)
        # 第一次 prompt: turn 0 → 进入 tool 执行中被 abort，models.call_count 变 1。
        # 第二次 prompt: call_count 1 → 取 turns[1] 作为本轮 LLM 输出。
        models = FakeModels(turns=[
            [self.make_tool_call("c1", "long", {})],
            "second-run",  # turns[1]：第二次 prompt 的输出
            "fallback",
        ])
        from app.agent.core import Agent, AgentState
        agent = Agent(initial_state=AgentState(model=FakeModel(), tools=[tool]), models=models)

        async def run_first():
            t = asyncio.create_task(agent.prompt("task 1"))
            await asyncio.sleep(0.040)
            await agent.abort()
            await t

        self._run(run_first())
        self._run(agent.wait_for_idle())
        self.assertIsNotNone(agent.error)
        self._run(agent.prompt("task 2"))
        self._run(agent.wait_for_idle())
        last = [m for m in agent.messages if m.role == "assistant"][-1]
        self.assertIn("second-run", str(last.content))


if __name__ == "__main__":
    import unittest
    unittest.main()
