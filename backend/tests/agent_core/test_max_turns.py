"""§7.5 max_turns 兜底。"""
from __future__ import annotations

from tests.agent_core._base import AgentCoreTestCase, FakeModel, FakeModels, build_agent_tool


def _loop_tool(name="x"):
    async def _exec(cid, params, signal, on_update):
        return {"content": [{"type": "text", "text": f"{cid}-{name}-done"}]}
    return build_agent_tool(name=name, mode="parallel", execute=_exec)


class TestMaxTurns(AgentCoreTestCase):

    def test_max_turns_stops_after_n_turns(self):
        t = _loop_tool("x")
        # lambda: 每次都产出 tool_call，确保不自然结束
        def repeat(_t, _c):
            return [self.make_tool_call(f"c{_t}", "x", {})]
        models = FakeModels(turns=[repeat] * 10)
        from app.agent.core import Agent, AgentState
        agent = Agent(
            initial_state=AgentState(model=FakeModel(), tools=[t]),
            max_turns=3, models=models,
        )
        self._run(agent.prompt("go"))
        self._run(agent.wait_for_idle())
        self.assertEqual(models.call_count, 3)
        self.assertEqual(agent.turn_count, 3)
        self.assertIsNotNone(agent.error)
        self.assertEqual(agent.error.code, "max_turns_reached")
        self.assertIn("max_turns=3", agent.error.message)

    def test_natural_ending_no_error(self):
        t = _loop_tool("x")
        models = FakeModels(turns=[
            [self.make_tool_call("c1", "x", {})],
            "done naturally",
        ])
        from app.agent.core import Agent, AgentState
        agent = Agent(
            initial_state=AgentState(model=FakeModel(), tools=[t]),
            max_turns=10, models=models,
        )
        self._run(agent.prompt("hi"))
        self._run(agent.wait_for_idle())
        self.assertIsNone(agent.error)
        self.assertEqual(agent.turn_count, 2)

    def test_constructor_rejects_invalid_max_turns(self):
        from app.agent.core import Agent, AgentState
        with self.assertRaises(ValueError):
            Agent(initial_state=AgentState(model=FakeModel()), max_turns=0)
        with self.assertRaises(ValueError):
            Agent(initial_state=AgentState(model=FakeModel()), max_turns=-1)


if __name__ == "__main__":
    import unittest
    unittest.main()
