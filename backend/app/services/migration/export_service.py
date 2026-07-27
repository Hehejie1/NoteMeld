from __future__ import annotations

import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.services.migration.job_store import MigrationJobStore
from app.services.migration.manifest_service import MigrationManifestService
from app.services.migration.validation import ensure_child_path, validate_path_component
from app.utils.storage_paths import database_path, migration_packages_dir, note_output_dir, static_dir, upload_dir


class MigrationExportService:
    def __init__(
        self,
        current_db_path: str | Path | None = None,
        note_output_root: str | Path | None = None,
        uploads_root: str | Path | None = None,
        static_root: str | Path | None = None,
        packages_dir: str | Path | None = None,
        manifest_service: MigrationManifestService | None = None,
        job_store: MigrationJobStore | None = None,
    ):
        self.current_db_path = Path(current_db_path or database_path())
        self.note_output_root = Path(note_output_root or note_output_dir())
        self.uploads_root = Path(uploads_root or upload_dir())
        self.static_root = Path(static_root or static_dir())
        self.packages_dir = Path(packages_dir or migration_packages_dir())
        self.manifests = manifest_service or MigrationManifestService()
        self.jobs = job_store or MigrationJobStore()

    def start_export(self, payload: dict, background_tasks=None) -> dict:
        target_path_str = str(payload.get("target_path") or "").strip()
        if target_path_str:
            archive_path = Path(target_path_str).resolve()
            if archive_path.suffix.lower() != ".zip":
                archive_path = archive_path.with_suffix(".zip")
            package_name = validate_path_component(payload.get("package_name") or archive_path.stem, "package_name")
            temp_archive_path = archive_path.with_suffix(".zip.tmp")
            # Build in a safe location instead of target dir to prevent accidental overwrites
            package_dir = ensure_child_path(self.packages_dir, self.packages_dir / package_name, "package_name")
        else:
            package_name = validate_path_component(payload.get("package_name") or self._default_package_name(), "package_name")
            package_dir = ensure_child_path(self.packages_dir, self.packages_dir / package_name, "package_name")
            archive_path = ensure_child_path(self.packages_dir, self.packages_dir / f"{package_name}.zip", "package_name")
            temp_archive_path = ensure_child_path(self.packages_dir, self.packages_dir / f"{package_name}.zip.tmp", "package_name")
        job_id = validate_path_component(payload.get("job_id") or f"migration-export-{package_name}", "job_id")

        job = self.jobs.write_progress(job_id, stage="prepare", progress=5, message="准备迁移导出目录")

        def _run_export():
            try:
                if package_dir.exists():
                    shutil.rmtree(package_dir)
                if archive_path.exists():
                    archive_path.unlink()
                if temp_archive_path.exists():
                    temp_archive_path.unlink()
                package_dir.mkdir(parents=True, exist_ok=True)

                includes = {
                    "database": self.current_db_path.exists(),
                    "note_results": self.note_output_root.exists(),
                    "uploads": self.uploads_root.exists(),
                    "static": self.static_root.exists(),
                    "wiki": (self.note_output_root / "wiki").exists(),
                    "vector_index": False,
                }

                if includes["database"]:
                    self.jobs.write_progress(job_id, stage="database", progress=25, message="导出数据库")
                    db_target = package_dir / "database" / "notemeld.db"
                    db_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(self.current_db_path, db_target)

                if includes["note_results"]:
                    self.jobs.write_progress(job_id, stage="note_results", progress=45, message="导出笔记结果")
                    self._copy_children(self.note_output_root, package_dir / "note_results", skip_names={"wiki"})

                if includes["uploads"]:
                    self.jobs.write_progress(job_id, stage="uploads", progress=60, message="导出上传附件")
                    self._copy_children(self.uploads_root, package_dir / "uploads")

                if includes["static"]:
                    self.jobs.write_progress(job_id, stage="static", progress=68, message="导出静态图片资源")
                    self._copy_children(self.static_root, package_dir / "static")

                if includes["wiki"]:
                    self.jobs.write_progress(job_id, stage="wiki", progress=75, message="导出 Wiki 贡献")
                    self._copy_children(self.note_output_root / "wiki", package_dir / "wiki")

                counts = self._build_counts()
                manifest = self.manifests.build_manifest(
                    package_id=package_name,
                    operation="export",
                    app_version=str(payload.get("app_version") or ""),
                    counts=counts,
                    includes=includes,
                    warnings=["vector index excluded from migration package"],
                )
                self.manifests.write_manifest(package_dir, manifest)
                self.jobs.write_progress(job_id, stage="archive", progress=90, message="打包迁移压缩包")
                self._build_archive(package_dir, temp_archive_path)
                temp_archive_path.replace(archive_path)
                shutil.rmtree(package_dir)

                self.jobs.mark_completed(
                    job_id,
                    summary={
                        "package_path": str(archive_path),
                        "manifest_path": "manifest.json",
                        "counts": counts,
                    },
                    warnings=manifest["warnings"],
                )
            except Exception as exc:
                self.jobs.mark_failed(job_id, error=str(exc))
                if not background_tasks:
                    raise

        if background_tasks:
            background_tasks.add_task(_run_export)
            return job
        else:
            _run_export()
            return self.jobs.read(job_id)

    def _build_counts(self) -> dict[str, int]:
        import sqlite3

        counts = {
            "conversations": 0,
            "conversation_messages": 0,
            "note_documents": 0,
            "note_result_files": self._file_count(self.note_output_root, skip_names={"wiki"}),
            "upload_files": self._file_count(self.uploads_root),
            "static_files": self._file_count(self.static_root),
            "wiki_files": self._file_count(self.note_output_root / "wiki"),
        }
        if not self.current_db_path.exists():
            return counts

        conn = sqlite3.connect(self.current_db_path)
        try:
            for table_name in ("conversations", "conversation_messages", "note_documents"):
                try:
                    counts[table_name] = int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])
                except Exception:
                    counts[table_name] = 0
        finally:
            conn.close()
        return counts

    def _copy_children(self, source_dir: Path, target_dir: Path, skip_names: set[str] | None = None) -> int:
        if not source_dir.exists():
            return 0
        target_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        skips = skip_names or set()
        for item in source_dir.iterdir():
            if item.name in skips:
                continue
            destination = target_dir / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
                copied += sum(1 for path in item.rglob("*") if path.is_file())
            else:
                shutil.copy2(item, destination)
                copied += 1
        return copied

    def _file_count(self, source_dir: Path, skip_names: set[str] | None = None) -> int:
        if not source_dir.exists():
            return 0
        skips = skip_names or set()
        count = 0
        for item in source_dir.iterdir():
            if item.name in skips:
                continue
            if item.is_dir():
                count += sum(1 for path in item.rglob("*") if path.is_file())
            elif item.is_file():
                count += 1
        return count

    def _build_archive(self, source_dir: Path, archive_path: Path) -> None:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=path.relative_to(source_dir).as_posix())

    def _default_package_name(self) -> str:
        return datetime.now(timezone.utc).strftime("migration-%Y%m%d-%H%M%S")
