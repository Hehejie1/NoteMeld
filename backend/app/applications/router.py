from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.applications.manifest import ApplicationManifestError
from app.applications.service import ApplicationError, ApplicationService
from app.security.session_token import require_session_token
from app.utils.response import ResponseWrapper as R

router = APIRouter(prefix="/applications", dependencies=[Depends(require_session_token)])
asset_router = APIRouter(prefix="/applications")
service = ApplicationService()


class InstancePayload(BaseModel):
    title: str = ""
    instance_id: str | None = None


class RunPayload(BaseModel):
    request_id: str | None = None
    method: str = "start"
    input: dict[str, Any] = Field(default_factory=dict)


class WorkspacePayload(BaseModel):
    root: str


class ExternalRootsPayload(BaseModel):
    roots: list[str]


class InvokePayload(BaseModel):
    method: str
    input: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["sync", "async"] = "sync"


class CapabilityInvokePayload(BaseModel):
    capability: str
    method: str
    input: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["sync", "async"] = "sync"


class PermissionPayload(BaseModel):
    grants: dict[str, bool]


def _call(fn, *args, **kwargs):
    try:
        return R.success(fn(*args, **kwargs))
    except ApplicationError as exc:
        return R.error(exc.message, code=exc.status, data={"error_code": exc.code})
    except ApplicationManifestError as exc:
        return R.error(exc.message, code=400, data={"error_code": exc.code})


@asset_router.get("/{app_id}/assets/{asset_path:path}")
def get_application_asset(app_id: str, asset_path: str):
    # Application UI assets contain no host secrets. Capability calls remain
    # protected by the session-bound API and the iframe Bridge.
    try:
        return FileResponse(service.registry.asset_path(app_id, asset_path))
    except ApplicationError as exc:
        return R.error(exc.message, code=exc.status, data={"error_code": exc.code})
    except ApplicationManifestError as exc:
        return R.error(exc.message, code=400, data={"error_code": exc.code})


@router.get("")
def list_applications():
    return _call(service.list)


@router.get("/settings/workspace")
def get_workspace_setting():
    return _call(service.workspace_config)


@router.put("/settings/workspace")
def put_workspace_setting(payload: WorkspacePayload):
    return _call(service.set_workspace_config, payload.root)


@router.put("/settings/external-read-roots")
def put_external_read_roots(payload: ExternalRootsPayload):
    return _call(service.set_external_read_roots, payload.roots)


@router.post("/runs/{run_id}/cancel")
def cancel_application_run(run_id: str):
    return _call(service.cancel_run, run_id)


@router.get("/runs/{run_id}")
def get_application_run(run_id: str):
    return _call(service.get_run, run_id)


@router.get("/runs/{run_id}/logs")
def get_application_run_logs(run_id: str):
    return _call(service.run_logs, run_id)


@router.post("/runs/{run_id}/invoke")
def invoke_application_run(run_id: str, payload: InvokePayload):
    if payload.mode != "sync":
        return _call(service.start_runtime_job, run_id, payload.method, payload.input)
    return _call(service.invoke_run, run_id, payload.method, payload.input)


@router.post("/runs/{run_id}/capability")
def invoke_application_capability(run_id: str, payload: CapabilityInvokePayload):
    return _call(service.invoke_capability, run_id, payload.capability, payload.method, payload.input, payload.mode)


@router.get("/{app_id}")
def get_application(app_id: str):
    return _call(service.get, app_id)


@router.post("/{app_id}/enable")
def enable_application(app_id: str):
    return _call(service.set_enabled, app_id, True)


@router.post("/{app_id}/disable")
def disable_application(app_id: str):
    return _call(service.set_enabled, app_id, False)


@router.get("/{app_id}/permissions")
def get_application_permissions(app_id: str):
    return _call(service.get_permissions, app_id)


@router.put("/{app_id}/permissions")
def put_application_permissions(app_id: str, payload: PermissionPayload):
    return _call(service.set_permissions, app_id, payload.grants)


@router.get("/jobs/{job_id}")
def get_application_job(job_id: str):
    return _call(service.get_job, job_id)


@router.get("/jobs/{job_id}/events")
def get_application_job_events(job_id: str, after_sequence: int = 0):
    return _call(service.job_events, job_id, after_sequence)


@router.get("/artifacts/{artifact_id}/download")
def download_application_artifact(artifact_id: str):
    try:
        data = service.download_artifact(artifact_id)
        return JSONResponse(content=data, headers={"Content-Disposition": f'attachment; filename="{artifact_id}.json"'})
    except ApplicationError as exc:
        return R.error(exc.message, code=exc.status, data={"error_code": exc.code})


@router.post("/{app_id}/instances")
def create_application_instance(app_id: str, payload: InstancePayload):
    return _call(service.create_instance, app_id, payload.title, payload.instance_id)


@router.get("/{app_id}/instances")
def list_application_instances(app_id: str):
    return _call(service.instances, app_id)


@router.post("/{app_id}/instances/{instance_id}/runs")
def start_application_run(app_id: str, instance_id: str, payload: RunPayload):
    return _call(service.start_run, app_id, instance_id, payload.model_dump())
