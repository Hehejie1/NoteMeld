import pathlib
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

gmssl_stub = types.ModuleType("gmssl")
gmssl_stub.sm3 = types.SimpleNamespace(sm3_hash=lambda data: "")
gmssl_stub.func = types.SimpleNamespace(bytes_to_list=lambda data: list(data))
sys.modules.setdefault("gmssl", gmssl_stub)
abogus_stub = types.ModuleType("app.downloaders.douyin_helper.abogus")
abogus_stub.ABogus = type("ABogus", (), {})
sys.modules.setdefault("app.downloaders.douyin_helper.abogus", abogus_stub)
youtube_transcript_stub = types.ModuleType("youtube_transcript_api")
youtube_transcript_stub.YouTubeTranscriptApi = type("YouTubeTranscriptApi", (), {})
sys.modules.setdefault("youtube_transcript_api", youtube_transcript_stub)
note_service_stub = types.ModuleType("app.services.note")
note_service_stub.NoteGenerator = type("NoteGenerator", (), {})
note_service_stub.logger = types.SimpleNamespace(
    warning=lambda *args, **kwargs: None,
    error=lambda *args, **kwargs: None,
    exception=lambda *args, **kwargs: None,
    info=lambda *args, **kwargs: None,
)
sys.modules.setdefault("app.services.note", note_service_stub)
web_note_stub = types.ModuleType("app.services.web_note")
web_note_stub.WebNoteGenerator = type("WebNoteGenerator", (), {})
sys.modules.setdefault("app.services.web_note", web_note_stub)
task_serial_executor_stub = types.ModuleType("app.services.task_serial_executor")
task_serial_executor_stub.task_serial_executor = types.SimpleNamespace(submit=lambda *args, **kwargs: None)
sys.modules.setdefault("app.services.task_serial_executor", task_serial_executor_stub)

from app.routers import note  # noqa: E402
from app.services import note_task_store, task_status_writer  # noqa: E402


class TestCoreNoteTaskStatusApi(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(note.router, prefix="/api")
        self.client = TestClient(app)

    def test_task_status_returns_canceled_for_canceled_task(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = pathlib.Path(tmp_dir)
            with patch.object(note, "NOTE_OUTPUT_DIR", str(data_dir)), patch.object(
                note_task_store, "NOTE_OUTPUT_DIR", data_dir
            ), patch.object(task_status_writer, "NOTE_OUTPUT_DIR", data_dir):
                note_task_store.cancel_note_task("task-canceled-1", "用户删除会话，任务已取消")

                response = self.client.get("/api/task_status/task-canceled-1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["status"], "CANCELED")
        self.assertEqual(payload["message"], "用户删除会话，任务已取消")

    def test_task_status_returns_not_found_when_task_has_no_artifacts_or_registration(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = pathlib.Path(tmp_dir)
            with patch.object(note, "NOTE_OUTPUT_DIR", str(data_dir)), patch.object(
                note_task_store, "NOTE_OUTPUT_DIR", data_dir
            ), patch.object(task_status_writer, "NOTE_OUTPUT_DIR", data_dir):
                response = self.client.get("/api/task_status/missing-task")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["status"], "NOT_FOUND")
        self.assertEqual(payload["message"], "任务不存在或已被删除")

    def test_task_status_returns_collector_timings_from_status_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = pathlib.Path(tmp_dir)
            (data_dir / "task-collector-1.status.json").write_text(
                json.dumps(
                    {
                        "status": "TRANSCRIBING",
                        "message": "正在转写",
                        "stage_timings": {
                            "PARSING": {"status": "done", "duration_ms": 11},
                            "DOWNLOADING": {"status": "done", "duration_ms": 22},
                            "TRANSCRIBING": {"status": "running", "elapsed_ms": 33},
                            "SUMMARIZING": {"status": "running", "elapsed_ms": 44},
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(note, "NOTE_OUTPUT_DIR", str(data_dir)):
                response = self.client.get("/api/task_status/task-collector-1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(
            payload["collector_timings"],
            {
                "PARSING": {"status": "done", "duration_ms": 11},
                "DOWNLOADING": {"status": "done", "duration_ms": 22},
                "TRANSCRIBING": {"status": "running", "elapsed_ms": 33},
            },
        )


if __name__ == "__main__":
    unittest.main()
