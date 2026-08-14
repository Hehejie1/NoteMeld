"""P3 阶段二：conversation_store research_space_id 读写 + 迁移幂等。

覆盖：
- ensure_conversation_columns 幂等（无表 / 有表无列 → 补列；有列 → 跳过）
- upsert_conversation 写 research_space_id；get_conversation 读
- get_conversation_research_space_id 容错（不存在 / 列缺失 → None）
- 历史行 research_space_id NULL 兼容
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class EnsureConversationColumnsTest(unittest.TestCase):
    """ensure_conversation_columns 幂等迁移。"""

    def test_skip_when_table_missing(self):
        """表不存在时跳过（create_all 负责）。"""
        import sqlite3
        from sqlalchemy import create_engine
        from app.db.conversation_schema import ensure_conversation_columns

        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            # 不创建任何表
            ensure_conversation_columns(engine)
            conn = sqlite3.connect(str(db_path))
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            conn.close()
            self.assertEqual(tables, [])

    def test_adds_column_when_missing(self):
        """表存在但缺 research_space_id → 补列。"""
        import sqlite3
        from sqlalchemy import create_engine
        from app.db.conversation_schema import ensure_conversation_columns

        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            # 创建旧 schema（无 research_space_id）
            with engine.begin() as conn:
                conn.execute(__import__("sqlalchemy").text(
                    "CREATE TABLE conversations (id TEXT PRIMARY KEY, mode TEXT)"
                ))
            ensure_conversation_columns(engine)
            conn = sqlite3.connect(str(db_path))
            cols = [row[1] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()]
            conn.close()
            self.assertIn("research_space_id", cols)

    def test_idempotent_when_column_exists(self):
        """列已存在 → 不重复添加。"""
        import sqlite3
        from sqlalchemy import create_engine, text
        from app.db.conversation_schema import ensure_conversation_columns

        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE conversations (id TEXT PRIMARY KEY, research_space_id TEXT)"
                ))
            # 第二次调用不应报错
            ensure_conversation_columns(engine)
            ensure_conversation_columns(engine)
            conn = sqlite3.connect(str(db_path))
            cols = [row[1] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()]
            conn.close()
            self.assertEqual(cols.count("research_space_id"), 1)


class ConversationStoreResearchSpaceTest(unittest.TestCase):
    """conversation_store research_space_id 读写 + 容错。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = pathlib.Path(self._tmp.name) / "test.db"
        # patch engine 到临时 sqlite
        from sqlalchemy import create_engine
        self._engine = create_engine(f"sqlite:///{self._db_path}")
        # 创建表结构
        from app.db.engine import Base
        from app.db.models import conversation as _conv_models  # noqa: F401 - ensure models loaded
        Base.metadata.create_all(bind=self._engine)

        self._patches: list = []
        self._patches.append(patch("app.services.conversation_store.get_db", self._make_get_db))
        for p in self._patches:
            p.start()

    def _make_get_db(self):
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=self._engine)
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_upsert_and_read_research_space_id(self):
        """upsert_conversation 写 research_space_id，get_conversation 读出。"""
        from app.services.conversation_store import upsert_conversation, get_conversation

        upsert_conversation({
            "id": "conv-rs-1",
            "mode": "chat",
            "researchSpaceId": "rs-001",
        })
        payload = get_conversation("conv-rs-1")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["researchSpaceId"], "rs-001")

    def test_upsert_without_research_space_id_keeps_null(self):
        """不传 researchSpaceId 时保持 NULL。"""
        from app.services.conversation_store import upsert_conversation, get_conversation

        upsert_conversation({"id": "conv-rs-2", "mode": "chat"})
        payload = get_conversation("conv-rs-2")
        self.assertIsNotNone(payload)
        self.assertIsNone(payload["researchSpaceId"])

    def test_get_conversation_research_space_id_returns_value(self):
        """get_conversation_research_space_id 返回绑定的 rs_id。"""
        from app.services.conversation_store import (
            upsert_conversation,
            get_conversation_research_space_id,
        )

        upsert_conversation({"id": "conv-rs-3", "researchSpaceId": "rs-002"})
        self.assertEqual(get_conversation_research_space_id("conv-rs-3"), "rs-002")

    def test_get_conversation_research_space_id_none_for_missing(self):
        """会话不存在 → None。"""
        from app.services.conversation_store import get_conversation_research_space_id
        self.assertIsNone(get_conversation_research_space_id("no-such-conv"))

    def test_get_conversation_research_space_id_empty_cid(self):
        """空 cid → None。"""
        from app.services.conversation_store import get_conversation_research_space_id
        self.assertIsNone(get_conversation_research_space_id(""))
        self.assertIsNone(get_conversation_research_space_id(None))

    def test_update_research_space_id(self):
        """再次 upsert 更新 rs_id。"""
        from app.services.conversation_store import (
            upsert_conversation,
            get_conversation_research_space_id,
        )

        upsert_conversation({"id": "conv-rs-4", "researchSpaceId": "rs-a"})
        self.assertEqual(get_conversation_research_space_id("conv-rs-4"), "rs-a")
        upsert_conversation({"id": "conv-rs-4", "researchSpaceId": "rs-b"})
        self.assertEqual(get_conversation_research_space_id("conv-rs-4"), "rs-b")

    def test_clear_research_space_id_with_empty_string(self):
        """传空字符串清空 rs_id。"""
        from app.services.conversation_store import (
            upsert_conversation,
            get_conversation_research_space_id,
        )

        upsert_conversation({"id": "conv-rs-5", "researchSpaceId": "rs-x"})
        upsert_conversation({"id": "conv-rs-5", "researchSpaceId": ""})
        self.assertIsNone(get_conversation_research_space_id("conv-rs-5"))


if __name__ == "__main__":
    unittest.main()
