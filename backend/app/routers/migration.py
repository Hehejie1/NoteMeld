from typing import Optional
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from fastapi.responses import FileResponse
from pydantic import AliasChoices, BaseModel, Field

from app.security.session_token import require_session_token
from app.services.migration import (
    MigrationExportService,
    MigrationImportService,
    MigrationJobStore,
    MigrationManifestError,
    MigrationReindexService,
)
from app.utils.response import ResponseWrapper as R
from app.utils.storage_paths import migration_upload_dir


router = APIRouter(prefix="/migration", dependencies=[Depends(require_session_token)])


class MigrationExportPayload(BaseModel):
    package_name: Optional[str] = None
    job_id: Optional[str] = None
    app_version: Optional[str] = None
    target_path: Optional[str] = None


class MigrationImportPayload(BaseModel):
    package_path: str = Field(validation_alias=AliasChoices("package_path", "package_dir"))
    job_id: Optional[str] = None
    rebuild_indexes: bool = True


class MigrationReindexPayload(BaseModel):
    task_ids: list[str] = Field(default_factory=list)


@router.post("/export")
def start_migration_export(data: MigrationExportPayload, background_tasks: BackgroundTasks):
    try:
        return R.success(MigrationExportService().start_export(data.model_dump(exclude_none=True), background_tasks=background_tasks))
    except Exception as exc:
        return R.error(str(exc), code=400)


@router.post("/import")
def start_migration_import(data: MigrationImportPayload, background_tasks: BackgroundTasks):
    try:
        return R.success(MigrationImportService().start_import(data.model_dump(exclude_none=True), background_tasks=background_tasks))
    except MigrationManifestError as exc:
        return R.error(exc.message, code=400)
    except FileNotFoundError as exc:
        return R.error(str(exc), code=404)
    except Exception as exc:
        return R.error(str(exc), code=500)


@router.post("/import/upload")
def upload_migration_package(file: UploadFile):
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".zip"):
        return R.error("migration import only accepts .zip packages", code=400)

    target_dir = migration_upload_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{uuid4().hex}-{filename}"
    with target_path.open("wb") as output:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    return R.success({"package_path": str(target_path.resolve())})


@router.get("/{job_id}/job")
def get_migration_job(job_id: str):
    return R.success(MigrationJobStore().read(job_id))


@router.get("/{job_id}/download")
def download_migration_package(job_id: str):
    job = MigrationJobStore().read(job_id)
    package_path = Path(str((job.get("summary") or {}).get("package_path") or "")).expanduser()
    if job.get("status") != "completed" or not package_path.is_file():
        return R.error("migration package is not ready", code=404)
    return FileResponse(
        path=package_path,
        media_type="application/zip",
        filename=package_path.name,
    )


@router.post("/reindex")
def rebuild_migration_indexes(data: MigrationReindexPayload):
    try:
        task_ids = data.task_ids or None
        return R.success(MigrationReindexService().rebuild(task_ids=task_ids))
    except Exception as exc:
        return R.error(str(exc), code=500)
