from __future__ import annotations

from types import SimpleNamespace

from app.services import agent_store


def test_recover_nonterminal_marks_interrupted_and_emits_terminal(monkeypatch):
    active = SimpleNamespace(turn_id="turn-active", status="running", error_code=None, error_message=None)
    terminal = SimpleNamespace(turn_id="turn-done", status="succeeded", error_code=None, error_message=None)

    class Query:
        def filter(self, *_args):
            return self

        def with_for_update(self):
            return self

        def all(self):
            return [active]

    class Transaction:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class DB:
        def query(self, *_args):
            return Query()

        def begin(self):
            return Transaction()

        def close(self):
            return None

    events = []
    monkeypatch.setattr(agent_store, "_db", lambda: DB())
    monkeypatch.setattr(agent_store, "_append_event", lambda *_args, **kwargs: events.append(kwargs))

    recovered = agent_store.recover_nonterminal()

    assert recovered == ["turn-active"]
    assert active.status == "interrupted"
    assert active.error_code == "interrupted"
    assert events[0]["event_type"] == "turn.interrupted"
    assert events[0]["payload"]["reason"] == "host_restart"
    assert terminal.status == "succeeded"
