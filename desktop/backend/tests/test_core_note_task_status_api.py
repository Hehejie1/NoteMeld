import pathlib
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

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

# 这些 stub 只用于隔离 note router 的收集期依赖；导入完成后立即恢复模块表，
# 避免污染同一 pytest 进程中随后加载的真实 service 契约测试。
for _module_name, _stub in (
    ("app.services.note", note_service_stub),
    ("app.services.web_note", web_note_stub),
    ("app.services.task_serial_executor", task_serial_executor_stub),
):
    if sys.modules.get(_module_name) is _stub:
        sys.modules.pop(_module_name, None)


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

    def test_model_config_reset_keeps_historical_note_readable_via_conversation_api(self):
        from app.db.engine import Base
        from app.db import model_dao
        from app.db.model_schema import ensure_model_runtime_schema
        from app.routers import conversation as conversation_router
        from app.services import conversation_store, note_document_store
        from app.services.model import ModelService

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE models (
                    id INTEGER PRIMARY KEY,
                    provider_id TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                CREATE TABLE model_capabilities (
                    id INTEGER PRIMARY KEY,
                    provider_id TEXT NOT NULL,
                    model_name TEXT NOT NULL
                )
            """))
            conn.execute(text(
                "INSERT INTO models (id, provider_id, model_name) "
                "VALUES (1, 'provider-old', 'model-old')"
            ))
            conn.execute(text(
                "INSERT INTO model_capabilities (id, provider_id, model_name) "
                "VALUES (1, 'provider-old', 'model-old')"
            ))
        Base.metadata.create_all(bind=engine)
        testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        def session_factory():
            return testing_session()

        with patch("app.services.conversation_store._db", side_effect=session_factory), patch(
            "app.services.note_document_store._db", side_effect=session_factory
        ):
            conversation_store.upsert_conversation(
                {"id": "conv-old", "mode": "note", "title": "历史笔记"}
            )
            note_document_store.upsert_note_document(
                {
                    "task_id": "task-old",
                    "conversation_id": "conv-old",
                    "title": "历史笔记",
                    "content": "# 历史笔记\n\n必须保留",
                }
            )
            ensure_model_runtime_schema(engine)
            with engine.connect() as conn:
                self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM models")).scalar_one(), 0)

            app = FastAPI()
            app.include_router(conversation_router.router, prefix="/api")
            client = TestClient(app)
            with patch.object(
                conversation_router,
                "get_conversation",
                side_effect=conversation_store.get_conversation,
            ):
                response = client.get("/api/conversations/conv-old")

            with patch(
                "app.db.model_dao.get_db",
                side_effect=lambda: iter([session_factory()]),
            ):
                saved_model = model_dao.insert_model(
                    provider_id="provider-new",
                    model_name="model-new",
                    context_window_tokens=8192,
                    supports_vision=False,
                    supports_stream=True,
                )
                runtime_config = ModelService.build_saved_model_config(
                    {
                        "id": "provider-new",
                        "name": "Ollama",
                        "api_key": "",
                        "base_url": "http://127.0.0.1:11434/v1",
                    },
                    "model-new",
                )

            with tempfile.TemporaryDirectory() as tmp_dir:
                data_dir = pathlib.Path(tmp_dir)
                result_path = data_dir / "task-new-after-reset.json"
                result_path.write_text(
                    json.dumps(
                        {
                            "markdown": "# 重加模型后的新笔记\n\n正文",
                            "transcript": {"full_text": "字幕"},
                            "audio_meta": {"title": "新笔记", "platform": "youtube"},
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                with patch.object(task_status_writer, "NOTE_OUTPUT_DIR", data_dir):
                    conversation_store.upsert_conversation(
                        {
                            "id": "conv-new-after-reset",
                            "mode": "note",
                            "title": "新笔记",
                            "formData": {"model_name": runtime_config.model_name},
                        }
                    )
                    task_status_writer.register_task_conversation(
                        "task-new-after-reset",
                        "conv-new-after-reset",
                        source_url="https://example.com/new",
                    )
                    task_status_writer.emit_note_result(
                        "task-new-after-reset",
                        {
                            "message_id": "note-result-task-new-after-reset",
                            "content": "新笔记",
                            "title": "新笔记",
                            "source_url": "https://example.com/new",
                            "platform": "youtube",
                        },
                    )
                    persisted_task_result = json.loads(result_path.read_text(encoding="utf-8"))
                    new_conversation = conversation_store.get_conversation("conv-new-after-reset")

        self.assertEqual(response.status_code, 200)
        documents = response.json()["data"]["documents"]
        self.assertEqual(documents[0]["taskId"], "task-old")
        self.assertEqual(documents[0]["content"], "# 历史笔记\n\n必须保留")
        self.assertEqual(saved_model["context_window_tokens"], 8192)
        self.assertEqual(runtime_config.context_window_tokens, 8192)
        self.assertFalse(runtime_config.supports_vision)
        self.assertTrue(runtime_config.supports_stream)
        self.assertEqual(new_conversation["messages"][-1]["message_type"], "note_result")
        expected_markdown = "# 重加模型后的新笔记\n\n正文"
        self.assertEqual(persisted_task_result["markdown"], expected_markdown)
        self.assertEqual(new_conversation["markdown"], expected_markdown)
        self.assertEqual(new_conversation["documents"][0]["content"], expected_markdown)
        self.assertEqual(new_conversation["documents"][0]["modelName"], "model-new")

    def test_new_note_result_persists_file_conversation_message_and_note_document(self):
        from app.db.engine import Base
        from app.services import conversation_store, note_document_store

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        def session_factory():
            return testing_session()

        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = pathlib.Path(tmp_dir)
            result_path = data_dir / "task-new.json"
            result_path.write_text(
                json.dumps(
                    {
                        "markdown": "# 新笔记\n\n新模型生成正文",
                        "transcript": {"full_text": "字幕"},
                        "audio_meta": {"title": "新笔记", "platform": "youtube"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch.object(task_status_writer, "NOTE_OUTPUT_DIR", data_dir), patch(
                "app.services.conversation_store._db", side_effect=session_factory
            ), patch("app.services.note_document_store._db", side_effect=session_factory):
                conversation_store.upsert_conversation(
                    {
                        "id": "conv-new",
                        "mode": "note",
                        "title": "新笔记",
                        "formData": {"model_name": "model-new"},
                    }
                )
                task_status_writer.register_task_conversation(
                    "task-new",
                    "conv-new",
                    source_url="https://example.com/new",
                )
                task_status_writer.emit_note_result(
                    "task-new",
                    {
                        "message_id": "note-result-task-new",
                        "content": "新笔记",
                        "title": "新笔记",
                        "source_url": "https://example.com/new",
                        "platform": "youtube",
                    },
                )
                conversation = conversation_store.get_conversation("conv-new")

            saved_result = json.loads(result_path.read_text(encoding="utf-8"))

        self.assertEqual(saved_result["markdown"], "# 新笔记\n\n新模型生成正文")
        self.assertEqual(conversation["messages"][-1]["message_type"], "note_result")
        self.assertEqual(conversation["documents"][0]["content"], "# 新笔记\n\n新模型生成正文")
        self.assertEqual(conversation["documents"][0]["modelName"], "model-new")


if __name__ == "__main__":
    unittest.main()
