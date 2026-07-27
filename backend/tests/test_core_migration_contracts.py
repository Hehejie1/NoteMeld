import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.migration.export_service import MigrationExportService  # noqa: E402
from app.services.migration.import_service import MigrationImportService  # noqa: E402
from app.services.migration.job_store import MigrationJobStore  # noqa: E402
from app.services.migration.merge_service import MigrationMergeService  # noqa: E402
from app.services.migration.manifest_service import (  # noqa: E402
    MigrationManifestError,
    MigrationManifestService,
)
from app.services.migration.reindex_service import MigrationReindexService  # noqa: E402
from app.utils import storage_paths  # noqa: E402


class TestCoreMigrationContracts(unittest.TestCase):
    def test_storage_paths_follow_notemeld_data_dir_for_migration_assets(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_root = pathlib.Path(tmp_dir).resolve()
            with patch.dict(os.environ, {"NOTEMELD_DATA_DIR": str(data_root)}, clear=True):
                self.assertEqual(storage_paths.migration_root_dir(), data_root / "migrations")
                self.assertEqual(storage_paths.migration_jobs_dir(), data_root / "migrations" / "jobs")
                self.assertEqual(storage_paths.migration_packages_dir(), data_root / "migrations" / "packages")

    def test_manifest_service_round_trip_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            package_dir = pathlib.Path(tmp_dir) / "export-001"
            service = MigrationManifestService()
            manifest = service.build_manifest(
                package_id="export-001",
                operation="export",
                app_version="0.1.0",
                counts={"conversations": 3, "notes": 4},
                includes={
                    "database": True,
                    "note_results": True,
                    "uploads": True,
                    "wiki": True,
                    "vector_index": False,
                },
                warnings=["vector index excluded"],
            )

            manifest_path = service.write_manifest(package_dir, manifest)
            loaded_manifest = service.read_manifest(package_dir)
            validated_manifest = service.validate_manifest(loaded_manifest)

            self.assertEqual(manifest_path, package_dir / "manifest.json")
            self.assertEqual(validated_manifest["schema_version"], "migration_manifest.v1")
            self.assertEqual(validated_manifest["package_id"], "export-001")
            self.assertEqual(validated_manifest["counts"]["notes"], 4)
            self.assertFalse(validated_manifest["includes"]["vector_index"])
            self.assertEqual(validated_manifest["warnings"], ["vector index excluded"])

    def test_manifest_service_rejects_invalid_schema(self):
        service = MigrationManifestService()

        with self.assertRaises(MigrationManifestError) as ctx:
            service.validate_manifest({"schema_version": "migration_manifest.v0", "package_id": "pkg-1"})

        self.assertEqual(ctx.exception.code, "migration_manifest_unsupported_schema")

    def test_job_store_defaults_and_transitions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MigrationJobStore(pathlib.Path(tmp_dir))

            pending = store.read("job-1")
            self.assertEqual(pending["schema_version"], "migration_job.v1")
            self.assertEqual(pending["status"], "pending")
            self.assertEqual(pending["progress"], 0)
            self.assertEqual(pending["events"], [])

            running = store.write_progress("job-1", stage="exporting_db", progress=35, message="导出数据库")
            self.assertEqual(running["status"], "running")
            self.assertEqual(running["stage"], "exporting_db")
            self.assertEqual(running["progress"], 35)
            self.assertEqual(running["events"][0]["message"], "导出数据库")

            completed = store.mark_completed(
                "job-1",
                summary={"exported": {"conversations": 3}},
                warnings=["vector index skipped"],
            )
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["progress"], 100)
            self.assertEqual(completed["summary"]["exported"]["conversations"], 3)
            self.assertEqual(completed["warnings"], ["vector index skipped"])
            self.assertTrue(completed["completed_at"])

    def test_job_store_clears_previous_error_when_marked_completed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MigrationJobStore(pathlib.Path(tmp_dir))
            store.mark_failed("job-retry", error="previous failure", recoverable=True)

            completed = store.mark_completed("job-retry", summary={"ok": True})

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["error"], "")
            self.assertFalse(completed["recoverable"])

    def test_job_store_can_persist_failure_payload(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = MigrationJobStore(pathlib.Path(tmp_dir))

            failed = store.mark_failed("job-fail", error="manifest mismatch", recoverable=False)

            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["error"], "manifest mismatch")
            self.assertFalse(failed["recoverable"])
            self.assertTrue(failed["completed_at"])

    def test_job_store_rejects_path_traversal_job_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            store = MigrationJobStore(root / "jobs")

            with self.assertRaises(ValueError):
                store.write_progress("../evil", stage="prepare", progress=1, message="bad")

            self.assertFalse((root / "evil_migration_job.json").exists())

    def test_export_service_rejects_path_traversal_package_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            current_db = root / "notemeld.db"
            note_output_dir = root / "note_results"
            packages_dir = root / "packages"
            victim_dir = root / "victim"
            self._prepare_conversation_tables(current_db)
            note_output_dir.mkdir(parents=True, exist_ok=True)
            victim_dir.mkdir(parents=True, exist_ok=True)
            (victim_dir / "keep.txt").write_text("keep", encoding="utf-8")

            service = MigrationExportService(
                current_db_path=current_db,
                note_output_root=note_output_dir,
                packages_dir=packages_dir,
                job_store=MigrationJobStore(root / "jobs"),
            )

            with self.assertRaises(ValueError):
                service.start_export({"job_id": "job-export-1", "package_name": "../victim"})

            self.assertTrue((victim_dir / "keep.txt").exists())

    def test_export_service_writes_structured_package(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            current_db = root / "notemeld.db"
            note_output_dir = root / "note_results"
            uploads_dir = root / "uploads"
            static_dir = root / "static"
            packages_dir = root / "packages"
            self._prepare_conversation_tables(current_db)
            self._insert_conversation(current_db, title="本地版本")

            (note_output_dir / "task_conversations").mkdir(parents=True, exist_ok=True)
            (note_output_dir / "wiki" / "contributions").mkdir(parents=True, exist_ok=True)
            uploads_dir.mkdir(parents=True, exist_ok=True)
            (static_dir / "screenshots").mkdir(parents=True, exist_ok=True)
            (note_output_dir / "task-1.json").write_text('{"markdown":"# Title"}', encoding="utf-8")
            (note_output_dir / "task_conversations" / "task-1.json").write_text(
                '{"task_id":"task-1","conversation_id":"conv-1"}',
                encoding="utf-8",
            )
            (note_output_dir / "wiki" / "contributions" / "task-1.json").write_text(
                '{"source_id":"task-1","title":"Title","source_type":"note","summary":"","topics":[],"claims":[],"evidence":[],"relations":[],"entities":[],"concepts":[]}',
                encoding="utf-8",
            )
            (uploads_dir / "demo.txt").write_text("upload", encoding="utf-8")
            (static_dir / "screenshots" / "shot-1.jpg").write_bytes(b"fake-image")

            with patch.dict(os.environ, {"STATIC_DIR": str(static_dir)}):
                service = MigrationExportService(
                    current_db_path=current_db,
                    note_output_root=note_output_dir,
                    uploads_root=uploads_dir,
                    packages_dir=packages_dir,
                    job_store=MigrationJobStore(root / "jobs"),
                )

                result = service.start_export({"job_id": "job-export-1", "package_name": "backup-1"})
            archive_path = packages_dir / "backup-1.zip"

            self.assertEqual(result["status"], "completed")
            self.assertTrue(archive_path.exists())
            self.assertFalse((packages_dir / "backup-1").exists())
            self.assertEqual(result["summary"]["package_path"], str(archive_path.resolve()))
            self.assertEqual(result["summary"]["counts"]["conversations"], 1)

            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())
                manifest = MigrationManifestService().validate_manifest(
                    self._load_json_bytes(archive.read("manifest.json"))
                )

            self.assertIn("database/notemeld.db", names)
            self.assertIn("note_results/task-1.json", names)
            self.assertIn("note_results/task_conversations/task-1.json", names)
            self.assertIn("uploads/demo.txt", names)
            self.assertIn("static/screenshots/shot-1.jpg", names)
            self.assertIn("wiki/contributions/task-1.json", names)
            self.assertEqual(manifest["counts"]["conversations"], 1)
            self.assertEqual(manifest["counts"]["static_files"], 1)
            self.assertTrue(manifest["includes"]["static"])
            self.assertFalse(manifest["includes"]["vector_index"])

    def test_merge_service_overwrites_same_id_rows(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            current_db = root / "current.db"
            import_db = root / "import.db"
            self._prepare_conversation_tables(current_db)
            self._prepare_conversation_tables(import_db)
            self._insert_conversation(current_db, title="本地版本")
            self._insert_conversation(import_db, title="导入版本")

            summary = MigrationMergeService(current_db_path=current_db).merge_database(import_db)

            conn = sqlite3.connect(current_db)
            title = conn.execute("SELECT title FROM conversations WHERE id = ?", ("conv-1",)).fetchone()[0]
            conn.close()

            self.assertEqual(summary["conversations"]["overwritten"], 1)
            self.assertEqual(title, "导入版本")

    def test_import_service_merges_zip_package_and_runs_reindex(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            current_db = root / "current.db"
            note_output_dir = root / "note_results"
            uploads_dir = root / "uploads"
            static_dir = root / "static"
            package_dir = root / "packages" / "backup-1"
            archive_path = root / "packages" / "backup-1.zip"
            package_db = package_dir / "database" / "notemeld.db"
            self._prepare_conversation_tables(current_db)
            self._prepare_conversation_tables(package_db)
            self._insert_conversation(current_db, title="本地版本")
            self._insert_conversation(package_db, title="导入版本")

            (package_dir / "note_results").mkdir(parents=True, exist_ok=True)
            (package_dir / "uploads").mkdir(parents=True, exist_ok=True)
            (package_dir / "static" / "screenshots").mkdir(parents=True, exist_ok=True)
            (package_dir / "wiki").mkdir(parents=True, exist_ok=True)
            (package_dir / "note_results" / "task-1.json").write_text('{"markdown":"# Imported"}', encoding="utf-8")
            (package_dir / "static" / "screenshots" / "shot-1.jpg").write_bytes(b"fake-image")
            manifest = MigrationManifestService().build_manifest(
                package_id="backup-1",
                operation="export",
                app_version="0.1.0",
                counts={"conversations": 1, "static_files": 1},
                includes={
                    "database": True,
                    "note_results": True,
                    "uploads": True,
                    "static": True,
                    "wiki": True,
                    "vector_index": False,
                },
            )
            MigrationManifestService().write_manifest(package_dir, manifest)
            self._build_zip_archive(package_dir, archive_path)

            class _FakeReindexService:
                def __init__(self):
                    self.calls = []

                def rebuild(self, task_ids=None):
                    self.calls.append(task_ids or [])
                    return {"wiki_rebuilt": True, "vector_rebuilt": len(task_ids or []), "task_ids": task_ids or []}

            fake_reindex = _FakeReindexService()
            service = MigrationImportService(
                current_db_path=current_db,
                note_output_root=note_output_dir,
                uploads_root=uploads_dir,
                static_root=static_dir,
                reindex_service=fake_reindex,
                job_store=MigrationJobStore(root / "jobs"),
            )

            result = service.start_import({"job_id": "job-import-1", "package_path": str(archive_path)})

            conn = sqlite3.connect(current_db)
            title = conn.execute("SELECT title FROM conversations WHERE id = ?", ("conv-1",)).fetchone()[0]
            conn.close()

            self.assertEqual(result["status"], "completed")
            self.assertEqual(title, "导入版本")
            self.assertTrue((note_output_dir / "task-1.json").exists())
            self.assertTrue((static_dir / "screenshots" / "shot-1.jpg").exists())
            self.assertEqual(result["summary"]["merged"]["conversations"]["overwritten"], 1)
            self.assertEqual(result["summary"]["reindex"]["wiki_rebuilt"], True)
            self.assertEqual(fake_reindex.calls, [["task-1"]])

    def test_import_service_rejects_archive_when_disk_space_is_insufficient(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            current_db = root / "current.db"
            note_output_dir = root / "note_results"
            uploads_dir = root / "uploads"
            package_dir = root / "packages" / "backup-large"
            archive_path = root / "packages" / "backup-large.zip"
            package_db = package_dir / "database" / "notemeld.db"
            self._prepare_conversation_tables(current_db)
            self._prepare_conversation_tables(package_db)
            (package_dir / "note_results").mkdir(parents=True, exist_ok=True)
            (package_dir / "note_results" / "task-1.json").write_text('{"markdown":"# Imported"}', encoding="utf-8")
            (package_dir / "static" / "screenshots").mkdir(parents=True, exist_ok=True)
            (package_dir / "static" / "screenshots" / "large.jpg").write_bytes(b"x" * 128)
            manifest = MigrationManifestService().build_manifest(
                package_id="backup-large",
                operation="export",
                app_version="0.1.0",
                counts={"conversations": 0},
                includes={
                    "database": True,
                    "note_results": True,
                    "uploads": False,
                    "static": True,
                    "wiki": False,
                    "vector_index": False,
                },
            )
            MigrationManifestService().write_manifest(package_dir, manifest)
            self._build_zip_archive(package_dir, archive_path)

            service = MigrationImportService(
                current_db_path=current_db,
                note_output_root=note_output_dir,
                uploads_root=uploads_dir,
                reindex_service=unittest.mock.Mock(rebuild=unittest.mock.Mock(return_value={})),
                job_store=MigrationJobStore(root / "jobs"),
            )

            disk_usage = unittest.mock.Mock(free=64)
            with patch("app.services.migration.import_service.shutil.disk_usage", return_value=disk_usage):
                with self.assertRaises(MigrationManifestError) as ctx:
                    service.start_import({"job_id": "job-import-large", "package_path": str(archive_path)})

            self.assertEqual(ctx.exception.code, "migration_import_insufficient_storage")
            self.assertIn("存储空间不足", ctx.exception.message)

    def test_import_service_reports_memory_error_with_actionable_message(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            archive_path = root / "backup-memory.zip"
            with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", "{}")

            store = MigrationJobStore(root / "jobs")
            service = MigrationImportService(
                current_db_path=root / "current.db",
                note_output_root=root / "note_results",
                uploads_root=root / "uploads",
                job_store=store,
            )

            with patch.object(service, "_ensure_archive_fits_available_storage"):
                with patch.object(service, "_extract_archive", side_effect=MemoryError()):
                    with self.assertRaises(MemoryError):
                        service.start_import({"job_id": "job-import-memory", "package_path": str(archive_path)})

            job = store.read("job-import-memory")
            self.assertEqual(job["status"], "failed")
            self.assertIn("内存不足", job["error"])
            self.assertIn("清除缓存", job["error"])

    def test_merge_service_updates_existing_primary_key_without_replacing_row(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            current_db = root / "current.db"
            import_db = root / "import.db"
            self._prepare_simple_items_table(current_db)
            self._prepare_simple_items_table(import_db)
            current_conn = sqlite3.connect(current_db)
            current_conn.execute("INSERT INTO items (id, title) VALUES (?, ?)", ("item-1", "旧标题"))
            original_rowid = current_conn.execute("SELECT rowid FROM items WHERE id = ?", ("item-1",)).fetchone()[0]
            current_conn.commit()
            current_conn.close()

            import_conn = sqlite3.connect(import_db)
            import_conn.execute("INSERT INTO items (id, title) VALUES (?, ?)", ("item-1", "新标题"))
            import_conn.commit()
            import_conn.close()

            summary = MigrationMergeService(current_db_path=current_db).merge_database(import_db)

            current_conn = sqlite3.connect(current_db)
            rowid, title = current_conn.execute("SELECT rowid, title FROM items WHERE id = ?", ("item-1",)).fetchone()
            current_conn.close()

            self.assertEqual(summary["items"]["overwritten"], 1)
            self.assertEqual(title, "新标题")
            self.assertEqual(rowid, original_rowid)

    def test_import_service_reindex_ignores_note_auxiliary_json_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            current_db = root / "current.db"
            note_output_dir = root / "note_results"
            uploads_dir = root / "uploads"
            package_dir = root / "packages" / "backup-aux"
            archive_path = root / "packages" / "backup-aux.zip"
            package_db = package_dir / "database" / "notemeld.db"
            self._prepare_conversation_tables(current_db)
            self._prepare_conversation_tables(package_db)
            self._insert_conversation(current_db, title="本地版本")
            self._insert_conversation(package_db, title="导入版本")

            (package_dir / "note_results").mkdir(parents=True, exist_ok=True)
            (package_dir / "uploads").mkdir(parents=True, exist_ok=True)
            (package_dir / "wiki").mkdir(parents=True, exist_ok=True)
            (package_dir / "note_results" / "task-1.json").write_text('{"markdown":"# Imported"}', encoding="utf-8")
            (package_dir / "note_results" / "task-1_evidence_anchors.json").write_text("[]", encoding="utf-8")
            (package_dir / "note_results" / "task-1_knowledge_chunks.json").write_text("[]", encoding="utf-8")
            (package_dir / "note_results" / "task-1_markdown_assets.json").write_text("[]", encoding="utf-8")
            manifest = MigrationManifestService().build_manifest(
                package_id="backup-aux",
                operation="export",
                app_version="0.1.0",
                counts={"conversations": 1},
                includes={
                    "database": True,
                    "note_results": True,
                    "uploads": True,
                    "wiki": True,
                    "vector_index": False,
                },
            )
            MigrationManifestService().write_manifest(package_dir, manifest)
            self._build_zip_archive(package_dir, archive_path)

            class _FakeReindexService:
                def __init__(self):
                    self.calls = []

                def rebuild(self, task_ids=None):
                    self.calls.append(task_ids or [])
                    return {"wiki_rebuilt": True, "vector_rebuilt": len(task_ids or []), "task_ids": task_ids or []}

            fake_reindex = _FakeReindexService()
            service = MigrationImportService(
                current_db_path=current_db,
                note_output_root=note_output_dir,
                uploads_root=uploads_dir,
                reindex_service=fake_reindex,
                job_store=MigrationJobStore(root / "jobs"),
            )

            result = service.start_import({"job_id": "job-import-aux", "package_path": str(archive_path)})

            self.assertEqual(result["status"], "completed")
            self.assertEqual(fake_reindex.calls, [["task-1"]])

    def test_import_service_rejects_directory_input(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            package_dir = root / "packages" / "backup-1"
            package_dir.mkdir(parents=True, exist_ok=True)
            service = MigrationImportService(job_store=MigrationJobStore(root / "jobs"))

            with self.assertRaises(MigrationManifestError) as ctx:
                service.start_import({"job_id": "job-import-dir", "package_path": str(package_dir)})

            self.assertEqual(ctx.exception.code, "migration_import_requires_zip")

    def test_reindex_service_rebuilds_wiki_and_vector_entries(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = pathlib.Path(tmp_dir)
            current_db = root / "current.db"
            note_output_dir = root / "note_results"
            self._prepare_conversation_tables(current_db)
            self._insert_conversation(current_db, title="导入版本")
            note_output_dir.mkdir(parents=True, exist_ok=True)
            (note_output_dir / "task-1.json").write_text('{"markdown":"# Imported"}', encoding="utf-8")

            fake_vector_store = unittest.mock.Mock()
            with patch("app.services.migration.reindex_service.WikiStore") as wiki_store_cls:
                service = MigrationReindexService(
                    current_db_path=current_db,
                    note_output_root=note_output_dir,
                    vector_store_manager=fake_vector_store,
                )
                result = service.rebuild()

            wiki_store_cls.return_value.rebuild_from_contributions.assert_called_once()
            fake_vector_store.index_task.assert_called_once_with("task-1")
            self.assertTrue(result["wiki_rebuilt"])
            self.assertEqual(result["vector_rebuilt"], 1)

    def _prepare_conversation_tables(self, db_path: pathlib.Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
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

    def _insert_conversation(self, db_path: pathlib.Path, title: str) -> None:
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "conv-1",
                "note",
                title,
                "SUCCESS",
                "",
                "web",
                "task-1",
                "ready",
                "{}",
                "{}",
                "{}",
                "\"# Title\"",
                "2026-06-02T00:00:00+00:00",
                "2026-06-02T00:00:00+00:00",
                None,
            ),
        )
        conn.execute(
            "INSERT INTO note_documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "task-1",
                "conv-1",
                title,
                "# Imported",
                "https://example.com",
                "web",
                "gpt-4",
                "default",
                "SUCCESS",
                "pending",
                "2026-06-02T00:00:00+00:00",
                "2026-06-02T00:00:00+00:00",
                None,
            ),
        )
        conn.commit()
        conn.close()

    def _prepare_simple_items_table(self, db_path: pathlib.Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE items (
                id TEXT PRIMARY KEY,
                title TEXT
            )
            """
        )
        conn.commit()
        conn.close()

    def _load_json_bytes(self, payload: bytes) -> dict:
        import json

        return json.loads(payload.decode("utf-8"))

    def _build_zip_archive(self, source_dir: pathlib.Path, archive_path: pathlib.Path) -> None:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=path.relative_to(source_dir).as_posix())


if __name__ == "__main__":
    unittest.main()
