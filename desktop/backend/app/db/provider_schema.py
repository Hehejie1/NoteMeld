from __future__ import annotations

from sqlalchemy import inspect, text


def _copy_table_without_type(engine, table_name: str, create_sql: str, insert_sql: str) -> None:
    temp_table_name = f"{table_name}__type_cleanup"
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
        conn.execute(text(create_sql.format(temp_table_name=temp_table_name)))
        conn.execute(text(insert_sql.format(temp_table_name=temp_table_name)))
        conn.execute(text(f"DROP TABLE {table_name}"))
        conn.execute(text(f"ALTER TABLE {temp_table_name} RENAME TO {table_name}"))


def ensure_provider_schema(engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "providers" in table_names:
        provider_columns = {column["name"] for column in inspector.get_columns("providers")}
        if "type" in provider_columns:
            _copy_table_without_type(
                engine,
                "providers",
                """
                CREATE TABLE {temp_table_name} (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    logo TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    created_at DATETIME
                )
                """,
                """
                INSERT INTO {temp_table_name} (id, name, logo, api_key, base_url, enabled, created_at)
                SELECT id, name, logo, api_key, base_url, enabled, created_at
                FROM providers
                """,
            )

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "provider_templates" in table_names:
        template_columns = {column["name"] for column in inspector.get_columns("provider_templates")}
        if "type" in template_columns:
            _copy_table_without_type(
                engine,
                "provider_templates",
                """
                CREATE TABLE {temp_table_name} (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    logo TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    created_at DATETIME
                )
                """,
                """
                INSERT INTO {temp_table_name} (id, name, logo, base_url, created_at)
                SELECT id, name, logo, base_url, created_at
                FROM provider_templates
                """,
            )
