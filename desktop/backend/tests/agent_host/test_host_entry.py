from __future__ import annotations

from app.agent_host.entry import AgentHostEntry
from app.services import agent_store


def test_host_entry_delegates_to_durable_store_without_session_state(monkeypatch):
    calls = []
    monkeypatch.setattr(
        agent_store,
        "create_turn",
        lambda session_id, **kwargs: calls.append((session_id, kwargs))
        or {"turn_id": f"turn-{len(calls)}", "session_id": session_id},
    )

    entry = AgentHostEntry()
    first = entry.create_turn("session-1", model_name="demo")
    second = entry.create_turn("session-1", model_name="demo")

    assert first["turn_id"] == "turn-1"
    assert second["turn_id"] == "turn-2"
    assert calls == [
        ("session-1", {"model_name": "demo", "idempotency_key": None}),
        ("session-1", {"model_name": "demo", "idempotency_key": None}),
    ]
    assert vars(entry) == {}
