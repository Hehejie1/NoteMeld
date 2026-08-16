from __future__ import annotations

import pytest

from app.agent_host.turn_manager import SessionBusyError, TurnManager


def test_only_one_active_turn_per_session(monkeypatch):
    created = []
    monkeypatch.setattr("app.agent_host.turn_manager.agent_store.create_turn", lambda *a, **k: created.append(k) or {"turn_id": "t1", "status": "created"})
    manager = TurnManager()
    manager.start_turn("session-1", "hello")
    with pytest.raises(SessionBusyError):
        manager.start_turn("session-1", "again")
    assert len(created) == 1


def test_finish_removes_active_turn(monkeypatch):
    monkeypatch.setattr("app.agent_host.turn_manager.agent_store.create_turn", lambda *a, **k: {"turn_id": "t1", "status": "created"})
    monkeypatch.setattr("app.agent_host.turn_manager.agent_store.transition_turn", lambda *a, **k: {"turn_id": "t1", "status": k["status"]})
    manager = TurnManager()
    manager.start_turn("session-1", "hello")
    manager.finish_turn("session-1", "t1", "succeeded", {"content": "ok"})
    assert manager.active_turn("session-1") is None
