import pathlib
import sys
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

from app.routers import ingestion  # noqa: E402
from app.services.ingestion.artifact_reader import IngestionArtifactError  # noqa: E402


class _FakeReader:
    def __init__(self, report=None, chunks=None, error=None):
        self._report = report or {}
        self._chunks = chunks or []
        self._error = error

    def build_report(self, _task_id: str):
        if self._error:
            raise self._error
        return self._report

    def read_chunks(self, _task_id: str):
        if self._error:
            raise self._error
        return self._chunks


class TestCoreIngestionContracts(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(ingestion.router, prefix="/api")
        self.client = TestClient(app)

    def test_report_and_chunks_routes_return_reader_payload(self):
        fake_reader = _FakeReader(
            report={"task_id": "task-1", "parser": "document"},
            chunks=[{"id": "chunk-1", "text": "hello"}],
        )
        with patch("app.routers.ingestion._reader", return_value=fake_reader):
            report_response = self.client.get("/api/ingestion/task-1/report")
            chunks_response = self.client.get("/api/ingestion/task-1/chunks")

        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(report_response.json()["data"]["task_id"], "task-1")
        self.assertEqual(chunks_response.status_code, 200)
        self.assertEqual(chunks_response.json()["data"][0]["id"], "chunk-1")

    def test_missing_report_artifact_returns_http_404(self):
        fake_reader = _FakeReader(
            error=IngestionArtifactError("ingestion_artifact_missing", "missing parsed document")
        )
        with patch("app.routers.ingestion._reader", return_value=fake_reader):
            response = self.client.get("/api/ingestion/task-404/report")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "ingestion_artifact_missing")

    def test_job_route_returns_job_store_payload(self):
        fake_payload = {"job_id": "job-1", "status": "completed", "events": []}
        with patch("app.routers.ingestion.IngestionJobStore") as store_cls:
            store_cls.return_value.read.return_value = fake_payload
            response = self.client.get("/api/ingestion/job-1/job")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], fake_payload)

    def test_jobs_route_returns_durable_plugin_task_projection(self):
        fake_payload = [{"job_id": "job-1", "status": "running", "events": []}]
        with patch("app.routers.ingestion.IngestionJobStore") as store_cls:
            store_cls.return_value.list.return_value = fake_payload
            response = self.client.get("/api/ingestion/jobs?limit=10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], fake_payload)
        store_cls.return_value.list.assert_called_once_with(10)


if __name__ == "__main__":
    unittest.main()
