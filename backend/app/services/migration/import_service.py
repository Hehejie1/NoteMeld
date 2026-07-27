from __future__ import annotations

import shutil
import tempfile
import zipfile
import json
from pathlib import Path

from app.services.migration.job_store import MigrationJobStore
from app.services.migration.manifest_service import MigrationManifestError, MigrationManifestService
from app.services.migration.merge_service import MigrationMergeService
from app.services.migration.reindex_service import MigrationReindexService
from app.services.migration.validation import validate_path_component
from app.utils.storage_paths import database_path, note_output_dir, static_dir, upload_dir


class MigrationImportService:
    def __init__(
        self,
        current_db_path: str | Path | None = None,
        note_output_root: str | Path | None = None,
        uploads_root: str | Path | None = None,
        static_root: str | Path | None = None,
        manifest_service: MigrationManifestService | None = None,
        job_store: MigrationJobStore | None = None,
        merge_service: MigrationMergeService | None = None,
        reindex_service: MigrationReindexService | None = None,
    ):
        self.current_db_path = Path(current_db_path or database_path())
        self.note_output_root = Path(note_output_root or note_output_dir())
        self.uploads_root = Path(uploads_root or upload_dir())
        self.static_root = Path(static_root or static_dir())
        self.manifests = manifest_service or MigrationManifestService()
        self.jobs = job_store or MigrationJobStore()
        self.merge_service = merge_service or MigrationMergeService(self.current_db_path)
        self.reindex_service = reindex_service or MigrationReindexService(
            current_db_path=self.current_db_path,
            note_output_root=self.note_output_root,
        )

    def start_import(self, payload: dict, background_tasks=None) -> dict:
        archive_path = self._resolve_archive_path(payload)
        job_id = validate_path_component(payload.get("job_id") or f"migration-import-{archive_path.stem}", "job_id")

        job = self.jobs.write_progress(job_id, stage="extract", progress=5, message="解压迁移压缩包")

        def _run_import():
            try:
                with tempfile.TemporaryDirectory(prefix="notemeld-migration-import-") as temp_dir:
                    package_dir = Path(temp_dir) / archive_path.stem
                    self._ensure_archive_fits_available_storage(archive_path, self.current_db_path.parent)
                    self._extract_archive(archive_path, package_dir)
                    self._import_extracted_package(
                        job_id=job_id,
                        package_dir=package_dir,
                        archive_path=archive_path,
                        rebuild_indexes=bool(payload.get("rebuild_indexes", True)),
                    )
            except MemoryError as exc:
                self.jobs.mark_failed(
                    job_id,
                    error="导入迁移包时内存不足。建议清除缓存、关闭其他占用内存的应用后再处理。",
                    recoverable=True,
                )
                if not background_tasks:
                    raise
            except Exception as exc:
                self.jobs.mark_failed(job_id, error=str(exc), recoverable=isinstance(exc, MigrationManifestError))
                if not background_tasks:
                    raise

        if background_tasks:
            background_tasks.add_task(_run_import)
            return job
        else:
            _run_import()
            return self.jobs.read(job_id)

    def _resolve_archive_path(self, payload: dict) -> Path:
        raw_path = str(payload.get("package_path") or payload.get("package_dir") or "").strip()
        archive_path = Path(raw_path).expanduser()
        if not raw_path or not archive_path.exists():
            raise FileNotFoundError(f"migration package missing: {archive_path}")
        if not archive_path.is_file() or archive_path.suffix.lower() != ".zip":
            raise MigrationManifestError(
                code="migration_import_requires_zip",
                message="migration import only accepts .zip packages",
            )
        return archive_path.resolve()

    def _ensure_archive_fits_available_storage(self, archive_path: Path, target_dir: Path) -> None:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                total_uncompressed_size = sum(
                    member.file_size
                    for member in archive.infolist()
                    if not member.is_dir()
                )
        except zipfile.BadZipFile as exc:
            raise MigrationManifestError(
                code="migration_import_invalid_archive",
                message=f"migration package is not a valid zip archive: {archive_path}",
            ) from exc

        target_dir.mkdir(parents=True, exist_ok=True)
        available_bytes = int(shutil.disk_usage(target_dir).free)
        if total_uncompressed_size > available_bytes:
            raise MigrationManifestError(
                code="migration_import_insufficient_storage",
                message=(
                    "导入迁移包所需解压空间超过当前磁盘可用空间，存储空间不足。"
                    "请清除缓存或释放磁盘空间后再处理。"
                ),
            )

    def _import_extracted_package(
        self,
        job_id: str,
        package_dir: Path,
        archive_path: Path,
        rebuild_indexes: bool,
    ) -> dict:
        self.jobs.write_progress(job_id, stage="validate", progress=15, message="校验迁移包")
        manifest = self.manifests.validate_manifest(self.manifests.read_manifest(package_dir))
        merged = {}
        copied = {"note_results": 0, "uploads": 0, "static": 0, "wiki": 0}

        package_db = package_dir / "database" / "notemeld.db"
        if manifest["includes"].get("database"):
            self.jobs.write_progress(job_id, stage="merge_db", progress=35, message="增量合并数据库")
            if not package_db.exists():
                raise MigrationManifestError(
                    code="migration_package_missing_database",
                    message=f"migration database missing: {package_db}",
                )
            merged = self.merge_service.merge_database(package_db)

        if manifest["includes"].get("note_results"):
            self.jobs.write_progress(job_id, stage="copy_note_results", progress=55, message="同步笔记结果")
            copied["note_results"] = self._copy_children(package_dir / "note_results", self.note_output_root)

        if manifest["includes"].get("uploads"):
            self.jobs.write_progress(job_id, stage="copy_uploads", progress=70, message="同步上传附件")
            copied["uploads"] = self._copy_children(package_dir / "uploads", self.uploads_root)

        if manifest["includes"].get("static"):
            self.jobs.write_progress(job_id, stage="copy_static", progress=75, message="同步静态图片资源")
            copied["static"] = self._copy_children(package_dir / "static", self.static_root)

        if manifest["includes"].get("wiki"):
            self.jobs.write_progress(job_id, stage="copy_wiki", progress=80, message="同步 Wiki 数据")
            copied["wiki"] = self._copy_children(package_dir / "wiki", self.note_output_root / "wiki")

        reindex_result = {"wiki_rebuilt": False, "vector_rebuilt": 0, "task_ids": []}
        if rebuild_indexes:
            self.jobs.write_progress(job_id, stage="reindex", progress=90, message="重建索引")
            task_ids = self._task_ids_from_note_results(self.note_output_root)
            reindex_result = self.reindex_service.rebuild(task_ids=task_ids or None)

        return self.jobs.mark_completed(
            job_id,
            summary={
                "package_path": str(archive_path),
                "manifest": manifest,
                "merged": merged,
                "copied": copied,
                "reindex": reindex_result,
            },
            warnings=manifest.get("warnings", []),
        )

    def _extract_archive(self, archive_path: Path, target_dir: Path) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    destination = (target_dir / member.filename).resolve()
                    if not self._is_within_directory(target_dir.resolve(), destination):
                        raise MigrationManifestError(
                            code="migration_import_invalid_archive",
                            message=f"archive contains invalid entry: {member.filename}",
                        )
                    if member.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, destination.open("wb") as output:
                        shutil.copyfileobj(source, output)
        except zipfile.BadZipFile as exc:
            raise MigrationManifestError(
                code="migration_import_invalid_archive",
                message=f"migration package is not a valid zip archive: {archive_path}",
            ) from exc

    def _is_within_directory(self, root_dir: Path, target_path: Path) -> bool:
        try:
            target_path.relative_to(root_dir)
            return True
        except ValueError:
            return False

    def _copy_children(self, source_dir: Path, target_dir: Path) -> int:
        if not source_dir.exists():
            return 0
        target_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for item in source_dir.iterdir():
            destination = target_dir / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
                copied += sum(1 for path in item.rglob("*") if path.is_file())
            else:
                shutil.copy2(item, destination)
                copied += 1
        return copied

    def _task_ids_from_note_results(self, note_results_dir: Path) -> list[str]:
        task_ids: list[str] = []
        if not note_results_dir.exists():
            return task_ids
        auxiliary_suffixes = (
            "_audio",
            "_transcript",
            "_ingestion_job",
            "_migration_job",
            "_artifacts",
            "_evidence_anchors",
            "_knowledge_chunks",
            "_markdown_assets",
            "_refine_trace",
            ".status",
        )
        for path in sorted(note_results_dir.glob("*.json")):
            stem = path.stem
            if any(stem.endswith(suffix) for suffix in auxiliary_suffixes):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if stem not in task_ids:
                task_ids.append(stem)
        return task_ids
