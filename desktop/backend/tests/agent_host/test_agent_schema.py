from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.db.database import ensure_agent_schema


def _prepare_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'agent_host_schema.db'}")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                mode TEXT NOT NULL DEFAULT 'chat',
                title TEXT,
                status TEXT NOT NULL DEFAULT 'SUCCESS',
                message TEXT,
                platform TEXT,
                linked_note_task_id TEXT,
                note_state TEXT NOT NULL DEFAULT 'none',
                form_data_json TEXT NOT NULL DEFAULT '{}',
                transcript_json TEXT NOT NULL DEFAULT '{}',
                audio_meta_json TEXT NOT NULL DEFAULT '{}',
                markdown_json TEXT NOT NULL DEFAULT '""',
                research_space_id TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                deleted_at DATETIME
            )
        """))
    return engine


def _index_names(engine, table_name: str) -> set[str]:
    return {index["name"] for index in inspect(engine).get_indexes(table_name)}


def test_ensure_agent_schema_creates_tables_and_indexes(tmp_path):
    engine = _prepare_engine(tmp_path)

    ensure_agent_schema(engine)

    inspector = inspect(engine)
    assert {"agent_turns", "agent_events", "agent_preferences"} <= set(inspector.get_table_names())
    assert "uq_agent_turns_session_idempotency_key" in _index_names(engine, "agent_turns")
    assert "uq_agent_events_turn_sequence" in _index_names(engine, "agent_events")

    turn_columns = {column["name"] for column in inspector.get_columns("agent_turns")}
    event_columns = {column["name"] for column in inspector.get_columns("agent_events")}
    preference_columns = {column["name"] for column in inspector.get_columns("agent_preferences")}

    assert "turn_id" in turn_columns and "idempotency_key" in turn_columns
    assert "turn_id" in event_columns and "sequence" in event_columns
    assert "fallback_models_json" in preference_columns


def test_ensure_agent_schema_is_idempotent(tmp_path):
    engine = _prepare_engine(tmp_path)
    ensure_agent_schema(engine)
    first_turn_indexes = _index_names(engine, "agent_turns")
    first_event_indexes = _index_names(engine, "agent_events")

    ensure_agent_schema(engine)
    second_turn_indexes = _index_names(engine, "agent_turns")
    second_event_indexes = _index_names(engine, "agent_events")

    assert first_turn_indexes == second_turn_indexes
    assert first_event_indexes == second_event_indexes
