import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

from app.routers import migration  # noqa: E402


class TestCoreMigrationApiContracts(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(migration.router, prefix="/api")
        self.client = TestClient(app)

    def test_export_route_starts_job(self):
        fake_payload = {"job_id": "job-export-1", "status": "completed"}
        with patch("app.routers.migration.MigrationExportService") as service_cls:
            service_cls.return_value.start_export.return_value = fake_payload
            response = self.client.post("/api/migration/export", json={"package_name": "backup-1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], fake_payload)

    def test_import_route_returns_import_payload(self):
        fake_payload = {"job_id": "job-import-1", "status": "completed"}
        with patch("app.routers.migration.MigrationImportService") as service_cls:
            service_cls.return_value.start_import.return_value = fake_payload
            response = self.client.post("/api/migration/import", json={"package_path": "/tmp/backup-1.zip"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], fake_payload)
        service_cls.return_value.start_import.assert_called_once_with(
            {"package_path": "/tmp/backup-1.zip", "rebuild_indexes": True},
            background_tasks=unittest.mock.ANY
        )

    def test_import_route_accepts_legacy_package_dir_alias(self):
        fake_payload = {"job_id": "job-import-1", "status": "completed"}
        with patch("app.routers.migration.MigrationImportService") as service_cls:
            service_cls.return_value.start_import.return_value = fake_payload
            response = self.client.post("/api/migration/import", json={"package_dir": "/tmp/backup-1.zip"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], fake_payload)
        service_cls.return_value.start_import.assert_called_once_with(
            {"package_path": "/tmp/backup-1.zip", "rebuild_indexes": True},
            background_tasks=unittest.mock.ANY
        )

    def test_upload_import_package_stores_browser_zip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.routers.migration.migration_upload_dir", return_value=pathlib.Path(temp_dir)):
                response = self.client.post(
                    "/api/migration/import/upload",
                    files={"file": ("backup-1.zip", b"zip-data", "application/zip")},
                )

            self.assertEqual(response.status_code, 200)
            package_path = pathlib.Path(response.json()["data"]["package_path"])
            self.assertTrue(package_path.name.endswith("-backup-1.zip"))
            self.assertEqual(package_path.read_bytes(), b"zip-data")

    def test_upload_import_package_uses_unique_server_filename_for_same_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.routers.migration.migration_upload_dir", return_value=pathlib.Path(temp_dir)):
                first = self.client.post(
                    "/api/migration/import/upload",
                    files={"file": ("backup-1.zip", b"first", "application/zip")},
                )
                second = self.client.post(
                    "/api/migration/import/upload",
                    files={"file": ("backup-1.zip", b"second", "application/zip")},
                )

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            first_path = pathlib.Path(first.json()["data"]["package_path"])
            second_path = pathlib.Path(second.json()["data"]["package_path"])
            self.assertNotEqual(first_path, second_path)
            self.assertEqual(first_path.read_bytes(), b"first")
            self.assertEqual(second_path.read_bytes(), b"second")

    def test_job_route_reads_job_store_payload(self):
        fake_payload = {"job_id": "job-1", "status": "running", "events": []}
        with patch("app.routers.migration.MigrationJobStore") as store_cls:
            store_cls.return_value.read.return_value = fake_payload
            response = self.client.get("/api/migration/job-1/job")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], fake_payload)

    def test_download_route_returns_completed_export_archive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = pathlib.Path(temp_dir) / "backup-1.zip"
            archive_path.write_bytes(b"zip-data")
            fake_payload = {
                "job_id": "job-export-1",
                "status": "completed",
                "summary": {"package_path": str(archive_path)},
            }
            with patch("app.routers.migration.MigrationJobStore") as store_cls:
                store_cls.return_value.read.return_value = fake_payload
                response = self.client.get("/api/migration/job-export-1/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"zip-data")
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertIn("backup-1.zip", response.headers["content-disposition"])

    def test_reindex_route_returns_service_payload(self):
        fake_payload = {"wiki_rebuilt": True, "vector_rebuilt": 1, "task_ids": ["task-1"]}
        with patch("app.routers.migration.MigrationReindexService") as service_cls:
            service_cls.return_value.rebuild.return_value = fake_payload
            response = self.client.post("/api/migration/reindex", json={"task_ids": ["task-1"]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], fake_payload)


if __name__ == "__main__":
    unittest.main()
