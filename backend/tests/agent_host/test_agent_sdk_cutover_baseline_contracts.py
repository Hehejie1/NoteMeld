from __future__ import annotations

import inspect

from app.agent_host import native_executor
from app.routers import agent as agent_router


def test_submit_turn_should_include_session_history(monkeypatch):
    captured: dict[str, object] = {}

    class FakeRuntime:
        def __init__(self, *_, driver, on_event, **__):
            self.driver = driver
            self._on_event = on_event

        def submit_turn(self, request):
            captured["request"] = request
            self._on_event({"schema_version": "1", "type": "turn.succeeded", "sequence": 0, "payload": {"answer": "ok"}})
            return 1

        def wait(self, *_):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(
        native_executor.AgentSdkRuntime,
        "load",
        lambda **_: type(
            "loaded",
            (),
            {"binding": type("runtime", (), {"Runtime": FakeRuntime})},
        )(),
    )
    monkeypatch.setattr(native_executor, "_resolve_saved_model", lambda *_: (None, object()))
    monkeypatch.setattr(native_executor.agent_store, "append_event", lambda *_, **__: None)
    monkeypatch.setattr(native_executor.agent_store, "transition_turn", lambda *_, **__: None)

    executor = native_executor.NativeAgentExecutor(event_sink=lambda *_: None)
    executor.run_sync("turn-1", "session-1", "你好")

    request = captured["request"]
    assert isinstance(request, dict)
    input_payload = request["input"]
    assert "history" in input_payload, (
        "目标契约要求在 submit_turn.input 中包含会话历史；当前实现返回空上下文。"
    )
    assert "messages" in request, "SDK 入口必须接受按消息序列组织的上下文快照。"
    assert request["messages"] and request["messages"][-1]["role"] == "user"
    assert request["messages"] == input_payload["history"] + [{"role": "user", "content": "你好"}]
    assert "tools" in request, "SDK 入口必须回传工具描述清单。"
    assert "tools" in input_payload, "input schema 约束要求 tools 与 request 的顶层保持一致。"
    assert request["tools"] == input_payload["tools"]


def test_turn_events_api_should_be_live_stream():
    source = inspect.getsource(agent_router.get_turn_events)
    assert "await _events.subscribe(" in source


def test_steer_turn_should_support_mid_turn_control(monkeypatch):
    monkeypatch.setattr(agent_router.agent_store, "get_turn", lambda *_: {"turn_id": "turn-1"})
    response = agent_router.steer_turn("turn-1", {})
    assert response.get("data", {}).get("status") == "accepted"


def test_approval_resolve_should_ack_decision():
    result = agent_router.resolve_approval("approval-1", agent_router.ApprovalRequest(decision="approve"))
    assert isinstance(result, dict)
    assert result.get("data", {}).get("approval_id") == "approval-1"
