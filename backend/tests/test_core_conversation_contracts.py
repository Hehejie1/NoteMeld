import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.engine import merge_legacy_sqlite_data  # noqa: E402
from app.db.models.conversation import Base  # noqa: E402
from app.routers import conversation  # noqa: E402
from app.services import conversation_store, note_document_store  # noqa: E402


class TestCoreConversationContracts(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(conversation.router, prefix="/api")
        self.client = TestClient(app)

    def test_post_message_returns_conversation_not_found_payload(self):
        with patch("app.routers.conversation.append_message", side_effect=ValueError("conversation not found")):
            response = self.client.post(
                "/api/conversations/missing/messages",
                json={
                    "id": "msg-1",
                    "role": "user",
                    "content": "hello",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 404)
        self.assertEqual(response.json()["msg"], "会话不存在")

    def test_patch_message_returns_message_not_found_payload(self):
        with patch("app.routers.conversation.update_message", side_effect=ValueError("message not found")):
            response = self.client.patch(
                "/api/conversations/conv-1/messages/msg-1",
                json={"content": "updated"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 404)
        self.assertEqual(response.json()["msg"], "消息不存在")

    def test_delete_conversation_cancels_linked_note_tasks(self):
        with patch("app.routers.conversation.get_conversation", return_value={"id": "conv-1"}), patch(
            "app.routers.conversation.get_conversation_note_task_ids",
            return_value=["task-1", "task-2"],
        ), patch("app.routers.conversation.soft_delete_conversation", return_value=True), patch(
            "app.routers.conversation.delete_note_task_artifacts"
        ) as delete_artifacts, patch("app.routers.conversation.cancel_note_task") as cancel_note_task:
            response = self.client.delete("/api/conversations/conv-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 0)
        self.assertEqual(cancel_note_task.call_count, 2)
        cancel_note_task.assert_any_call("task-1", "会话已删除，任务已取消")
        cancel_note_task.assert_any_call("task-2", "会话已删除，任务已取消")
        self.assertEqual(delete_artifacts.call_count, 2)

    def test_cancel_task_rejects_card_from_another_conversation(self):
        manager = type("Manager", (), {})()
        manager.get_card = lambda _card_id: {"conversation_id": "conv-owner"}
        manager.cancel_task = AsyncMock(return_value=True)

        with patch(
            "app.routers.conversation.find_manager_by_card", return_value=manager
        ):
            response = self.client.post(
                "/api/conversations/conv-other/workspace/cancel_task",
                json={"card_id": "card-private"},
            )

        self.assertEqual(response.json()["code"], 404)
        manager.cancel_task.assert_not_awaited()

    def test_cancel_task_accepts_card_owned_by_path_conversation(self):
        manager = type("Manager", (), {})()
        manager.get_card = lambda _card_id: {"conversation_id": "conv-owner"}
        manager.cancel_task = AsyncMock(return_value=True)

        with patch(
            "app.routers.conversation.find_manager_by_card", return_value=manager
        ):
            response = self.client.post(
                "/api/conversations/conv-owner/workspace/cancel_task",
                json={"card_id": "card-owned"},
            )

        self.assertEqual(response.json()["code"], 0)
        manager.cancel_task.assert_awaited_once_with("card-owned")

    def test_legacy_sqlite_migration_includes_conversation_tables(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            current_path = pathlib.Path(tmp_dir) / "current.db"
            legacy_path = pathlib.Path(tmp_dir) / "legacy.db"
            self._prepare_conversation_tables(current_path)
            self._prepare_conversation_tables(legacy_path)

            legacy_conn = sqlite3.connect(legacy_path)
            legacy_conn.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "conv-1",
                    "chat",
                    "title",
                    "SUCCESS",
                    "message",
                    "chat",
                    "",
                    "none",
                    "{}",
                    "{}",
                    "{}",
                    "\"\"",
                    "2026-06-01T00:00:00+00:00",
                    "2026-06-01T00:00:00+00:00",
                    None,
                ),
            )
            legacy_conn.execute(
                "INSERT INTO conversation_messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "msg-1",
                    "conv-1",
                    "user",
                    "user_input",
                    "hello",
                    None,
                    "{}",
                    "[]",
                    0,
                    "2026-06-01T00:00:00+00:00",
                    "2026-06-01T00:00:00+00:00",
                ),
            )
            legacy_conn.execute(
                "INSERT INTO note_documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "task-1",
                    "conv-1",
                    "Doc",
                    "# Doc",
                    "https://example.com",
                    "web",
                    "gpt-4",
                    "default",
                    "SUCCESS",
                    "pending",
                    "2026-06-01T00:00:00+00:00",
                    "2026-06-01T00:00:00+00:00",
                    None,
                ),
            )
            legacy_conn.commit()
            legacy_conn.close()

            migrated = merge_legacy_sqlite_data(current_path, legacy_path)

            self.assertEqual(migrated["conversations"], 1)
            self.assertEqual(migrated["conversation_messages"], 1)
            self.assertEqual(migrated["note_documents"], 1)

            current_conn = sqlite3.connect(current_path)
            self.assertEqual(current_conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0], 1)
            self.assertEqual(current_conn.execute("SELECT COUNT(*) FROM conversation_messages").fetchone()[0], 1)
            self.assertEqual(current_conn.execute("SELECT COUNT(*) FROM note_documents").fetchone()[0], 1)
            current_conn.close()

    def test_bootstrap_conversations_restores_note_conversation_from_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = pathlib.Path(tmp_dir)
            task_id = "task-restore-1"
            conversation_id = "conv-restore-1"
            task_conversations_dir = data_dir / "task_conversations"
            task_conversations_dir.mkdir(parents=True, exist_ok=True)
            (task_conversations_dir / f"{task_id}.json").write_text(
                """
                {
                  "task_id": "task-restore-1",
                  "conversation_id": "conv-restore-1",
                  "source_url": "https://example.com/article",
                  "extras": "focus",
                  "attempt": 1,
                  "attempt_id": "task-restore-1:1"
                }
                """.strip(),
                encoding="utf-8",
            )
            (data_dir / f"{task_id}.json").write_text(
                """
                {
                  "markdown": "# Restored Title\\n\\nBody",
                  "transcript": {"full_text": "Body"},
                  "audio_meta": {"title": "Restored Title", "platform": "web"}
                }
                """.strip(),
                encoding="utf-8",
            )
            (data_dir / f"{task_id}.status.json").write_text(
                """
                {
                  "status": "SUCCESS",
                  "message": "done",
                  "source_url": "https://example.com/article",
                  "extras": "focus"
                }
                """.strip(),
                encoding="utf-8",
            )

            engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
            Base.metadata.create_all(bind=engine)
            TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

            def session_factory():
                return TestingSessionLocal()

            with patch("app.services.conversation_store._db", side_effect=session_factory), patch(
                "app.services.note_document_store._db", side_effect=session_factory
            ), patch("app.services.conversation_store.note_output_dir", return_value=data_dir, create=True):
                restored = conversation_store.bootstrap_conversations_from_storage()
                payload = conversation_store.get_conversation(conversation_id)

            self.assertEqual(restored["conversations"], 1)
            self.assertEqual(restored["messages"], 1)
            self.assertIsNotNone(payload)
            self.assertEqual(payload["id"], conversation_id)
            self.assertEqual(payload["mode"], "note")
            self.assertEqual(payload["linkedNoteTaskId"], task_id)
            self.assertEqual(payload["title"], "Restored Title")
            self.assertEqual(payload["markdown"], "# Restored Title\n\nBody")
            self.assertEqual(len(payload["messages"]), 1)
            self.assertEqual(payload["messages"][0]["message_type"], "note_result")
            self.assertEqual(len(payload["documents"]), 1)
            self.assertEqual(payload["documents"][0]["taskId"], task_id)

    def _prepare_conversation_tables(self, db_path: pathlib.Path) -> None:
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
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
                created_at TEXT,
                updated_at TEXT,
                deleted_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE conversation_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                role TEXT,
                message_type TEXT,
                content TEXT,
                status TEXT,
                meta_json TEXT,
                sources_json TEXT,
                error INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
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
                created_at TEXT,
                updated_at TEXT,
                deleted_at TEXT
            )
            """
        )
        conn.commit()
        conn.close()


if __name__ == "__main__":
    unittest.main()
