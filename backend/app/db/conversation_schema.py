"""Conversation tables idempotent column migrations.

模仿 ``note_style_dao.ensure_note_style_columns``：用 SQLAlchemy inspector
检查列是否存在，缺失时通过 ``ALTER TABLE ... ADD COLUMN`` 补齐。

当前维护的列：
- ``conversations.research_space_id``：会话绑定的研究空间 id，nullable。
- ``conversation_messages.context_refs_authority_version``：服务端引用权威版本；
  历史行默认 0，不得因 legacy merge 自动升级为可信。
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.utils.logger import get_logger

logger = get_logger(__name__)


#: ``conversations`` 表需要补齐的列与对应 SQL（仅在缺失时执行）。
_CONVERSATIONS_COLUMN_MIGRATIONS: dict[str, str] = {
    "research_space_id": "ALTER TABLE conversations ADD COLUMN research_space_id TEXT",
}

_CONVERSATION_MESSAGES_COLUMN_MIGRATIONS: dict[str, str] = {
    "context_refs_authority_version": (
        "ALTER TABLE conversation_messages "
        "ADD COLUMN context_refs_authority_version INTEGER NOT NULL DEFAULT 0"
    ),
}


def ensure_conversation_columns(engine: Engine | None = None) -> None:
    """幂等确保 conversation tables 包含受管列。

    Args:
        engine: 可选的 Engine；缺省使用 ``app.db.engine.engine``。
    """
    if engine is None:
        from app.db.engine import engine as _engine
        engine = _engine

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    pending: list[tuple[str, str, str]] = []
    for table_name, migrations in (
        ("conversations", _CONVERSATIONS_COLUMN_MIGRATIONS),
        ("conversation_messages", _CONVERSATION_MESSAGES_COLUMN_MIGRATIONS),
    ):
        if table_name not in tables:
            continue
        existing = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        pending.extend(
            (table_name, column_name, sql)
            for column_name, sql in migrations.items()
            if column_name not in existing
        )

    if pending:
        with engine.begin() as conn:
            for table_name, column_name, sql in pending:
                logger.info("%s 表补齐列: %s", table_name, column_name)
                conn.execute(text(sql))


__all__ = ["ensure_conversation_columns"]
