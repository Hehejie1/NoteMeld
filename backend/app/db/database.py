from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.db.engine import Base


def _has_unique_index(engine: Engine, table: str, index_name: str) -> bool:
    inspector = inspect(engine)
    return any(
        index["name"] == index_name and index["unique"] is True
        for index in inspector.get_indexes(table)
    )


def _create_agent_indexes(engine: Engine) -> None:
    with engine.connect() as conn:
        if not _has_unique_index(engine, "agent_turns", "uq_agent_turns_session_idempotency_key"):
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_turns_session_idempotency_key "
                "ON agent_turns (session_id, idempotency_key) "
                "WHERE idempotency_key IS NOT NULL"
            ))

        if not _has_unique_index(engine, "agent_events", "uq_agent_events_turn_sequence"):
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_events_turn_sequence "
                "ON agent_events (turn_id, sequence)"
            ))
        conn.commit()


def ensure_agent_schema(engine: Engine | None = None) -> None:
    if engine is None:
        from app.db.engine import engine as _engine

        engine = _engine

    # Keep schema upgrade minimal: only add agent tables/indexes when missing.
    Base.metadata.create_all(
        bind=engine,
        tables={Base.metadata.tables["agent_turns"], Base.metadata.tables["agent_events"], Base.metadata.tables["agent_preferences"]},
    )
    _create_agent_indexes(engine)


__all__ = ["ensure_agent_schema"]
