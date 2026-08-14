"""端到端 demo：3 turn + 工具 + 异常 tool + 空 prompt/continue 边界。"""
from __future__ import annotations

import asyncio

from tests.agent_core._base import AgentCoreTestCase, FakeModel, FakeModels


class TestE2EDemo(AgentCoreTestCase):

    def test_3_turn_with_two_tools(self):
        trace = []

        async def lookup(cid, params, signal, on_update):
            trace.append(("lookup", params))
            await on_update({"progress": 30})
            await on_update({"progress": 100})
            return {
                "content": [{"type": "text", "text": f"result:{params['kw']}@{params['tid']}"}],
                "details": {"kw": params["kw"]},
            }

        async def summarize(cid, params, signal, on_update):
            trace.append(("summarize", params))
            return {"content": [{"type": "text", "text": "SUMMARY_OK"}]}

        t_lookup = self.make_tool(
            name="lookup_transcript", mode="parallel", execute=lookup,
            params={"properties": {"tid": {}, "kw": {}}, "required": ["tid"]},
        )
        t_summ = self.make_tool(name="summarize", mode="parallel", execute=summarize)
        rec = self.recorder()

        models = FakeModels(turns=[
            [self.make_tool_call("c1", "lookup_transcript", {"tid": "t-abc", "kw": "NeRF"})],
            [self.make_tool_call("c2", "summarize", {"text": "result:NeRF@t-abc"})],
            "已总结 NeRF 相关内容。",
        ])
        from app.agent.core import Agent, AgentState
        agent = Agent(
            initial_state=AgentState(system_prompt="研究助手", model=FakeModel(), tools=[t_lookup, t_summ]),
            max_turns=10, models=models,
        )
        agent.subscribe(rec)
        self._run(agent.prompt("帮我在 t-abc 搜 NeRF 再总结"))
        self._run(agent.wait_for_idle())

        self.assertEqual([x[0] for x in trace], ["lookup", "summarize"])
        self.assertEqual(trace[0][1]["kw"], "NeRF")

        roles = [m.role for m in agent.messages]
        self.assertGreaterEqual(roles.count("assistant"), 3)
        self.assertEqual(roles.count("toolResult"), 2)

        self.assertIsNone(agent.error)
        self.assertEqual(agent.turn_count, 3)
        self.assertFalse(agent.is_streaming)

        types = rec.types()
        for m in ["agent_start", "agent_end", "turn_start", "turn_end",
                  "message_start", "message_end", "tool_execution_start", "tool_execution_end"]:
            self.assertIn(m, types, (m, types))
        self.assertIn("tool_execution_update", types)

    def test_tool_exception_returns_is_error(self):
        async def bad(cid, params, signal, on_update):
            raise RuntimeError("boom")
        t = self.make_tool("bad", mode="parallel", execute=bad)
        models = FakeModels(turns=[
            [self.make_tool_call("c1", "bad", {})],
            "收到错误。",
        ])
        from app.agent.core import Agent, AgentState
        agent = Agent(initial_state=AgentState(model=FakeModel(), tools=[t]), models=models)
        self._run(agent.prompt("run bad"))
        self._run(agent.wait_for_idle())
        self.assertIsNone(agent.error)
        tr = [m for m in agent.messages if m.role == "toolResult"]
        self.assertEqual(len(tr), 1)
        self.assertTrue(tr[0].is_error)
        self.assertIn("boom", str(tr[0].content))

    def test_empty_prompt_raises_value_error(self):
        from app.agent.core import Agent, AgentState
        agent = Agent(initial_state=AgentState(model=FakeModel()), models=FakeModels())
        with self.assertRaises(ValueError):
            self._run(agent.prompt(""))

    def test_continue_requires_good_last_role(self):
        from app.agent.core import Agent, AgentState, AgentError
        from app.agent.core.message import AssistantMessage
        agent = Agent(initial_state=AgentState(model=FakeModel(), messages=[]),
                      models=FakeModels(turns=["x"]))
        with self.assertRaises(AgentError):
            self._run(agent.continue_())
        agent.messages.append(AssistantMessage(content="x"))
        with self.assertRaises(AgentError):
            self._run(agent.continue_())


if __name__ == "__main__":
    import unittest
    unittest.main()
