from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.cloud_sync import CloudClient, CloudSyncHostRuntime
from app.cloud_sync.secure_identity import OsIdentityStore
from app.security.session_token import require_session_token
from app.utils.storage_paths import data_root


router = APIRouter(prefix="/cloud-sync", tags=["cloud-sync"], dependencies=[Depends(require_session_token)])


class HostBootstrapRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=2048)
    token: str = Field(min_length=1, max_length=8192)
    device_id: str = Field(min_length=1, max_length=256)
    display_name: str = Field(default="NoteMeld Desktop", max_length=256)
    lan_endpoints: list[str] = Field(default_factory=list, max_length=8)


@router.post("/host/bootstrap")
def bootstrap_host(payload: HostBootstrapRequest, request: Request):
    """Install the platform-backed remote Host after desktop Cloud login.

    The token is accepted only over the authenticated loopback desktop API and
    retained in the in-memory CloudClient; the identity private key is loaded
    from the OS credential store and never enters the request or environment.
    """
    app = request.app
    current = getattr(app.state, "cloud_sync_runtime", None)
    if current is not None:
        if current.host_device_id == payload.device_id:
            return {"status": "already_running", "device_id": payload.device_id}
        current.close()

    identity = OsIdentityStore().load_or_create()
    public_key = base64.urlsafe_b64encode(identity.public_key).decode("ascii").rstrip("=")
    client = CloudClient(payload.base_url, token=payload.token, device_id=payload.device_id)
    client.register_device(
        payload.device_id,
        "desktop",
        payload.display_name,
        public_key=public_key,
        lan_endpoints=payload.lan_endpoints,
    )
    mailbox_path = Path(data_root()) / "cloud-sync" / "mailbox.sqlite"
    runtime = CloudSyncHostRuntime(
        cloud_client=client,
        host_device_id=payload.device_id,
        mailbox_path=mailbox_path,
        cipher_resolver=lambda _authorization: (_ for _ in ()).throw(RuntimeError("session cipher is not installed")),
        host_signing_private=identity.private_key,
        host_signing_public=identity.public_key,
    )
    runtime.install(app)
    app.state.cloud_sync_runtime = runtime
    return {"status": "started", "device_id": payload.device_id, "public_key": public_key}


@router.post("/host/stop")
def stop_host(request: Request):
    runtime = getattr(request.app.state, "cloud_sync_runtime", None)
    if runtime is None:
        return {"status": "stopped"}
    runtime.close()
    request.app.state.cloud_sync_runtime = None
    return {"status": "stopped"}


@router.post("/host/relay/{session_id}/start")
async def start_relay(session_id: str, request: Request):
    runtime = getattr(request.app.state, "cloud_sync_runtime", None)
    if runtime is None:
        raise RuntimeError("Cloud Host runtime is not started")
    return await runtime.start_relay_session(session_id)


@router.post("/host/relay/{session_id}/stop")
async def stop_relay(session_id: str, request: Request):
    runtime = getattr(request.app.state, "cloud_sync_runtime", None)
    if runtime is None:
        return {"status": "stopped", "session_id": session_id}
    return await runtime.stop_relay_session(session_id)
