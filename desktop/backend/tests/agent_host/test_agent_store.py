from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.db.models.conversation import Conversation
from app.services import agent_store


def _make_session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'agent_host_store.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        session.add_all([
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
            ),
            Conversation(
                id="conv-2",
                mode="chat",
                title="other",
                status="SUCCESS",
                note_state="none",
                form_data_json="{}",
                transcript_json="{}",
                audio_meta_json="{}",
                markdown_json='""',
            ),
        ])
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


def test_concurrent_turn_creation_rejects_second_turn_in_same_session(monkeypatch, tmp_path):
    session_factory = _make_session_factory(tmp_path)
    monkeypatch.setattr(agent_store, "_db", session_factory)
    barrier = Barrier(2)

    def create(turn_id):
        barrier.wait()
        try:
            return agent_store.create_turn("conv-1", turn_id=turn_id)
        except agent_store.SessionBusyError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, ["turn-a", "turn-b"]))

    created = [result for result in results if isinstance(result, dict)]
    rejected = [result for result in results if isinstance(result, agent_store.SessionBusyError)]
    assert len(created) == 1
    assert len(rejected) == 1


def test_different_sessions_can_have_active_turns_concurrently(monkeypatch, tmp_path):
    session_factory = _make_session_factory(tmp_path)
    monkeypatch.setattr(agent_store, "_db", session_factory)
    barrier = Barrier(2)

    def create(item):
        session_id, turn_id = item
        barrier.wait()
        return agent_store.create_turn(session_id, turn_id=turn_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, [("conv-1", "turn-a"), ("conv-2", "turn-b")]))

    assert {result["session_id"] for result in results} == {"conv-1", "conv-2"}
    assert all(result["status"] == "created" for result in results)


def test_existing_conversation_is_the_only_session_state(monkeypatch, tmp_path):
    session_factory = _make_session_factory(tmp_path)
    monkeypatch.setattr(agent_store, "_db", session_factory)

    with session_factory() as session:
        before = session.query(Conversation).count()

    turn = agent_store.create_turn("conv-1", turn_id="continued-turn")
    agent_store.append_event(turn["turn_id"], {"delta": "ok"}, event_type="message.delta")

    with session_factory() as session:
        assert session.query(Conversation).count() == before
        assert session.get(Conversation, "conv-1") is not None
        table_names = set(inspect(session.get_bind()).get_table_names())
    assert turn["session_id"] == "conv-1"
    assert agent_store.list_events(turn["turn_id"])[0]["turn_id"] == turn["turn_id"]
    assert "agent_sessions" not in table_names
    assert "agent_messages" not in table_names


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


def test_approval_events_atomically_persist_waiting_and_running_status(monkeypatch, tmp_path):
    session_factory = _make_session_factory(tmp_path)
    monkeypatch.setattr(agent_store, "_db", session_factory)
    agent_store.create_turn("conv-1", turn_id="turn-approval", status="running")

    waiting = agent_store.transition_turn(
        "turn-approval",
        "waiting_approval",
        terminal_event={"type": "approval.required", "payload": {"approval_id": "approval-1"}},
        terminal_event_type="approval.required",
        event_sequence=4,
        event_id="event-required",
    )
    running = agent_store.transition_turn(
        "turn-approval",
        "running",
        terminal_event={"type": "approval.resolved", "payload": {"approval_id": "approval-1", "decision": "approve"}},
        terminal_event_type="approval.resolved",
        event_sequence=5,
        event_id="event-resolved",
    )

    assert waiting["status"] == "waiting_approval"
    assert running["status"] == "running"
    events = agent_store.list_events("turn-approval")
    assert [(event["sequence"], event["event_type"]) for event in events] == [
        (4, "approval.required"),
        (5, "approval.resolved"),
    ]
    assert events[0]["event_id"] == "event-required"


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
