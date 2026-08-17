from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.routers import agent


def test_agent_router_is_versioned_and_exposes_core_commands():
    paths = {route.path for route in agent.router.routes}
    assert "/agent/v1/sessions" in paths
    assert "/agent/v1/sessions/{session_id}/turns" in paths
    assert "/agent/v1/turns/{turn_id}/events" in paths
    assert "/agent/v1/sessions/{session_id}/model-preference" in paths


def test_events_endpoint_replays_then_waits_until_terminal(monkeypatch):
    event = {
        "event_id": "e1",
        "turn_id": "t1",
        "sequence": 0,
        "event_type": "message.delta",
        "payload_json": {"type": "message.delta", "delta": "hi"},
    }
    terminal = {
        "event_id": "e2",
        "turn_id": "t1",
        "sequence": 1,
        "event_type": "turn.succeeded",
        "payload_json": {"type": "turn.succeeded"},
    }
    snapshots = iter([
        [event],
        [event, terminal],
    ])
    calls: list[int] = []
    def list_events(_turn_id):
        calls.append(1)
        return next(snapshots, [event, terminal])

    monkeypatch.setattr(agent.agent_store, "list_events", list_events)
    monkeypatch.setattr(
        agent.agent_store,
        "get_turn",
        lambda _turn_id: {"status": "running"} if len(calls) < 2 else {"status": "succeeded"},
    )
    request = SimpleNamespace(headers={})
    response = agent.get_turn_events(request, "t1")

    async def collect():
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(collect())
    assert len(chunks) == 2
    assert "message.delta" in chunks[0]
    assert "turn.succeeded" in chunks[1]


def test_start_turn_projects_same_session_for_ui_and_cli(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "get_all_models", lambda: [{"model_name": "demo"}])
    monkeypatch.setattr(agent, "select_model", lambda *_args: "demo")
    monkeypatch.setattr(
        agent._turns,
        "start_turn",
        lambda session_id, content, **_kwargs: {"turn_id": "turn-1", "session_id": session_id, "status": "created"},
    )
    monkeypatch.setattr(agent, "append_message", lambda session_id, payload: calls.append((session_id, payload)) or {})
    monkeypatch.setattr(agent._executor, "start", lambda **kwargs: calls.append(("executor", kwargs)))

    result = agent.create_turn("session-1", agent.TurnRequest(input="hello", model="demo"))

    assert result["data"]["session_id"] == "session-1"
    assert result["data"]["user_message_id"]
    assert result["data"]["assistant_message_id"]
    assert calls[0][0] == calls[1][0] == "session-1"
    assert calls[2][0] == "executor"
    assert calls[2][1]["session_id"] == "session-1"
    assert calls[2][1]["assistant_message_id"] == result["data"]["assistant_message_id"]
