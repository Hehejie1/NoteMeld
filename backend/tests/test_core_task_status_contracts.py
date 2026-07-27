import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import task_status_writer  # noqa: E402
from app.services import note_task_store  # noqa: E402


class TestCoreTaskStatusContracts(unittest.TestCase):
    def test_register_task_conversation_persists_and_increments_attempt(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_dir = task_status_writer.NOTE_OUTPUT_DIR
            task_status_writer.NOTE_OUTPUT_DIR = pathlib.Path(tmp_dir)
            try:
                task_status_writer.register_task_conversation(
                    task_id="task-1",
                    conversation_id="conv-1",
                    source_url="https://example.com/1",
                    extras="first",
                )
                first_payload = task_status_writer.get_registered_task_input("task-1")
                self.assertEqual(first_payload["conversation_id"], "conv-1")
                self.assertEqual(first_payload["attempt"], 1)
                self.assertEqual(first_payload["attempt_id"], "task-1:1")

                task_status_writer.register_task_conversation(
                    task_id="task-1",
                    conversation_id="conv-1",
                    source_url="https://example.com/2",
                    extras="second",
                )
                second_payload = task_status_writer.get_registered_task_input("task-1")
                self.assertEqual(second_payload["attempt"], 2)
                self.assertEqual(second_payload["attempt_id"], "task-1:2")
                self.assertEqual(second_payload["source_url"], "https://example.com/2")
                self.assertEqual(second_payload["extras"], "second")
            finally:
                task_status_writer.NOTE_OUTPUT_DIR = original_dir

    def test_get_registered_task_input_returns_empty_for_missing_task(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_dir = task_status_writer.NOTE_OUTPUT_DIR
            task_status_writer.NOTE_OUTPUT_DIR = pathlib.Path(tmp_dir)
            try:
                self.assertEqual(task_status_writer.get_registered_task_input("missing-task"), {})
            finally:
                task_status_writer.NOTE_OUTPUT_DIR = original_dir

    def test_cancel_note_task_persists_terminal_canceled_status(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_status_dir = task_status_writer.NOTE_OUTPUT_DIR
            original_store_dir = note_task_store.NOTE_OUTPUT_DIR
            task_status_writer.NOTE_OUTPUT_DIR = pathlib.Path(tmp_dir)
            note_task_store.NOTE_OUTPUT_DIR = pathlib.Path(tmp_dir)
            try:
                task_status_writer.register_task_conversation(
                    task_id="task-cancel-1",
                    conversation_id="conv-cancel-1",
                    source_url="https://example.com/video",
                )

                payload = note_task_store.cancel_note_task("task-cancel-1", "用户删除会话，任务已取消")

                self.assertEqual(payload["status"], "CANCELED")
                self.assertEqual(payload["message"], "用户删除会话，任务已取消")
                self.assertTrue(note_task_store.is_note_task_canceled("task-cancel-1"))
            finally:
                task_status_writer.NOTE_OUTPUT_DIR = original_status_dir
                note_task_store.NOTE_OUTPUT_DIR = original_store_dir


if __name__ == "__main__":
    unittest.main()
