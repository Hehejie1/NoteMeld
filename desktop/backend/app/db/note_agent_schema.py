"""N02 Note adapter schema with an isolated migration registry."""

from __future__ import annotations

import sqlite3
from pathlib import Path

NOTE_AGENT_SCHEMA_VERSION = 1

_MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS note_agent_sources (
            source_id TEXT PRIMARY KEY NOT NULL,
            note_id TEXT NOT NULL,
            authority TEXT NOT NULL,
            locator TEXT NOT NULL,
            digest TEXT,
            captured_at TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
                CHECK (json_valid(metadata_json)),
            operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (note_id) REFERENCES note_documents(task_id)
        );
        CREATE INDEX IF NOT EXISTS idx_note_agent_sources_note
            ON note_agent_sources(note_id);

        CREATE TABLE IF NOT EXISTS note_agent_relations (
            relation_id TEXT PRIMARY KEY NOT NULL,
            from_note_id TEXT NOT NULL,
            to_note_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (from_note_id) REFERENCES note_documents(task_id),
            FOREIGN KEY (to_note_id) REFERENCES note_documents(task_id),
            CHECK (from_note_id <> to_note_id)
        );
        CREATE INDEX IF NOT EXISTS idx_note_agent_relations_from
            ON note_agent_relations(from_note_id);
        CREATE INDEX IF NOT EXISTS idx_note_agent_relations_to
            ON note_agent_relations(to_note_id);

        CREATE TABLE IF NOT EXISTS note_agent_operations (
            operation_id TEXT PRIMARY KEY NOT NULL,
            request_id TEXT NOT NULL UNIQUE,
            payload_hash TEXT NOT NULL,
            kind TEXT NOT NULL,
            note_id TEXT,
            expected_version INTEGER,
            status TEXT NOT NULL,
            checkpoint_json TEXT,
            outcome_json TEXT CHECK (
                outcome_json IS NULL OR json_valid(outcome_json)
            ),
            error_json TEXT CHECK (error_json IS NULL OR json_valid(error_json)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (status IN (
                'begun', 'checkpointed', 'committed', 'failed',
                'needs_attention'
            ))
        );
        CREATE INDEX IF NOT EXISTS idx_note_agent_operations_status
            ON note_agent_operations(status);

        CREATE TABLE IF NOT EXISTS note_agent_provenance (
            provenance_id TEXT PRIMARY KEY NOT NULL,
            note_id TEXT,
            note_version INTEGER,
            operation_id TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            actor_kind TEXT NOT NULL,
            plugin_id TEXT,
            plugin_version TEXT,
            turn_id TEXT,
            source_ids_json TEXT NOT NULL DEFAULT '[]'
                CHECK (json_valid(source_ids_json)),
            created_at TEXT NOT NULL,
            FOREIGN KEY (note_id) REFERENCES note_documents(task_id),
            FOREIGN KEY (operation_id) REFERENCES note_agent_operations(operation_id),
            UNIQUE (note_id, note_version),
            CHECK (note_version IS NULL OR note_version > 0)
        );
        CREATE INDEX IF NOT EXISTS idx_note_agent_provenance_operation
            ON note_agent_provenance(operation_id);
        """,
    ),
)


def connect_note_agent_database(database_path: str | Path) -> sqlite3.Connection:
    """Open a short-lived product connection with the adapter invariants enabled."""
    connection = sqlite3.connect(Path(database_path), timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def ensure_note_agent_schema(database_path: str | Path) -> None:
    """Apply forward-only N02 migrations without touching ``user_version``."""
    connection = connect_note_agent_database(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS note_agent_app_migrations (
                version INTEGER PRIMARY KEY NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()
        applied = {
            int(row[0])
            for row in connection.execute(
                "SELECT version FROM note_agent_app_migrations"
            ).fetchall()
        }
        newer = [version for version in applied if version > NOTE_AGENT_SCHEMA_VERSION]
        if newer:
            raise RuntimeError(
                f"note adapter schema {max(newer)} is newer than supported "
                f"{NOTE_AGENT_SCHEMA_VERSION}"
            )
        for version, sql in _MIGRATIONS:
            if version in applied:
                continue
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                f"{sql}\n"
                "INSERT OR IGNORE INTO note_agent_app_migrations(version) "
                f"VALUES ({version});\n"
                "COMMIT;"
            )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


__all__ = [
    "NOTE_AGENT_SCHEMA_VERSION",
    "connect_note_agent_database",
    "ensure_note_agent_schema",
]
