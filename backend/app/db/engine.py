from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

from app.utils.storage_paths import database_path

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT_DIR = Path(__file__).resolve().parents[3]


def _default_sqlite_path() -> Path:
    return database_path()


def _legacy_sqlite_paths() -> list[Path]:
    raw_paths = os.getenv("NOTEMELD_IMPORT_SQLITE_PATHS", "")
    paths = []
    for raw_path in raw_paths.split(os.pathsep):
        if not raw_path:
            continue

        path_obj = Path(raw_path)
        paths.append(path_obj if path_obj.is_absolute() else (PROJECT_ROOT_DIR / path_obj).resolve())

    return paths


def _resolve_database_url(database_url: str | None) -> str:
    if not database_url:
        return f"sqlite:///{_default_sqlite_path()}"

    if not database_url.startswith("sqlite:///"):
        return database_url

    sqlite_path = database_url[len("sqlite:///"):]
    if not sqlite_path:
        return f"sqlite:///{_default_sqlite_path()}"

    path_obj = Path(sqlite_path)
    if path_obj.is_absolute():
        return f"sqlite:///{path_obj}"

    return f"sqlite:///{(BACKEND_DIR / path_obj).resolve()}"


def _sqlite_file_from_url(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    return Path(database_url[len("sqlite:///"):])


def _sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _read_table_rows(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    cursor = conn.execute(f"SELECT * FROM {table_name}")
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _record_exists(conn: sqlite3.Connection, table_name: str, record: dict, unique_columns: list[str]) -> bool:
    where_clause = " AND ".join([f"{column} IS ?" for column in unique_columns])
    params = [record.get(column) for column in unique_columns]
    row = conn.execute(
        f"SELECT 1 FROM {table_name} WHERE {where_clause} LIMIT 1",
        params,
    ).fetchone()
    return row is not None


def merge_legacy_sqlite_data(current_db_path: str | Path, legacy_db_path: str | Path) -> dict[str, int]:
    current_path = Path(current_db_path)
    legacy_path = Path(legacy_db_path)
    migrated_counts = {
        "providers": 0,
        "models": 0,
        "video_tasks": 0,
        "model_usage_records": 0,
        "conversations": 0,
        "conversation_messages": 0,
        "note_documents": 0,
    }

    if not current_path.exists() or not legacy_path.exists() or current_path.resolve() == legacy_path.resolve():
        return migrated_counts

    table_configs = {
        "providers": {
            "insert_columns": ["id", "name", "logo", "api_key", "base_url", "enabled", "created_at"],
            "unique_columns": ["id"],
        },
        "video_tasks": {
            "insert_columns": ["video_id", "platform", "task_id", "created_at"],
            "unique_columns": ["task_id"],
        },
        "model_usage_records": {
            "insert_columns": [
                "task_id",
                "provider_id",
                "provider_name",
                "model_name",
                "phase",
                "platform",
                "video_id",
                "video_title",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "status",
                "error_message",
                "request_started_at",
                "request_finished_at",
                "duration_ms",
                "request_meta_json",
                "created_at",
            ],
            "unique_columns": [
                "task_id",
                "provider_id",
                "provider_name",
                "model_name",
                "phase",
                "platform",
                "video_id",
                "video_title",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "status",
                "error_message",
                "request_started_at",
                "request_finished_at",
                "duration_ms",
                "request_meta_json",
                "created_at",
            ],
        },
        "conversations": {
            "insert_columns": [
                "id",
                "mode",
                "title",
                "status",
                "message",
                "platform",
                "linked_note_task_id",
                "note_state",
                "form_data_json",
                "transcript_json",
                "audio_meta_json",
                "markdown_json",
                "created_at",
                "updated_at",
                "deleted_at",
            ],
            "unique_columns": ["id"],
        },
        "conversation_messages": {
            "insert_columns": [
                "id",
                "conversation_id",
                "role",
                "message_type",
                "content",
                "status",
                "meta_json",
                "sources_json",
                "error",
                "created_at",
                "updated_at",
            ],
            "unique_columns": ["id"],
        },
        "note_documents": {
            "insert_columns": [
                "task_id",
                "conversation_id",
                "title",
                "content",
                "source_url",
                "platform",
                "model_name",
                "style",
                "status",
                "wiki_status",
                "created_at",
                "updated_at",
                "deleted_at",
            ],
            "unique_columns": ["task_id"],
        },
    }

    current_conn = sqlite3.connect(current_path)
    legacy_conn = sqlite3.connect(legacy_path)
    try:
        for table_name, config in table_configs.items():
            if not _sqlite_table_exists(current_conn, table_name) or not _sqlite_table_exists(legacy_conn, table_name):
                continue

            rows = _read_table_rows(legacy_conn, table_name)
            insert_columns = config["insert_columns"]
            unique_columns = config["unique_columns"]
            placeholders = ", ".join(["?"] * len(insert_columns))
            column_sql = ", ".join(insert_columns)

            for row in rows:
                record = {column: row.get(column) for column in insert_columns}
                if _record_exists(current_conn, table_name, record, unique_columns):
                    continue

                current_conn.execute(
                    f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})",
                    [record.get(column) for column in insert_columns],
                )
                migrated_counts[table_name] += 1

        current_conn.commit()
        return migrated_counts
    finally:
        legacy_conn.close()
        current_conn.close()


def migrate_legacy_sqlite_if_needed(database_url: str) -> dict[str, int]:
    current_path = _sqlite_file_from_url(database_url)
    if current_path is None:
        return {}

    migrated_counts = {
        "providers": 0,
        "models": 0,
        "video_tasks": 0,
        "model_usage_records": 0,
        "conversations": 0,
        "conversation_messages": 0,
        "note_documents": 0,
    }
    for legacy_path in _legacy_sqlite_paths():
        if current_path.resolve() == legacy_path.resolve():
            continue

        for table_name, count in merge_legacy_sqlite_data(current_path, legacy_path).items():
            migrated_counts[table_name] = migrated_counts.get(table_name, 0) + count

    return migrated_counts


# NoteMeld owns one local database below the unified data root.
DATABASE_URL = f"sqlite:///{_default_sqlite_path()}"

# SQLite 需要特定连接参数，其他数据库不需要
engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}
    sqlite_file = _sqlite_file_from_url(DATABASE_URL)
    if sqlite_file is not None:
        sqlite_file.parent.mkdir(parents=True, exist_ok=True)

_pool_args = {}
if not DATABASE_URL.startswith("sqlite"):
    _pool_args = {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_pre_ping": True,
    }

engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true",
    **engine_args,
    **_pool_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_engine():
    return engine


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
