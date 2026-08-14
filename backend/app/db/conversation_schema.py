"""P3 阶段二：conversations 表幂等列迁移。

模仿 ``note_style_dao.ensure_note_style_columns``：用 SQLAlchemy inspector
检查列是否存在，缺失时通过 ``ALTER TABLE ... ADD COLUMN`` 补齐。

当前维护的列：
- ``research_space_id``：会话绑定的研究空间 id（cid→rs_id 映射），nullable。
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


def ensure_conversation_columns(engine: Engine | None = None) -> None:
    """幂等确保 ``conversations`` 表包含 P3 阶段二新增列。

    Args:
        engine: 可选的 Engine；缺省使用 ``app.db.engine.engine``。
    """
    if engine is None:
        from app.db.engine import engine as _engine
        engine = _engine

    inspector = inspect(engine)
    if "conversations" not in inspector.get_table_names():
        # create_all 会负责建表；这里跳过
        return

    existing = {column["name"] for column in inspector.get_columns("conversations")}
    pending = [(col, sql) for col, sql in _CONVERSATIONS_COLUMN_MIGRATIONS.items() if col not in existing]
    if not pending:
        return

    with engine.begin() as conn:
        for col, sql in pending:
            logger.info("conversations 表补齐列: %s", col)
            conn.execute(text(sql))


__all__ = ["ensure_conversation_columns"]
