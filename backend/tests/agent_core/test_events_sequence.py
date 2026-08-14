"""§7.1 事件序列严格顺序。"""
from __future__ import annotations

from tests.agent_core._base import AgentCoreTestCase, FakeModel, FakeModels


class TestEventsSequence(AgentCoreTestCase):

    def test_3_turn_event_sequence_order(self):
        t_lookup = self.make_tool("lookup_transcript", mode="parallel")
        t_summ = self.make_tool("summarize", mode="parallel")
        models = FakeModels(turns=[
            [self.make_tool_call("c1", "lookup_transcript", {"task_id": "x", "keyword": "NeRF"})],
            [self.make_tool_call("c2", "summarize", {"sources": "1,2"})],
            "找到了 NeRF 相关内容，3DGS 与之不同...",
        ])
        from app.agent.core import Agent, AgentState
        rec = self.recorder()
        agent = Agent(
            initial_state=AgentState(system_prompt="你是研究助手", model=FakeModel(), tools=[t_lookup, t_summ]),
            max_turns=10,
            models=models,
        )
        agent.subscribe(rec)
        self._run(agent.prompt("帮我搜 NeRF 再总结"))
        self._run(agent.wait_for_idle())
        types = rec.types()
        self.assertEqual(types[0], "agent_start")
        self.assertEqual(types[-1], "agent_end")
        self.assertEqual(types.count("turn_start"), 3)
        self.assertEqual(types.count("turn_end"), 3)
        self.assertEqual(types.count("message_start"), types.count("message_end"))
        turn1 = types[types.index("turn_start") + 1:types.index("turn_end")]
        self.assertIn("tool_execution_start", turn1)
        self.assertIn("tool_execution_end", turn1)

    def test_listener_exception_does_not_break_loop(self):
        good = []
        async def bad(e):
            if e.type.value == "tool_execution_start":
                raise RuntimeError("boom")
        async def gd(e):
            good.append(e.type.value)
        t = self.make_tool("ok")
        models = FakeModels(turns=[
            [self.make_tool_call("c1", "ok", {})],
            "done",
        ])
        from app.agent.core import Agent, AgentState
        agent = Agent(initial_state=AgentState(model=FakeModel(), tools=[t]), models=models)
        agent.subscribe(bad)
        agent.subscribe(gd)
        self._run(agent.prompt("hello"))
        self._run(agent.wait_for_idle())
        self.assertIsNone(agent.error)
        self.assertIn("agent_start", good)
        self.assertIn("agent_end", good)
        self.assertIn("tool_execution_end", good)

    def test_oracle_export_keeps_event_turns_and_tool_result_order(self):
        """Changing core event data must change the cross-language oracle rows."""
        from tests.agent_core.export_oracle_fixtures import collect_oracle_rows

        rows = self._run(collect_oracle_rows("parallel_tools"))
        self.assertEqual([row["sequence"] for row in rows], list(range(1, len(rows) + 1)))
        self.assertEqual(
            [row["payload"]["result"]["details"]["name"] for row in rows if row["type"] == "tool_execution_end"],
            ["fast", "slow"],
        )
        turn_end = next(row for row in rows if row["type"] == "turn_end")
        self.assertEqual(
            [result["call_id"] for result in turn_end["payload"]["tool_results"]],
            ["slow-call", "fast-call"],
        )


if __name__ == "__main__":
    import unittest
    unittest.main()
