from fastapi import APIRouter, HTTPException, Query

from app.services.ingestion.artifact_reader import IngestionArtifactError, IngestionArtifactReader
from app.services.ingestion.job_store import IngestionJobStore
from app.services.ingestion.source_asset_reader import IngestionSourceAssetReader
from app.utils.response import ResponseWrapper as R


router = APIRouter(prefix="/ingestion")


def _reader() -> IngestionArtifactReader:
    return IngestionArtifactReader()


def _artifact_error(exc: IngestionArtifactError) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": exc.code, "message": exc.message},
    )


@router.get("/{task_id}/report")
def get_ingestion_report(task_id: str):
    try:
        return R.success(_reader().build_report(task_id))
    except IngestionArtifactError as exc:
        raise _artifact_error(exc) from exc


@router.get("/{task_id}/evidence")
def get_ingestion_evidence(task_id: str):
    try:
        return R.success(_reader().read_evidence(task_id))
    except IngestionArtifactError as exc:
        raise _artifact_error(exc) from exc


@router.get("/{task_id}/chunks")
def get_ingestion_chunks(task_id: str):
    try:
        return R.success(_reader().read_chunks(task_id))
    except IngestionArtifactError as exc:
        raise _artifact_error(exc) from exc


@router.get("/{task_id}/source")
def get_ingestion_source(task_id: str):
    try:
        return R.success(IngestionSourceAssetReader().read_source(task_id))
    except IngestionArtifactError as exc:
        raise _artifact_error(exc) from exc


@router.get("/{task_id}/job")
def get_ingestion_job(task_id: str):
    return R.success(IngestionJobStore().read(task_id))


@router.get("/jobs")
def list_ingestion_jobs(limit: int = Query(default=50, ge=1, le=200)):
    """Return the durable plugin/ingestion task projection for app-level monitoring."""
    return R.success(IngestionJobStore().list(limit))
