from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


_RUNTIME_COLUMN_MIGRATIONS: dict[str, str] = {
    "context_window_tokens": "ALTER TABLE models ADD COLUMN context_window_tokens INTEGER NOT NULL DEFAULT 4096",
    "supports_vision": "ALTER TABLE models ADD COLUMN supports_vision BOOLEAN NOT NULL DEFAULT 0",
    "supports_stream": "ALTER TABLE models ADD COLUMN supports_stream BOOLEAN NOT NULL DEFAULT 1",
}
_MODEL_UNIQUE_INDEX_NAME = "uq_models_provider_model"


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
        if pending_migrations:
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


__all__ = ["ensure_model_runtime_schema"]
