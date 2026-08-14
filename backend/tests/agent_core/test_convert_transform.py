"""§7.4 convert_to_llm 过滤 + 不 mutate + transform_context + before_tool_call block。"""
from __future__ import annotations

import copy

from tests.agent_core._base import AgentCoreTestCase, FakeModel, FakeModels


class TestConvertTransform(AgentCoreTestCase):

    def test_default_convert_filters_ui_only_types(self):
        from app.agent.core.hooks import _default_convert_to_llm
        from app.agent.core.message import AgentMessage, UserMessage, AssistantMessage, ToolResultMessage
        msgs = [
            UserMessage(content="u1"),
            AgentMessage(role="user", content="", message_type="note_progress"),
            AgentMessage(role="user", content="", message_type="task_card_progress"),
            AgentMessage(role="assistant", content="", message_type="parameter_request"),
            AssistantMessage(content="a1"),
            AgentMessage(role="user", content="", message_type="note_progress"),
            ToolResultMessage(call_id="c1", content="ok"),
            AgentMessage(role="assistant", content="", message_type="knowledge_board"),
            AgentMessage(role="assistant", content="", message_type="note_result"),
        ]
        original = copy.deepcopy(msgs)
        out = _default_convert_to_llm(msgs)
        roles = [o["role"] for o in out]
        self.assertEqual(roles, ["user", "assistant", "tool"])
        # 不 mutate 原数组
        self.assertEqual(len(msgs), len(original))
        for a, b in zip(msgs, original):
            self.assertEqual(a.role, b.role)
            self.assertEqual(a.message_type, b.message_type)

    def test_tool_result_error_prefixes_message(self):
        from app.agent.core.hooks import _default_convert_to_llm
        from app.agent.core.message import ToolResultMessage
        msgs = [ToolResultMessage(call_id="c1", content="boom", is_error=True)]
        out = _default_convert_to_llm(msgs)
        self.assertEqual(out[0]["role"], "tool")
        self.assertIn("TOOL_EXECUTION_ERROR", out[0]["content"])
        self.assertIn("boom", out[0]["content"])

    def test_default_transform_is_shallow_copy(self):
        from app.agent.core.hooks import _default_transform_context
        from app.agent.core.signal import AbortSignal
        from app.agent.core.message import UserMessage
        msgs = [UserMessage(content="x")]
        out = _default_transform_context(msgs, AbortSignal())
        self.assertIsNot(out, msgs)
        self.assertIs(out[0], msgs[0])

    def test_before_tool_call_block_yields_error_result(self):
        blocks = []
        async def before(tc, args, ctx):
            if tc["function"]["name"] == "x":
                blocks.append((tc, args))
                return {"block": True, "reason": "permission denied"}
            return None
        t = self.make_tool("x")
        models = FakeModels(turns=[
            [self.make_tool_call("c1", "x", {"p": 1})],
            "OK",
        ])
        from app.agent.core import Agent, AgentState
        agent = Agent(
            initial_state=AgentState(model=FakeModel(), tools=[t]),
            models=models, before_tool_call=before,
        )
        self._run(agent.prompt("hi"))
        self._run(agent.wait_for_idle())
        self.assertEqual(len(blocks), 1)
        tr = [m for m in agent.messages if m.role == "toolResult"]
        self.assertEqual(len(tr), 1)
        self.assertTrue(tr[0].is_error)
        self.assertIn("permission denied", str(tr[0].content))


if __name__ == "__main__":
    import unittest
    unittest.main()
