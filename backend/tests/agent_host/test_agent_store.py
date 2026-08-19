from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.db.models.conversation import Conversation
from app.services import agent_store


def _make_session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'agent_host_store.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        session.add(
            Conversation(
                id="conv-1",
                mode="chat",
                title="test",
                status="SUCCESS",
                note_state="none",
                form_data_json="{}",
                transcript_json="{}",
                audio_meta_json="{}",
                markdown_json='""',
            )
        )
        session.commit()

    return session_factory


def test_create_turn_idempotency_and_missing_session(monkeypatch, tmp_path):
    session_factory = _make_session_factory(tmp_path)
    monkeypatch.setattr(agent_store, "_db", session_factory)

    first = agent_store.create_turn("conv-1", turn_id="turn-1", idempotency_key="k-1", status="created")
    second = agent_store.create_turn("conv-1", turn_id="turn-2", idempotency_key="k-1")

    assert first["turn_id"] == "turn-1"
    assert second["turn_id"] == "turn-1"
    assert second["_replayed"] is True

    with pytest.raises(agent_store.TurnNotFoundError):
        agent_store.create_turn("missing-session", turn_id="turn-missing")


def test_create_turn_blocks_parallel_active_turn_in_same_session(monkeypatch, tmp_path):
    session_factory = _make_session_factory(tmp_path)
    monkeypatch.setattr(agent_store, "_db", session_factory)

    agent_store.create_turn("conv-1", turn_id="turn-1", status="running")

    with pytest.raises(agent_store.SessionBusyError):
        agent_store.create_turn("conv-1", turn_id="turn-2")


def test_create_turn_allows_replay_when_session_is_busy(monkeypatch, tmp_path):
    session_factory = _make_session_factory(tmp_path)
    monkeypatch.setattr(agent_store, "_db", session_factory)

    first = agent_store.create_turn("conv-1", turn_id="turn-1", idempotency_key="reuse", status="running")
    second = agent_store.create_turn("conv-1", turn_id="turn-2", idempotency_key="reuse")

    assert first["turn_id"] == second["turn_id"]
    assert second["_replayed"] is True


def test_append_event_sequence_and_list(monkeypatch, tmp_path):
    session_factory = _make_session_factory(tmp_path)
    monkeypatch.setattr(agent_store, "_db", session_factory)

    turn = agent_store.create_turn("conv-1", turn_id="turn-1")
    first_event = agent_store.append_event(turn["turn_id"], {"type": "message-1"}, event_type="assistant")
    second_event = agent_store.append_event(turn["turn_id"], {"type": "message-2"}, event_type="assistant")

    assert first_event["sequence"] == 0
    assert second_event["sequence"] == 1

    events = agent_store.list_events(turn["turn_id"])
    assert [item["sequence"] for item in events] == [0, 1]


def test_append_event_rejects_sequence_conflict(monkeypatch, tmp_path):
    session_factory = _make_session_factory(tmp_path)
    monkeypatch.setattr(agent_store, "_db", session_factory)

    turn = agent_store.create_turn("conv-1", turn_id="turn-1")
    agent_store.append_event(turn["turn_id"], {"type": "message"}, sequence=0)

    with pytest.raises(agent_store.TurnStoreSequenceError):
        agent_store.append_event(turn["turn_id"], {"type": "dup"}, sequence=0)


def test_transition_turn_atomic_terminal_event(monkeypatch, tmp_path):
    session_factory = _make_session_factory(tmp_path)
    monkeypatch.setattr(agent_store, "_db", session_factory)

    turn = agent_store.create_turn("conv-1", turn_id="turn-1")

    with pytest.raises(agent_store.TurnTerminalError):
        agent_store.transition_turn(turn["turn_id"], "succeeded", terminal_event=None)

    terminal = agent_store.transition_turn(
        turn["turn_id"],
        "succeeded",
        error_code="completed",
        error_message=None,
        terminal_event={"type": "terminal"},
        terminal_event_type="terminal",
    )
    assert terminal["status"] == "succeeded"
    assert terminal["error_code"] == "completed"

    events = agent_store.list_events(turn["turn_id"])
    assert events[-1]["sequence"] == 0
    assert events[-1]["event_type"] == "terminal"

    with pytest.raises(agent_store.TurnTerminalError):
        agent_store.append_event(turn["turn_id"], {"type": "late"})

    with pytest.raises(agent_store.TurnNotFoundError):
        agent_store.append_event("not-found", {"type": "miss"})


def test_model_preference_get_set_and_update(monkeypatch, tmp_path):
    session_factory = _make_session_factory(tmp_path)
    monkeypatch.setattr(agent_store, "_db", session_factory)

    assert agent_store.get_model_preference("conv-1") == {
        "session_id": "conv-1",
        "default_model_id": None,
        "fallback_models": [],
    }

    initial = agent_store.set_model_preference(
        "conv-1",
        default_model_id="gpt-4o",
        fallback_models=["gpt-4", "qwen"],
    )
    assert initial["default_model_id"] == "gpt-4o"
    assert initial["fallback_models"] == ["gpt-4", "qwen"]

    updated = agent_store.set_model_preference(
        "conv-1",
        default_model_id="o1-mini",
        fallback_models=["gpt-4o-mini"],
    )
    assert updated["default_model_id"] == "o1-mini"
    assert updated["fallback_models"] == ["gpt-4o-mini"]

    with pytest.raises(agent_store.PreferenceError):
        agent_store.set_model_preference("conv-1", default_model_id="gpt-4", fallback_models="not-list")

    with pytest.raises(agent_store.PreferenceError):
        agent_store.set_model_preference("conv-1", default_model_id="gpt-4", fallback_models=[1, 2, 3])

    with pytest.raises(agent_store.TurnNotFoundError):
        agent_store.set_model_preference("missing", default_model_id="gpt-4", fallback_models=[])
