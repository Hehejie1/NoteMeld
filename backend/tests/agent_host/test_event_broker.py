from __future__ import annotations

import asyncio

from app.agent_host.event_broker import EventBroker


def test_replay_then_live_without_duplicates(monkeypatch):
    async def exercise():
        monkeypatch.setattr("app.agent_host.event_broker.agent_store.list_events", lambda _turn: [{"sequence": 0}, {"sequence": 1}])
        monkeypatch.setattr("app.agent_host.event_broker.agent_store.append_event", lambda *args, **kwargs: kwargs.get("payload", args[1] if len(args) > 1 else {}))
        broker = EventBroker()
        stream = broker.subscribe("t1", after_sequence=0)
        assert await stream.__anext__() == {"sequence": 1}
        await broker.publish("t1", {"sequence": 2})
        assert await asyncio.wait_for(stream.__anext__(), 0.1) == {"sequence": 2}
    asyncio.run(exercise())
