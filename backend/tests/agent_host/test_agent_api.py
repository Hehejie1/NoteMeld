from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.routers import agent
from fastapi import HTTPException


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


def test_events_endpoint_returns_404_for_unknown_turn(monkeypatch):
    monkeypatch.setattr(agent.agent_store, "get_turn", lambda _turn_id: None)

    request = SimpleNamespace(headers={})
    try:
        agent.get_turn_events(request, "missing-turn")
    except HTTPException as error:
        assert error.status_code == 404
        assert error.detail["code"] == "turn_not_found"
    else:
        raise AssertionError("expected 404")


def test_start_turn_projects_same_session_for_ui_and_cli(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "get_all_models", lambda: [{"model_name": "demo"}])
    monkeypatch.setattr(agent, "select_model", lambda *_args: "demo")
    monkeypatch.setattr(
        agent.agent_store,
        "create_turn",
        lambda session_id, **_kwargs: {"turn_id": "turn-1", "session_id": session_id, "status": "created"},
    )
    monkeypatch.setattr(agent._executor, "start", lambda **kwargs: calls.append(("executor", kwargs)))

    result = agent.create_turn("session-1", agent.TurnRequest(input="hello", model="demo"))

    assert result["data"]["session_id"] == "session-1"
    assert result["data"]["user_message_id"]
    assert result["data"]["assistant_message_id"]
    assert calls[0][0] == "executor"
    assert calls[0][1]["session_id"] == "session-1"
    assert calls[0][1]["assistant_message_id"] == result["data"]["assistant_message_id"]
    assert calls[0][1]["user_message_id"] == result["data"]["user_message_id"]


def test_idempotent_retry_returns_existing_turn_without_duplicate_projection(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "get_all_models", lambda: [{"model_name": "demo"}])
    monkeypatch.setattr(agent, "select_model", lambda *_args: "demo")
    monkeypatch.setattr(
        agent.agent_store,
        "create_turn",
        lambda *_args, **_kwargs: {
            "turn_id": "turn-existing", "session_id": "session-1", "status": "succeeded",
            "_replayed": True,
        },
    )
    monkeypatch.setattr(agent._executor, "start", lambda **kwargs: calls.append(("executor", kwargs)))

    result = agent.create_turn(
        "session-1",
        agent.TurnRequest(input="hello", model="demo", idempotency_key="same-request"),
    )

    assert result["data"]["replayed"] is True
    assert calls == []


def test_start_turn_accepts_empty_text_with_context_refs_and_attachments(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "get_all_models", lambda: [{"model_name": "demo"}])
    monkeypatch.setattr(agent, "select_model", lambda *_args: "demo")
    monkeypatch.setattr(
        agent.agent_store,
        "create_turn",
        lambda *_, **__: {"turn_id": "turn-2", "session_id": "session-1", "status": "created"},
    )
    monkeypatch.setattr(agent._executor, "start", lambda **kwargs: calls.append(kwargs))

    result = agent.create_turn(
        "session-1",
        agent.TurnRequest(
            input={
                "text": "",
                "attachments": [{"type": "text", "content": "ctx"}],
                "context_refs": [{"type": "note", "id": "n1"}],
            },
            model="demo",
        ),
    )

    assert result["data"]["user_message_id"]
    assert result["data"]["assistant_message_id"]
    assert calls and calls[0]["content"] == ""
    assert calls[0]["attachments"] == [{"type": "text", "content": "ctx"}]
    assert calls[0]["context_refs"] == [{"type": "note", "id": "n1"}]


def test_cancel_does_not_pretend_native_turn_is_terminal(monkeypatch):
    monkeypatch.setattr(agent.agent_store, "get_turn", lambda _turn_id: {
        "turn_id": "turn-1", "session_id": "session-1", "status": "running",
    })
    monkeypatch.setattr(agent.get_agent_sdk_host(), "cancel", lambda _turn_id: None)
    transitions = []
    monkeypatch.setattr(agent.agent_store, "transition_turn", lambda *args, **kwargs: transitions.append((args, kwargs)) or {
        "turn_id": "turn-1", "status": "cancelling",
    })

    result = agent.cancel_turn("turn-1")

    assert result["data"] == {"turn_id": "turn-1", "accepted": True, "status": "cancelling"}
    assert transitions[0][0][1] == "cancelling"
    assert transitions[0][1]["terminal_event_type"] == "turn.cancelling"


def test_resolve_approval_routes_to_native_host(monkeypatch):
    calls = []
    monkeypatch.setattr(agent.get_agent_sdk_host(), "resolve_approval", lambda approval_id, decision: calls.append((approval_id, decision)))
    result = agent.resolve_approval("approval-1", agent.ApprovalRequest(decision="approve"))
    assert result["data"] == {"approval_id": "approval-1", "decision": "approve", "accepted": True}
    assert calls == [("approval-1", "approve")]
