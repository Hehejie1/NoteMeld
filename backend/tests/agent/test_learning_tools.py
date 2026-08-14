from __future__ import annotations

import asyncio

from app.agent.core.signal import AbortSignal
from app.agent.learning_tools import create_learning_tools
from app.models.learning_canvas import LearningCanvas


class _Service:
    def __init__(self):
        self.calls = []

    def create_canvas(self, conversation_id: str, **kwargs):
        from app.models.learning_canvas import LearningCanvas

        self.calls.append((conversation_id, kwargs))
        return LearningCanvas(
            canvas_id="lc_tool",
            conversation_id=conversation_id,
            goal=kwargs["goal"],
        )


def test_learning_tools_are_bound_to_current_conversation() -> None:
    service = _Service()
    tools = create_learning_tools("conv_tool", canvas_service=service)
    build = next(tool for tool in tools if tool.name == "build_learning_canvas")

    result = asyncio.run(
        build.execute(
            "call-1",
            {"goal": "学习 Agent", "external_scopes": ["academic"]},
            AbortSignal(),
            lambda _event: None,
        )
    )

    assert result.is_error is False
    assert service.calls[0][0] == "conv_tool"
    assert service.calls[0][1]["goal"] == "学习 Agent"


def test_learning_tool_set_exposes_four_stable_names() -> None:
    names = [tool.name for tool in create_learning_tools("conv_tool", canvas_service=_Service())]
    assert names == [
        "build_learning_canvas",
        "read_learning_canvas",
        "start_learning_unit",
        "submit_learning_evidence",
    ]


def test_read_learning_canvas_can_resume_latest_without_canvas_id() -> None:
    class _Store:
        def latest(self, conversation_id: str):
            assert conversation_id == "conv_tool"
            return LearningCanvas(
                canvas_id="lc_latest",
                conversation_id=conversation_id,
                goal="继续学习",
            )

    tools = create_learning_tools(
        "conv_tool",
        canvas_service=_Service(),
        canvas_store=_Store(),
    )
    read = next(tool for tool in tools if tool.name == "read_learning_canvas")

    result = asyncio.run(
        read.execute("call-read", {}, AbortSignal(), lambda _event: None)
    )

    assert result.is_error is False
    assert "lc_latest" in result.content[0]["text"]
    assert read.parameters["required"] == []


def test_build_uses_mandatory_learning_scopes_when_caller_omits_scopes() -> None:
    class _Config:
        def get_learning_scopes(self, requested_scopes=None):
            assert requested_scopes is None
            return ["academic", "github"]

    service = _Service()
    tools = create_learning_tools(
        "conv_tool",
        canvas_service=service,
        search_config_manager=_Config(),
    )
    build = next(tool for tool in tools if tool.name == "build_learning_canvas")

    result = asyncio.run(
        build.execute(
            "call-build",
            {"goal": "学习 Agent"},
            AbortSignal(),
            lambda _event: None,
        )
    )

    assert result.is_error is False
    assert service.calls[0][1]["external_scopes"] == ["academic", "github"]
