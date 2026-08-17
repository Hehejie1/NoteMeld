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
