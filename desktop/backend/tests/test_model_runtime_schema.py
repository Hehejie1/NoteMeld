from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db import model_dao
from app.db.engine import Base, merge_legacy_sqlite_data
from app.db import init_db as init_db_module
from app.db.models.providers import Provider
from app.db.model_schema import ensure_model_runtime_schema


def _create_legacy_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE models (
                id INTEGER PRIMARY KEY,
                provider_id TEXT NOT NULL,
                model_name TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE model_capabilities (
                id INTEGER PRIMARY KEY,
                provider_id TEXT NOT NULL,
                model_name TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE note_documents (
                task_id TEXT PRIMARY KEY,
                content TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE conversation_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE model_usage_records (
                id INTEGER PRIMARY KEY,
                model_name TEXT NOT NULL
            )
        """))

        for table_name, columns, values in (
            ("models", "id, provider_id, model_name", "1, 'provider-1', 'old-model'"),
            ("model_capabilities", "id, provider_id, model_name", "1, 'provider-1', 'old-model'"),
            ("providers", "id, name", "'provider-1', 'Provider'"),
            ("note_documents", "task_id, content", "'note-1', 'note'"),
            ("conversations", "id, title", "'conversation-1', 'Conversation'"),
            ("conversation_messages", "id, conversation_id, content", "'message-1', 'conversation-1', 'message'"),
            ("model_usage_records", "id, model_name", "1, 'old-model'"),
        ):
            conn.execute(text(f"INSERT INTO {table_name} ({columns}) VALUES ({values})"))


def _columns(engine, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def _count(engine, table_name: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()


def test_runtime_schema_upgrade_clears_only_model_configuration_once():
    engine = create_engine("sqlite://")
    _create_legacy_schema(engine)

    result = ensure_model_runtime_schema(engine)

    assert result == {
        "upgraded": True,
        "cleared_models": 1,
        "cleared_capabilities": 1,
    }
    assert _columns(engine, "models") >= {
        "context_window_tokens",
        "supports_vision",
        "supports_stream",
    }
    assert _count(engine, "models") == 0
    assert _count(engine, "model_capabilities") == 0
    assert _count(engine, "providers") == 1
    assert _count(engine, "note_documents") == 1
    assert _count(engine, "conversations") == 1
    assert _count(engine, "conversation_messages") == 1
    assert _count(engine, "model_usage_records") == 1

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO models (
                provider_id, model_name, context_window_tokens, supports_vision, supports_stream
            ) VALUES ('provider-1', 'new-model', 8192, 1, 1)
        """))

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO models (
                    provider_id, model_name, context_window_tokens, supports_vision, supports_stream
                ) VALUES ('provider-1', 'new-model', 8192, 1, 1)
            """))

    assert ensure_model_runtime_schema(engine) == {
        "upgraded": False,
        "cleared_models": 0,
        "cleared_capabilities": 0,
    }
    assert _count(engine, "models") == 1


def test_complete_runtime_schema_adds_unique_index_without_clearing_saved_model():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE models (
                id INTEGER PRIMARY KEY,
                provider_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                context_window_tokens INTEGER NOT NULL DEFAULT 4096,
                supports_vision BOOLEAN NOT NULL DEFAULT 0,
                supports_stream BOOLEAN NOT NULL DEFAULT 1
            )
        """))
        conn.execute(text("""
            CREATE TABLE model_capabilities (
                id INTEGER PRIMARY KEY,
                provider_id TEXT NOT NULL,
                model_name TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO models (provider_id, model_name, context_window_tokens, supports_vision, supports_stream)
            VALUES ('provider-1', 'saved-model', 32768, 1, 1)
        """))

    assert ensure_model_runtime_schema(engine) == {
        "upgraded": False,
        "cleared_models": 0,
        "cleared_capabilities": 0,
    }
    assert _count(engine, "models") == 1
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO models (provider_id, model_name, context_window_tokens, supports_vision, supports_stream)
                VALUES ('provider-1', 'saved-model', 32768, 1, 1)
            """))


def test_model_dao_persists_runtime_fields_and_returns_deleted_identity(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def get_test_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(model_dao, "get_db", get_test_db)
    with session_factory.begin() as db:
        db.add(Provider(
            id="provider-1",
            name="Provider",
            logo="",
            api_key="",
            base_url="http://localhost",
            enabled=1,
        ))

    created = model_dao.insert_model(
        provider_id="provider-1",
        model_name="runtime-model",
        context_window_tokens=8192,
        supports_vision=True,
        supports_stream=False,
    )

    for row in (
        created,
        model_dao.get_model_by_provider_and_name("provider-1", "runtime-model"),
        model_dao.get_models_by_provider("provider-1")[0],
        model_dao.get_all_models()[0],
    ):
        assert row is not None
        assert row["context_window_tokens"] == 8192
        assert row["supports_vision"] is True
        assert row["supports_stream"] is False

    assert model_dao.delete_model(created["id"]) == {
        "id": created["id"],
        "provider_id": "provider-1",
        "model_name": "runtime-model",
    }
    assert model_dao.delete_model(created["id"]) is None


def test_legacy_model_import_skips_models_but_keeps_provider(tmp_path):
    current_db_path = tmp_path / "current.db"
    legacy_db_path = tmp_path / "legacy.db"
    current_engine = create_engine(f"sqlite:///{current_db_path}")
    Base.metadata.create_all(current_engine)
    current_engine.dispose()

    with sqlite3.connect(legacy_db_path) as conn:
        conn.execute("""
            CREATE TABLE providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                logo TEXT NOT NULL,
                api_key TEXT NOT NULL,
                base_url TEXT NOT NULL,
                enabled INTEGER,
                created_at DATETIME
            )
        """)
        conn.execute("""
            CREATE TABLE models (
                id INTEGER PRIMARY KEY,
                provider_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                created_at DATETIME
            )
        """)
        conn.execute("""
            INSERT INTO providers (id, name, logo, api_key, base_url, enabled)
            VALUES ('provider-1', 'Provider', '', '', 'http://localhost', 1)
        """)
        conn.execute("""
            INSERT INTO models (provider_id, model_name)
            VALUES ('provider-1', 'legacy-model')
        """)

    migrated = merge_legacy_sqlite_data(current_db_path, legacy_db_path)
    assert migrated["providers"] == 1
    assert migrated["models"] == 0
    with create_engine(f"sqlite:///{current_db_path}").connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM providers")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM models")).scalar_one() == 0


def test_init_db_imports_legacy_provider_and_note_but_never_model_rows(tmp_path, monkeypatch):
    current_db_path = tmp_path / "current.db"
    legacy_db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{current_db_path}")

    with sqlite3.connect(legacy_db_path) as conn:
        conn.executescript("""
            CREATE TABLE providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                logo TEXT NOT NULL,
                api_key TEXT NOT NULL,
                base_url TEXT NOT NULL,
                enabled INTEGER,
                created_at DATETIME
            );
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                mode TEXT,
                title TEXT,
                status TEXT,
                message TEXT,
                platform TEXT,
                linked_note_task_id TEXT,
                note_state TEXT,
                form_data_json TEXT,
                transcript_json TEXT,
                audio_meta_json TEXT,
                markdown_json TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                deleted_at DATETIME
            );
            CREATE TABLE models (
                id INTEGER PRIMARY KEY,
                provider_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                context_window_tokens INTEGER NOT NULL,
                supports_vision BOOLEAN NOT NULL,
                supports_stream BOOLEAN NOT NULL,
                created_at DATETIME
            );
            CREATE TABLE note_documents (
                task_id TEXT PRIMARY KEY,
                conversation_id TEXT,
                title TEXT,
                content TEXT,
                source_url TEXT,
                platform TEXT,
                model_name TEXT,
                style TEXT,
                status TEXT,
                wiki_status TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                deleted_at DATETIME
            );
            INSERT INTO providers (id, name, logo, api_key, base_url, enabled)
            VALUES ('provider-1', 'Provider', '', '', 'http://localhost', 1);
            INSERT INTO models (
                provider_id, model_name, context_window_tokens, supports_vision, supports_stream
            ) VALUES ('provider-1', 'legacy-model', 131072, 1, 0);
            INSERT INTO conversations (
                id, mode, title, status, note_state, form_data_json,
                transcript_json, audio_meta_json, markdown_json
            ) VALUES (
                'conversation-1', 'note', 'Legacy note', 'SUCCESS', 'ready',
                '{}', '{}', '{}', '""'
            );
            INSERT INTO note_documents (task_id, conversation_id, title, content, status, wiki_status)
            VALUES (
                'note-1', 'conversation-1', 'Legacy note', '# Legacy note',
                'SUCCESS', 'pending'
            );
        """)

    monkeypatch.setattr(init_db_module, "get_engine", lambda: engine)
    monkeypatch.setattr(init_db_module, "DATABASE_URL", f"sqlite:///{current_db_path}")
    monkeypatch.setenv("NOTEMELD_IMPORT_SQLITE_PATHS", str(legacy_db_path))
    monkeypatch.setattr(init_db_module, "ensure_note_style_columns", lambda: None)
    monkeypatch.setattr(init_db_module, "bootstrap_conversations_from_storage", lambda: {})

    init_db_module.init_db()

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM providers")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM note_documents")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM models")).scalar_one() == 0
