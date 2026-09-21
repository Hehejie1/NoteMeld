from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


_RUNTIME_COLUMN_MIGRATIONS: dict[str, str] = {
    "context_window_tokens": "ALTER TABLE models ADD COLUMN context_window_tokens INTEGER NOT NULL DEFAULT 4096",
    "max_input_tokens": "ALTER TABLE models ADD COLUMN max_input_tokens INTEGER NOT NULL DEFAULT 3072",
    "max_output_tokens": "ALTER TABLE models ADD COLUMN max_output_tokens INTEGER NOT NULL DEFAULT 1024",
    "supports_vision": "ALTER TABLE models ADD COLUMN supports_vision BOOLEAN NOT NULL DEFAULT 0",
    "supports_stream": "ALTER TABLE models ADD COLUMN supports_stream BOOLEAN NOT NULL DEFAULT 1",
}
_MODEL_UNIQUE_INDEX_NAME = "uq_models_provider_model"

# notemeld.model-add.v1 目录字段：纯 additive，缺失不触清表（清表只绑定上面的运行字段一次性迁移）
_MODEL_CATALOG_COLUMN_MIGRATIONS: dict[str, str] = {
    "model_id": "ALTER TABLE models ADD COLUMN model_id TEXT",
    "display_name": "ALTER TABLE models ADD COLUMN display_name TEXT",
    "enabled": "ALTER TABLE models ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1",
    "is_default": "ALTER TABLE models ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0",
    "test_status": "ALTER TABLE models ADD COLUMN test_status TEXT NOT NULL DEFAULT 'unknown'",
    "updated_at": "ALTER TABLE models ADD COLUMN updated_at DATETIME",
}
_MODEL_ID_PARTIAL_INDEX_NAME = "uq_models_provider_model_id_partial"


def _has_index(inspector, name: str) -> bool:
    return any(index.get("name") == name for index in inspector.get_indexes("models"))


def ensure_model_catalog_schema(engine: Engine) -> bool:
    """models 表的协议目录字段迁移：加列、回填 model_id/display_name、建部分唯一索引。

    幂等且绝不删行；与 ensure_model_runtime_schema 的历史清空行为完全隔离。
    """
    inspector = inspect(engine)
    if "models" not in inspector.get_table_names():
        return False

    existing_columns = {column["name"] for column in inspector.get_columns("models")}
    pending = [
        sql for name, sql in _MODEL_CATALOG_COLUMN_MIGRATIONS.items() if name not in existing_columns
    ]
    needs_partial_index = not _has_index(inspector, _MODEL_ID_PARTIAL_INDEX_NAME) and not _has_index(
        inspector, "uq_models_provider_model_id"
    )
    if not pending and not needs_partial_index:
        return False

    with engine.begin() as conn:
        for sql in pending:
            conn.execute(text(sql))
        conn.execute(text("UPDATE models SET model_id = model_name WHERE model_id IS NULL OR model_id = ''"))
        conn.execute(text(
            "UPDATE models SET display_name = model_name WHERE display_name IS NULL OR display_name = ''"
        ))
        # updated_at 回填：SQLite 的 ADD COLUMN 不允许 CURRENT_TIMESTAMP 默认值，先加可空列再补
        conn.execute(text(
            "UPDATE models SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"
        ))
        if needs_partial_index:
            # 旧库 model_id 列可空：用部分唯一索引，仅约束已回填的协议标识
            conn.execute(text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {_MODEL_ID_PARTIAL_INDEX_NAME} "
                "ON models (provider_id, model_id) WHERE model_id IS NOT NULL"
            ))
    return True


def _has_model_identity_constraint(inspector) -> bool:
    expected_columns = {"provider_id", "model_name"}
    unique_constraints = inspector.get_unique_constraints("models")
    indexes = inspector.get_indexes("models")
    return any(set(constraint.get("column_names") or []) == expected_columns for constraint in unique_constraints) or any(
        index.get("unique") and set(index.get("column_names") or []) == expected_columns
        for index in indexes
    )


def ensure_model_runtime_schema(engine: Engine) -> dict[str, object]:
    """Upgrade model runtime fields and clear only stale model configuration.

    The destructive reset is deliberately tied to a missing runtime field, so a
    complete schema is safe to check at every application startup.
    """
    inspector = inspect(engine)
    if "models" not in inspector.get_table_names():
        return {
            "upgraded": False,
            "cleared_models": 0,
            "cleared_capabilities": 0,
        }

    existing_columns = {column["name"] for column in inspector.get_columns("models")}
    pending_migrations = [
        sql for name, sql in _RUNTIME_COLUMN_MIGRATIONS.items() if name not in existing_columns
    ]
    needs_unique_index = not _has_model_identity_constraint(inspector)
    if not pending_migrations and not needs_unique_index:
        return {
            "upgraded": False,
            "cleared_models": 0,
            "cleared_capabilities": 0,
        }

    with engine.begin() as conn:
        for sql in pending_migrations:
            conn.execute(text(sql))

        cleared_models = 0
        cleared_capabilities = 0
        # Runtime limit additions are additive. Do not erase saved providers/models
        # when upgrading an installation that already has the core runtime fields.
        if pending_migrations and any(name not in existing_columns for name in ("context_window_tokens", "supports_vision", "supports_stream")):
            cleared_models = conn.execute(text("SELECT COUNT(*) FROM models")).scalar_one()
            cleared_capabilities = conn.execute(
                text("SELECT COUNT(*) FROM model_capabilities")
            ).scalar_one()
            conn.execute(text("DELETE FROM models"))
            conn.execute(text("DELETE FROM model_capabilities"))

        if needs_unique_index:
            conn.execute(text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {_MODEL_UNIQUE_INDEX_NAME} "
                "ON models (provider_id, model_name)"
            ))

    return {
        "upgraded": bool(pending_migrations),
        "cleared_models": cleared_models,
        "cleared_capabilities": cleared_capabilities,
    }


__all__ = ["ensure_model_runtime_schema", "ensure_model_catalog_schema"]
