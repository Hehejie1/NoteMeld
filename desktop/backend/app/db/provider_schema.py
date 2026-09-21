from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from app.security import model_secret

logger = logging.getLogger(__name__)

_PROVIDER_CATALOG_COLUMNS: dict[str, str] = {
    "display_name": "ALTER TABLE providers ADD COLUMN display_name TEXT",
    "vendor_id": "ALTER TABLE providers ADD COLUMN vendor_id TEXT NOT NULL DEFAULT 'custom'",
    "protocol": "ALTER TABLE providers ADD COLUMN protocol TEXT NOT NULL DEFAULT 'openai-compatible'",
    "auth_type": "ALTER TABLE providers ADD COLUMN auth_type TEXT NOT NULL DEFAULT 'api_key'",
    "api_key_ciphertext": "ALTER TABLE providers ADD COLUMN api_key_ciphertext TEXT",
    "updated_at": "ALTER TABLE providers ADD COLUMN updated_at DATETIME",
}


def _copy_table_without_type(engine, table_name: str, create_sql: str, insert_sql: str) -> None:
    temp_table_name = f"{table_name}__type_cleanup"
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {temp_table_name}"))
        conn.execute(text(create_sql.format(temp_table_name=temp_table_name)))
        conn.execute(text(insert_sql.format(temp_table_name=temp_table_name)))
        conn.execute(text(f"DROP TABLE {table_name}"))
        conn.execute(text(f"ALTER TABLE {temp_table_name} RENAME TO {table_name}"))


def ensure_provider_catalog_schema(engine) -> dict[str, int]:
    """notemeld.model-add.v1 协议字段的 additive 迁移。

    - 仅加列/回填，绝不删行、不清表（区别于 models 历史上的一次性清空迁移）。
    - 历史明文 api_key 逐行加密入 api_key_ciphertext，成功后清空明文列内容（列保留）。
    - 可重复执行：已有密文的行不再处理；失败行保留明文并只记录 id。
    """
    inspector = inspect(engine)
    if "providers" not in inspector.get_table_names():
        return {"encrypted_keys": 0, "failed_keys": 0}

    existing_columns = {column["name"] for column in inspector.get_columns("providers")}
    pending = [sql for name, sql in _PROVIDER_CATALOG_COLUMNS.items() if name not in existing_columns]
    if not pending and "api_key_ciphertext" in existing_columns:
        return {"encrypted_keys": 0, "failed_keys": 0}

    encrypted = 0
    failed = 0
    with engine.begin() as conn:
        for sql in pending:
            conn.execute(text(sql))
        # updated_at 回填：SQLite 的 ADD COLUMN 不允许 CURRENT_TIMESTAMP 默认值，先加可空列再补
        conn.execute(text(
            "UPDATE providers SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"
        ))
        # display_name 回填（旧版本只有 name）
        conn.execute(text("UPDATE providers SET display_name = name WHERE display_name IS NULL"))
        # 历史 ollama 行按旧启发式补协议标记，其余保持默认 openai-compatible
        # 注意：LIKE 模式中的 ":" 会被 SQLAlchemy 当作绑定参数前缀，必须通过参数传入
        conn.execute(text(
            "UPDATE providers SET protocol = 'ollama' "
            "WHERE protocol = 'openai-compatible' "
            "AND (lower(name) = 'ollama' OR base_url LIKE :port_pattern OR base_url LIKE :loopback_pattern)"
        ), {"port_pattern": "%:11434%", "loopback_pattern": "%//127.0.0.1:11434%"})
        rows = conn.execute(text(
            "SELECT id, api_key, api_key_ciphertext FROM providers "
            "WHERE COALESCE(api_key_ciphertext, '') = '' AND COALESCE(api_key, '') != ''"
        )).fetchall()
        for row in rows:
            provider_id, plaintext, _ciphertext = row
            try:
                ciphertext = model_secret.encrypt(plaintext)
                conn.execute(
                    text("UPDATE providers SET api_key_ciphertext = :ct, api_key = '' WHERE id = :id"),
                    {"ct": ciphertext, "id": provider_id},
                )
                encrypted += 1
            except Exception:  # noqa: BLE001 - 迁移不能因单行失败中断，日志只允许出现 id
                failed += 1
                logger.warning("Provider 密钥加密迁移失败，已保留原明文行 provider_id=%s", provider_id)

    if encrypted or failed:
        logger.info(
            "Provider catalog schema migrated: encrypted_keys=%s failed_keys=%s",
            encrypted,
            failed,
        )
    return {"encrypted_keys": encrypted, "failed_keys": failed}


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
