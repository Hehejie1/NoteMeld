from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.services.plugins.manager import PluginManager
from app.services.plugins.response import PluginResponse as R
from app.services.plugins.verifier import PluginVerificationError
from app.security.session_token import require_session_token


router = APIRouter(prefix="/plugins", dependencies=[Depends(require_session_token)])
manager = PluginManager()


class InstallPayload(BaseModel):
    source_url: str
    expected_sha256: Optional[str] = None
    plugin_id: Optional[str] = None
    version: Optional[str] = None
    granted_permissions: list[str] = Field(default_factory=list)


@router.get("")
def list_plugins():
    return R.success({"plugins": manager.list()})


@router.get("/ready")
def plugin_ready_gate():
    plugins = manager.list()
    failed = [p["plugin_id"] for p in plugins if p["enabled"] and p["runtime_status"] != "running"]
    return R.success({"ready": not failed, "failed_plugins": failed})


@router.post("/install")
def install_plugin(payload: InstallPayload):
    try:
        return R.success(manager.install(**payload.model_dump()))
    except PluginVerificationError as exc:
        return R.error(str(exc), code=400)
    except Exception as exc:
        return R.error(str(exc), code=502)


@router.post("/{plugin_id}/enable")
def enable_plugin(plugin_id: str):
    try:
        return R.success(manager.set_enabled(plugin_id, True))
    except PluginVerificationError as exc:
        return R.error(str(exc), code=400)


@router.post("/{plugin_id}/disable")
def disable_plugin(plugin_id: str):
    try:
        return R.success(manager.set_enabled(plugin_id, False))
    except PluginVerificationError as exc:
        return R.error(str(exc), code=400)


@router.post("/{plugin_id}/activate/{version}")
def activate_plugin(plugin_id: str, version: str):
    try:
        return R.success(manager.activate(plugin_id, version))
    except PluginVerificationError as exc:
        return R.error(str(exc), code=400)


@router.post("/{plugin_id}/rollback/{version}")
def rollback_plugin(plugin_id: str, version: str):
    try:
        return R.success(manager.rollback(plugin_id, version))
    except PluginVerificationError as exc:
        return R.error(str(exc), code=400)


@router.get("/{plugin_id}/audit")
def plugin_audit(plugin_id: str):
    return R.success({"events": manager.audit(plugin_id)})
