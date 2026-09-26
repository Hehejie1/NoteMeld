from __future__ import annotations

import hashlib
import base64
import binascii
from contextlib import asynccontextmanager, contextmanager
import json
import os
import secrets
import shutil
import threading
import time
import uuid
import fnmatch
import ipaddress
import logging
import re
import socket
import weakref
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import httpx

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import MutableHeaders
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import CloudSettings, load_settings
from .db import CloudDB
from .agent import OpenAICompatibleAgentRunner, create_agent_runner
from .security import decrypt_secret, encrypt_secret, hash_password, issue_token, parse_token, token_digest, token_expiry, verify_password
from .workspace import Workspace, workspace_mutation_lock
from .terminal import SandboxedShell, TerminalError, open_workspace_shell
from .backup_storage import BackupStorage, create_backup_storage
from .relay import InMemoryRelayBroker, RedisRelayBroker
from .mailer import MailDeliveryError, send_invitation as deliver_invitation, send_verification_code as deliver_verification_code


TOKEN_SCOPES = frozenset({"*", "auth.token", "admin", "device.read", "device.write", "grant.read", "grant.write", "session.read", "session.write", "share.read", "share.write", "workspace.read", "workspace.write", "model.read", "model.write"})
ORGANIZATION_PREFERENCE_KEYS = frozenset({"default_workspace", "default_model", "high_risk_approval"})
DEVICE_TOKEN_SCOPES = TOKEN_SCOPES - {"*", "auth.token", "admin"}
GRANT_SCOPES = frozenset({"message.send", "context.select", "model.select", "tool.invoke", "event.receive", "workspace.read", "workspace.write", "dangerous.approve", "approval.remote.resolve", "session.permission.manage", "session.full_access", "full_access"})
LAN_ENDPOINT_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::1/128"),
)
SHARE_SCOPES = frozenset({"message.send", "event.receive"})
_DUMMY_PASSWORD_HASH = hash_password("notemeld-dummy-password")
_MAX_HISTORY_MESSAGES = 200
_MAX_HISTORY_MESSAGE_CHARS = 100_000
_MAX_HISTORY_CHARS = 1_000_000
LOGGER = logging.getLogger(__name__)
_CONFIG_SYNC_FORBIDDEN_KEY_PARTS = ("secret", "password", "api_key", "apikey", "token", "private_key")


def _config_sync_key_allowed(kind: str, key: str) -> bool:
    del kind
    lowered = key.lower()
    return not any(part in lowered for part in _CONFIG_SYNC_FORBIDDEN_KEY_PARTS)


class SecurityHeadersMiddleware:
    """Add response headers without Starlette BaseHTTPMiddleware stream wrapping."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        scheme = str(scope.get("scheme", ""))

        async def send_with_security_headers(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                headers = MutableHeaders(raw=message.setdefault("headers", []))
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "SAMEORIGIN" if path.startswith("/cloud/") else "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("Cache-Control", "no-store")
                if path == "/cloud" or path.startswith("/cloud/") or path.startswith("/assets/"):
                    headers.setdefault(
                        "Content-Security-Policy",
                        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                        "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws: wss:; "
                        "object-src 'none'; base-uri 'self'; frame-ancestors 'self'",
                    )
                if scheme == "https":
                    headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


class RequestSizeGuardMiddleware:
    """Enforce request limits while preserving the original ASGI receive flow."""

    def __init__(self, app: Any, max_request_bytes: int) -> None:
        self.app = app
        self.max_request_bytes = max_request_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except ValueError:
                await self._reject(send, 400, "invalid content length")
                return
            if content_length < 0 or content_length > self.max_request_bytes:
                await self._reject(send, 413, "request body too large")
                return

        # Buffer the bounded body before entering Starlette/FastAPI. Raising
        # from a wrapped receive can be converted into a generic 400 by the
        # request parser before this middleware sees it; replaying the
        # validated messages keeps oversized chunked requests deterministic.
        buffered: list[dict[str, Any]] = []
        received = 0
        while True:
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_request_bytes:
                    await self._reject(send, 413, "request body too large")
                    return
                buffered.append(message)
                if not message.get("more_body", False):
                    break
            else:
                buffered.append(message)
                break

        async def replay_receive() -> dict[str, Any]:
            if buffered:
                return buffered.pop(0)
            # 缓冲已全部回放：交回原始 receive。它会阻塞直到客户端真正断开，
            # 从而既不会用无限空 request 形成忙循环，也不会过早终止响应流。
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(send: Any, status_code: int, message: str) -> None:
        body = json.dumps({"code": status_code, "msg": message}, ensure_ascii=False).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))],
        })
        await send({"type": "http.response.body", "body": body, "more_body": False})


class RequestTooLargeError(Exception):
    pass


class LoginRequest(BaseModel):
    username: str | None = Field(default=None, max_length=256)
    account_id: str | None = Field(default=None, max_length=128)
    password: str = Field(max_length=4096)


class EmailPasswordLogin(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=4096)


class VerificationCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    purpose: str = Field(default="login", pattern="^(login|access_request|password_reset)$")


class EmailCodeLogin(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    code: str = Field(min_length=6, max_length=6, pattern="^[0-9]{6}$")


class PasswordReset(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    code: str = Field(min_length=6, max_length=6, pattern="^[0-9]{6}$")
    password: str = Field(min_length=8, max_length=256)


class AccessRequestCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)
    confirm_password: str = Field(min_length=8, max_length=256)
    # The Cloud Web form intentionally treats the application note as optional.
    # Keep the API contract aligned with that UI instead of returning a 422 for
    # an otherwise valid access request with no additional explanation.
    reason: str = Field(default="", max_length=2000)


class AccessRequestReview(BaseModel):
    status: str = Field(pattern="^(approved|rejected)$")


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=128)


class InvitationAccept(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)


class PreferencesUpdate(BaseModel):
    notifications_enabled: bool | None = None
    high_risk_approval: bool | None = None
    default_workspace: str | None = Field(default=None, max_length=128)
    default_model: str | None = Field(default=None, max_length=128)
    theme: str | None = Field(default=None, pattern="^(light|dark)$")
    language: str | None = Field(default=None, pattern="^(zh-CN|en-US)$")


class OrganizationPreferencesUpdate(BaseModel):
    default_workspace: str | None = Field(default=None, max_length=128)
    default_model: str | None = Field(default=None, max_length=128)
    high_risk_approval: bool | None = None


class ConfigSyncChange(BaseModel):
    kind: str = Field(min_length=1, max_length=64)
    key: str = Field(min_length=1, max_length=256)
    operation: str = Field(pattern="^(set|delete)$")
    value: Any = None


class ConfigSyncChangesRequest(BaseModel):
    workspace_id: str = Field(default="default", min_length=1, max_length=128)
    base_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128)
    changes: list[ConfigSyncChange] = Field(min_length=1, max_length=100)


class OrganizationMemoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=20_000)
    source: str = Field(default="admin", min_length=1, max_length=100)


class UserProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    avatar: str | None = Field(default=None, min_length=1, max_length=4)
    password: str | None = Field(default=None, min_length=8, max_length=256)


class PersonalTokenCreate(BaseModel):
    scopes: list[str] = Field(default_factory=lambda: ["*"] , max_length=32)
    expires_at: int | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(scope not in TOKEN_SCOPES for scope in value):
            raise ValueError("invalid token scope")
        if "*" in value and len(value) != 1:
            raise ValueError("wildcard token scope cannot be combined")
        return value

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value: int | None) -> int | None:
        if value is not None and value <= int(time.time()):
            raise ValueError("expires_at must be in the future")
        return value


class PairingConfirm(BaseModel):
    code: str = Field(min_length=8, max_length=64)
    device_id: str = Field(min_length=8, max_length=256)
    platform: str = Field(min_length=1, max_length=32)
    display_name: str = Field(min_length=1, max_length=128)
    public_key: str | None = None


class GrantCreate(BaseModel):
    controller_device_id: str
    host_device_id: str
    role: str = Field(default="standard", pattern="^(standard|super_admin)$")
    scopes: list[str] = Field(default_factory=lambda: ["message.send", "context.select", "model.select", "tool.invoke"], max_length=32)
    workspace_refs: list[str] = Field(default_factory=list, max_length=32)
    expires_at: int | None = None

    @field_validator("scopes")
    @classmethod
    def validate_grant_scopes(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(scope not in GRANT_SCOPES for scope in value):
            raise ValueError("invalid grant scope")
        return value


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=256)
    role: str = "user"


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    password: str | None = Field(default=None, min_length=12, max_length=256)
    disabled: bool | None = None


class DeviceCreate(BaseModel):
    device_id: str = Field(min_length=8, max_length=256)
    platform: str = Field(min_length=1, max_length=32)
    display_name: str = Field(min_length=1, max_length=128)
    public_key: str | None = None
    lan_endpoints: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("lan_endpoints")
    @classmethod
    def validate_lan_endpoints(cls, value: list[str]) -> list[str]:
        return _validate_lan_endpoints(value)


class DeviceHeartbeat(BaseModel):
    lan_endpoints: list[str] | None = Field(default=None, max_length=8)

    @field_validator("lan_endpoints")
    @classmethod
    def validate_lan_endpoints(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _validate_lan_endpoints(value)


class DevicePermissionsUpdate(BaseModel):
    workspace_read: bool = True
    remote_execute: bool = False
    session_read: bool = True
    artifact_download: bool = True
    approval_required: bool = True


class DeviceKeyRotate(BaseModel):
    public_key: str


class DeviceProof(BaseModel):
    challenge: str = Field(min_length=16, max_length=256)
    signature: str = Field(min_length=16, max_length=256)


class DeviceTokenCreate(BaseModel):
    scopes: list[str] = Field(default_factory=lambda: sorted(DEVICE_TOKEN_SCOPES), max_length=32)
    expires_in_seconds: int = Field(default=24 * 60 * 60, ge=300, le=30 * 24 * 60 * 60)
    revoke_source_token: bool = True

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        if not value or len(set(value)) != len(value) or any(scope not in DEVICE_TOKEN_SCOPES for scope in value):
            raise ValueError("invalid device token scope")
        return value


class LanAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=256)
    controller_device_id: str = Field(min_length=8, max_length=256)
    host_device_id: str = Field(min_length=8, max_length=256)


class AuthorityLease(BaseModel):
    owner: str = Field(min_length=1, max_length=128)
    ttl_seconds: int = Field(default=30, ge=5, le=300)


class SessionCreate(BaseModel):
    kind: str = Field(pattern="^(cloud_native|device_remote)$")
    title: str = Field(default="New session", max_length=200)
    workspace_id: str = Field(default="default", min_length=1, max_length=128, pattern="^[A-Za-z0-9_-]+$")
    model_id: str | None = Field(default=None, max_length=128)


class SessionRename(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=256)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    enabled: bool = True
    is_default: bool = False


class ModelDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=64)
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)


class ModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider: str | None = Field(default=None, min_length=1, max_length=64)
    model: str | None = Field(default=None, min_length=1, max_length=256)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    enabled: bool | None = None
    is_default: bool | None = None


_PROTOCOL_PATTERN = "^(openai-compatible|anthropic-messages|ollama)$"


class CatalogProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=128)
    vendor_id: str = Field(default="custom", min_length=1, max_length=64)
    protocol: str = Field(pattern=_PROTOCOL_PATTERN)
    base_url: str = Field(min_length=1, max_length=2048)
    auth_type: str = Field(default="bearer", pattern="^(bearer|x-api-key|none)$")
    api_key: str | None = Field(default=None, max_length=4096)
    organization_id: str | None = Field(default=None, min_length=1, max_length=64)


class CatalogProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    vendor_id: str | None = Field(default=None, min_length=1, max_length=64)
    protocol: str | None = Field(default=None, pattern=_PROTOCOL_PATTERN)
    base_url: str | None = Field(default=None, min_length=1, max_length=2048)
    auth_type: str | None = Field(default=None, pattern="^(bearer|x-api-key|none)$")
    api_key: str | None = Field(default=None, max_length=4096)
    organization_id: str | None = Field(default=None, min_length=1, max_length=64)


class CatalogModelItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=256)
    display_name: str | None = Field(default=None, min_length=1, max_length=256)
    context_window: int = Field(default=128000, ge=512, le=4_000_000)
    modalities: str = Field(default="text", min_length=1, max_length=64)
    enabled: bool = True
    is_default: bool = False


class CatalogModelBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    models: list[CatalogModelItem] = Field(min_length=1, max_length=200)
    organization_id: str | None = Field(default=None, min_length=1, max_length=64)


class CatalogModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=1, max_length=256)
    context_window: int | None = Field(default=None, ge=512, le=4_000_000)
    modalities: str | None = Field(default=None, min_length=1, max_length=64)
    enabled: bool | None = None
    is_default: bool | None = None
    test_status: str | None = Field(default=None, pattern="^(unknown|testing|ok|failed)$")


class CatalogDiscoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol: str = Field(pattern=_PROTOCOL_PATTERN)
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    organization_id: str | None = Field(default=None, min_length=1, max_length=64)


class CatalogTestConnectionRequest(CatalogDiscoverRequest):
    model_id: str | None = Field(default=None, min_length=1, max_length=256)


class CatalogDefaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: str | None = Field(default=None, min_length=1, max_length=64)


class ApprovalResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=2000)


class SessionImportFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=1024)
    content_base64: str
    sha256: str = Field(pattern="^[a-f0-9]{64}$")
    size: int = Field(ge=0)
    mime_type: str = Field(min_length=1, max_length=255)


class SessionImportEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: int | None = Field(default=None, ge=0)


class SessionImport(BaseModel):
    """Explicit allowlist for a local-to-cloud full-share snapshot."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    source_session_id: str = Field(min_length=1, max_length=256)
    source_device_id: str = Field(min_length=8, max_length=256)
    title: str = Field(default="Imported session", max_length=200)
    conversation: dict[str, Any] = Field(default_factory=dict)
    events: list[SessionImportEvent] = Field(default_factory=list, max_length=100_000)
    compression: dict[str, Any] | list[Any] | None = None
    memory: dict[str, Any] | list[Any] | None = None
    model_descriptor: dict[str, Any] = Field(default_factory=dict)
    mcp_config: dict[str, Any] | list[Any] = Field(default_factory=dict)
    tool_records: list[dict[str, Any]] = Field(default_factory=list, max_length=100_000)
    approval_records: list[dict[str, Any]] = Field(default_factory=list, max_length=100_000)
    task_state: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    files: list[SessionImportFile] = Field(default_factory=list)


class CommandCreate(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    input: str = Field(min_length=1, max_length=100_000)
    attachments: list[dict[str, Any]] = Field(default_factory=list, max_length=16)
    model_id: str | None = Field(default=None, max_length=128)
    authorization_mode: str = Field(default="default", pattern="^(default|full)$")


class StreamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: str = Field(min_length=1, max_length=65536)
    request_id: str = Field(min_length=1, max_length=64)
    model_id: str | None = None
    authorization_mode: str = Field(default="default", pattern="^(default|full)$")


class TerminalExec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(min_length=1, max_length=4096)
    cwd: str | None = None


class CommandRecover(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str = Field(pattern="^(resume|abandon)$")


class WorkspaceWrite(BaseModel):
    content: str = Field(max_length=10_000_000)


class WorkspaceRestore(BaseModel):
    backup_id: str = Field(min_length=1, max_length=128, pattern="^[A-Za-z0-9_-]+$")


class ShareTokenCreate(BaseModel):
    session_id: str
    role: str = Field(default="viewer", pattern="^(viewer|standard|super_admin)$")
    scopes: list[str] = Field(default_factory=list, max_length=32)
    expires_at: int | None = None

    @field_validator("scopes")
    @classmethod
    def validate_share_scopes(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(scope not in SHARE_SCOPES for scope in value):
            raise ValueError("invalid share scope")
        return value


def create_app(settings: CloudSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.validate()
    db = CloudDB(settings.database_path)
    db.init()
    _recover_running_commands(db)
    settings.workspaces_dir.mkdir(parents=True, exist_ok=True)
    backup_storage: BackupStorage = create_backup_storage(settings)
    _bootstrap_admin(db, settings)
    if settings.startup_backup_image:
        _restore_startup_backup(db, settings)
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.worker_shutdown.clear()
        _start_command_reconciler(application, db)
        _start_queued_workers(application, db)
        yield
        _stop_queued_workers(application)
        close_relay = getattr(application.state, "relay_broker", None)
        close_relay = getattr(close_relay, "close", None)
        if callable(close_relay):
            result = close_relay()
            if hasattr(result, "__await__"):
                await result
        close = getattr(application.state.agent_runner, "close", None)
        if callable(close):
            close()

    app = FastAPI(title="NoteMeld Cloud", version="0.1.0", lifespan=lifespan)
    configured_cloud_web_root = os.getenv("NOTEMELD_CLOUD_WEB_DIST")
    cloud_web_candidates = [
        Path(configured_cloud_web_root).expanduser().resolve() if configured_cloud_web_root else None,
        Path(__file__).resolve().parent.parent / "desktop" / "frontend" / "dist-cloud-web",
    ]
    cloud_web_root = next((candidate for candidate in cloud_web_candidates if candidate and candidate.is_dir()), None)
    if cloud_web_root and cloud_web_root.is_dir():
        # Serve hashed assets directly and use the production index for every
        # Cloud deep link.  This keeps BrowserRouter routes working without
        # falling back to the old docs/new-product prototype.
        assets_root = cloud_web_root / "assets"
        if assets_root.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_root), name="cloud-web-assets")

        cloud_favicon = cloud_web_root / "icon.svg"
        if not cloud_favicon.is_file():
            cloud_favicon = next(iter(assets_root.glob("notemeld-cloud-logo-*")), cloud_favicon)
        if cloud_favicon.is_file():
            @app.get("/favicon.ico", include_in_schema=False)
            def cloud_favicon_route() -> FileResponse:
                return FileResponse(cloud_favicon, media_type="image/svg+xml")

        @app.get("/cloud", include_in_schema=False)
        @app.get("/cloud/{path:path}", include_in_schema=False)
        def cloud_web_fallback(path: str = "") -> FileResponse:
            # Never revive the removed `/docs/new-product` HTML prototype (or
            # make its former `/cloud/pages/*.html` aliases look like valid
            # production routes).  BrowserRouter deep links remain supported
            # for application routes, while legacy prototype paths are a hard
            # 404.
            normalized_path = path.strip("/")
            if normalized_path.startswith("pages/") or normalized_path.endswith(".html"):
                raise HTTPException(status_code=404, detail="cloud page not found")
            return FileResponse(cloud_web_root / "index.html")

    @app.get("/", include_in_schema=False)
    def cloud_home() -> RedirectResponse:
        return RedirectResponse("/cloud/login")

    app.add_middleware(RequestSizeGuardMiddleware, max_request_bytes=settings.max_request_bytes)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Share-Token", "X-Device-Id", "X-Request-Id"])
    app.state.db = db
    app.state.settings = settings
    app.state.agent_runner = create_agent_runner(settings)
    app.state.command_locks: dict[str, threading.RLock] = {}
    app.state.command_locks_guard = threading.RLock()
    app.state.workspace_locks = weakref.WeakValueDictionary()
    app.state.workspace_locks_guard = threading.RLock()
    app.state.user_locks = weakref.WeakValueDictionary()
    app.state.user_locks_guard = threading.RLock()
    app.state.queue_workers: dict[str, threading.Thread] = {}
    app.state.queue_conditions: dict[tuple[str, str], threading.Condition] = {}
    # Native SDK turns waiting for approval must remain addressable by the
    # Cloud approval API. The runner owns the live native runtime; the DB owns
    # the durable approval record.
    app.state.native_approval_runtimes: dict[str, Any] = {}
    app.state.native_approval_lock = threading.RLock()
    app.state.worker_shutdown = threading.Event()
    app.state.command_reconciler: threading.Thread | None = None

    if settings.relay_backend == "memory":
        app.state.relay_broker = InMemoryRelayBroker()
    elif settings.relay_backend == "redis":
        app.state.relay_broker = RedisRelayBroker(settings.relay_url or "", online_ttl_seconds=settings.device_online_ttl_seconds)
    else:
        raise RuntimeError(f"relay backend '{settings.relay_backend}' is not installed in this build")
    app.state.relay_sequences: dict[tuple[str, str], int] = {}
    app.state.device_challenges: dict[str, tuple[str, str, int]] = {}
    app.state.device_proofs: dict[tuple[str, str], int] = {}

    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "notemeld-cloud"}

    @app.get("/ready")
    async def readiness() -> dict:
        checks: dict[str, str] = {}
        agent_backend = "canonical-sdk" if getattr(app.state.agent_runner, "native_library", None) else ("openai-compatible" if settings.agent_base_url else "deterministic")
        try:
            with db.connect() as cx:
                cx.execute("SELECT 1").fetchone()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
        checks["workspace_root"] = "ok" if settings.workspaces_dir.is_dir() and os.access(settings.workspaces_dir, os.W_OK) else "error"
        if settings.relay_backend == "redis":
            relay_ready = await app.state.relay_broker.ready()
            checks["relay"] = "ok" if relay_ready else "error"
        if settings.require_device_proof:
            try:
                import cryptography  # noqa: F401
                checks["device_proof_crypto"] = "ok"
            except ImportError:
                checks["device_proof_crypto"] = "error"
        if settings.deployment_env == "production":
            # Production readiness must describe the runtime that will execute
            # turns, not merely the presence of a provider URL. The
            # deterministic and Python-owned adapters remain development/test
            # fixtures and can never make a production deployment ready.
            provider_configured = bool(settings.agent_base_url)
            if not provider_configured and agent_backend == "canonical-sdk":
                try:
                    with db.connect() as cx:
                        default_model = cx.execute(
                            "SELECT base_url,api_key_ciphertext FROM models WHERE enabled=1 AND is_default=1 ORDER BY created_at LIMIT 1"
                        ).fetchone()
                    if default_model and default_model["base_url"] and default_model["api_key_ciphertext"]:
                        decrypt_secret(default_model["api_key_ciphertext"], settings.secret_key)
                        provider_configured = True
                except Exception:
                    provider_configured = False
            checks["agent_provider_config"] = "ok" if provider_configured and agent_backend == "canonical-sdk" else "error"
            checks["backup_storage_config"] = "ok" if settings.backup_storage_backend == "s3" and settings.s3_bucket else "error"
            checks["otp_delivery_config"] = "ok" if not settings.otp_dev_mode and settings.smtp_host and settings.smtp_sender else "error"
            checks["device_proof_config"] = "ok" if settings.require_device_proof else "error"
            checks["release_identity"] = "ok" if settings.build_commit and settings.image_digest else "error"
        identity = {"build_commit": settings.build_commit, "image_digest": settings.image_digest}
        if any(value != "ok" for value in checks.values()):
            raise HTTPException(503, detail={"service": "notemeld-cloud", "ready": False, "environment": settings.deployment_env, "agent_backend": agent_backend, "checks": checks, **identity})
        return {"service": "notemeld-cloud", "ready": True, "environment": settings.deployment_env, "agent_backend": agent_backend, "checks": checks, **identity}

    @app.get("/v1/capabilities")
    def capabilities(current=Depends(_auth_dependency(db))):
        return {"code": 0, "msg": "success", "data": {
            "protocol_version": "notemeld.sync.v1",
            "protocol": {"name": "notemeld.sync", "current": 1, "min": 1, "max": 1},
            "runtime": {"sdk_version": "0.1.0", "abi": 1, "schema": 1},
            "service": {"version": "0.1.0", "build_commit": settings.build_commit},
            "required_features": ["config_sync_v1", "e2ee_relay_v1", "durable_receipt_v1"],
            "canonical_session_prefix": "/v1/cloud/sessions",
            "device_proof_required": settings.require_device_proof,
            "e2ee_relay_envelope": True,
            "relay_persists_payload": False,
            "relay_backend": settings.relay_backend,
            "relay_multi_worker": settings.relay_backend == "redis",
            "lan_first_candidates": True,
            "worker_count": settings.worker_count,
            "max_request_bytes": settings.max_request_bytes,
            "event_page_limit": 5000,
            "relay_max_frame_bytes": settings.relay_max_frame_bytes,
            "max_active_commands_per_user": settings.max_active_commands_per_user,
            "device_token_max_ttl_seconds": 30 * 24 * 60 * 60,
            "max_workspace_bytes": settings.max_workspace_bytes,
            "max_workspace_files": settings.max_workspace_files,
            "features": {"cloud_agent": True, "session_queue": True, "command_recovery": True, "approval_gated_mutations": True, "model_registry": True, "device_tokens": True},
        }}

    @app.get("/v1/config-sync/snapshot")
    def config_sync_snapshot(workspace_id: str = "default", after_revision: int = 0, current=Depends(_auth_dependency(db))):
        if not workspace_id or len(workspace_id) > 128 or after_revision < 0:
            raise HTTPException(422, "invalid config sync cursor")
        user_id = current["id"]
        with db.connect() as cx:
            state = cx.execute("SELECT revision FROM config_sync_state WHERE user_id=? AND workspace_id=?", (user_id, workspace_id)).fetchone()
            revision = int(state["revision"]) if state else 0
            rows = cx.execute(
                "SELECT kind,item_key,value_json,revision,deleted FROM config_sync_items WHERE user_id=? AND workspace_id=? AND revision>? ORDER BY revision,kind,item_key",
                (user_id, workspace_id, after_revision),
            ).fetchall()
        items = [{"kind": row["kind"], "key": row["item_key"], "value": json.loads(row["value_json"])} for row in rows if not row["deleted"]]
        deleted = [{"kind": row["kind"], "key": row["item_key"], "revision": row["revision"]} for row in rows if row["deleted"]]
        return {"code": 0, "msg": "success", "data": {"revision": revision, "full": after_revision == 0, "items": items, "deleted": deleted, "next_cursor": None, "server_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}

    @app.post("/v1/config-sync/changes")
    def config_sync_changes(payload: ConfigSyncChangesRequest, current=Depends(_auth_dependency(db))):
        user_id = current["id"]
        if any(not _config_sync_key_allowed(change.kind, change.key) for change in payload.changes):
            raise HTTPException(422, "sensitive configuration keys cannot be synchronized")
        identities = [(change.kind, change.key) for change in payload.changes]
        if len(set(identities)) != len(identities):
            raise HTTPException(422, "duplicate configuration change")
        try:
            request_hash = hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "configuration value is not JSON serializable") from exc
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            existing = cx.execute("SELECT request_hash,response_json FROM config_sync_idempotency WHERE user_id=? AND workspace_id=? AND idempotency_key=?", (user_id, payload.workspace_id, payload.idempotency_key)).fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    cx.execute("ROLLBACK")
                    raise HTTPException(409, "idempotency key was already used for another request")
                response = json.loads(existing["response_json"])
                cx.execute("COMMIT")
                return response
            state = cx.execute("SELECT revision FROM config_sync_state WHERE user_id=? AND workspace_id=?", (user_id, payload.workspace_id)).fetchone()
            current_revision = int(state["revision"]) if state else 0
            if payload.base_revision != current_revision:
                cx.execute("ROLLBACK")
                return JSONResponse(status_code=409, content={"code": "revision_conflict", "msg": "configuration revision conflict", "data": {"current_revision": current_revision}})
            items: list[dict[str, Any]] = []
            deleted: list[dict[str, Any]] = []
            revision = current_revision
            for change in payload.changes:
                revision += 1
                is_deleted = change.operation == "delete"
                value_json = None if is_deleted else json.dumps(change.value, ensure_ascii=False, separators=(",", ":"))
                cx.execute(
                    "INSERT INTO config_sync_items(user_id,workspace_id,kind,item_key,value_json,revision,deleted,updated_at) VALUES(?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(user_id,workspace_id,kind,item_key) DO UPDATE SET value_json=excluded.value_json,revision=excluded.revision,deleted=excluded.deleted,updated_at=excluded.updated_at",
                    (user_id, payload.workspace_id, change.kind, change.key, value_json, revision, int(is_deleted), now),
                )
                if is_deleted:
                    deleted.append({"kind": change.kind, "key": change.key, "revision": revision})
                else:
                    items.append({"kind": change.kind, "key": change.key, "value": change.value, "revision": revision})
            cx.execute(
                "INSERT INTO config_sync_state(user_id,workspace_id,revision,updated_at) VALUES(?,?,?,?) ON CONFLICT(user_id,workspace_id) DO UPDATE SET revision=excluded.revision,updated_at=excluded.updated_at",
                (user_id, payload.workspace_id, revision, now),
            )
            response = {"code": 0, "msg": "success", "data": {"revision": revision, "items": items, "deleted": deleted}}
            cx.execute("INSERT INTO config_sync_idempotency(user_id,workspace_id,idempotency_key,request_hash,response_json,created_at) VALUES(?,?,?,?,?,?)", (user_id, payload.workspace_id, payload.idempotency_key, request_hash, json.dumps(response, ensure_ascii=False, separators=(",", ":")), now))
            cx.execute("COMMIT")
            return response

    @app.get("/v1/cloud/dashboard")
    def cloud_dashboard(current=Depends(_auth_dependency(db))):
        """Return the Cloud control-plane summary used by the C02 dashboard."""
        user_id = current["id"]
        with db.connect() as cx:
            sessions = cx.execute("SELECT id,title,status,workspace_id,updated_at FROM sessions WHERE user_id=? ORDER BY updated_at DESC", (user_id,)).fetchall()
            approvals = cx.execute("SELECT COUNT(*) FROM approvals WHERE user_id=? AND status='pending'", (user_id,)).fetchone()[0]
            events = cx.execute("SELECT s.title,e.event_type,e.created_at FROM events e JOIN sessions s ON s.id=e.session_id WHERE s.user_id=? ORDER BY e.created_at DESC LIMIT 8", (user_id,)).fetchall()
            devices = cx.execute("SELECT COUNT(*) FROM devices WHERE user_id=? AND revoked_at IS NULL", (user_id,)).fetchone()[0]
            usage = cx.execute("SELECT COALESCE(SUM(total_tokens),0) FROM model_usage_records WHERE user_id=?", (user_id,)).fetchone()[0]
            daily = cx.execute("SELECT COUNT(*) FROM commands WHERE session_id IN (SELECT id FROM sessions WHERE user_id=?) AND created_at>=?", (user_id, int(time.time()) - 86400)).fetchone()[0]
            workspace_rows = cx.execute("SELECT id,display_name FROM workspaces WHERE user_id=? ORDER BY updated_at DESC", (user_id,)).fetchall()
        counts = {status: sum(1 for row in sessions if row["status"] == status) for status in {"running", "pending", "failed", "completed"}}
        workspaces: dict[str, dict[str, Any]] = {row["id"]: {"sessions": 0, "display_name": row["display_name"]} for row in workspace_rows}
        for row in sessions:
            workspace = row["workspace_id"]
            entry = workspaces.setdefault(workspace, {"sessions": 0, "display_name": workspace})
            entry["sessions"] += 1
        storage = sum(Workspace(settings.workspaces_dir / user_id / name).stats()["bytes_used"] for name in workspaces)
        return {"code": 0, "msg": "success", "data": {"session_count": len(sessions), "running_count": counts["running"], "pending_approval_count": approvals, "failed_count": counts["failed"], "device_count": devices, "storage_total": storage, "daily_agent_conversations": daily, "total_tokens": usage, "recent_activity": [dict(row) for row in events], "workspaces": [{"id": name, **summary} for name, summary in workspaces.items()]}}

    @app.get("/v1/cloud/usage")
    def cloud_usage(days: int = 7, current=Depends(_auth_dependency(db))):
        days = max(1, min(days, 31))
        since = int(time.time()) - days * 86400
        with db.connect() as cx:
            rows = cx.execute("SELECT date(created_at,'unixepoch') AS date, COUNT(*) AS conversations, COALESCE(SUM(total_tokens),0) AS total_tokens FROM model_usage_records WHERE user_id=? AND created_at>=? GROUP BY date ORDER BY date", (current["id"], since)).fetchall()
        return {"code": 0, "msg": "success", "data": {"days": [dict(row) for row in rows], "total_tokens": sum(int(row["total_tokens"]) for row in rows)}}

    @app.post("/v1/auth/login")
    def login(payload: LoginRequest, request: Request):
        source = request.client.host if request.client else "unknown"
        identity = payload.account_id or payload.username or ""
        account_key = _login_key("account", source, identity)
        source_key = _login_key("source", source)
        now = int(time.time())
        if _login_rate_limited(db, account_key, now) or _login_rate_limited(db, source_key, now):
            raise HTTPException(429, "too many login attempts", headers={"Retry-After": "60"})
        if not payload.username and not payload.account_id:
            raise HTTPException(400, "username or account_id is required")
        user = _user_by_account_id(db, payload.account_id) if payload.account_id else _user_by_username(db, payload.username or "")
        password_hash = user["password_hash"] if user else _DUMMY_PASSWORD_HASH
        password_valid = verify_password(payload.password, password_hash)
        if not user or user["disabled"] or not password_valid:
            failures = _record_login_failure(db, account_key, now)
            _record_login_failure(db, source_key, now)
            if failures > 5:
                raise HTTPException(429, "too many login attempts", headers={"Retry-After": "60"})
            raise HTTPException(401, "invalid credentials")
        _clear_login_failures(db, account_key)
        _clear_login_failures(db, source_key)
        raw, digest = issue_token()
        now = int(time.time())
        expires_at = token_expiry(settings.token_ttl_seconds)
        with db.connect() as cx:
            token_id = raw[4:].split(".", 1)[0]
            cx.execute("INSERT INTO tokens(id,user_id,digest,expires_at,audience,scopes_json,created_at) VALUES(?,?,?,?,?,?,?)", (token_id, user["id"], digest, expires_at, "cloud-api", '["*"]', now))
        _audit(db, user["id"], "auth.login", user["id"], {"role": user["role"]})
        return {"code": 0, "msg": "success", "data": {"token": raw, "jti": token_id, "user_id": user["id"], "role": user["role"], "audience": "cloud-api", "scopes": ["*"], "expires_at": expires_at}}

    @app.post("/v1/auth/login/password")
    def login_by_email(payload: EmailPasswordLogin, request: Request):
        email = _normalize_email(payload.email)
        source = request.client.host if request.client else "unknown"
        account_key = _login_key("email", source, email)
        source_key = _login_key("source", source)
        now = int(time.time())
        if _login_rate_limited(db, account_key, now) or _login_rate_limited(db, source_key, now):
            raise HTTPException(429, "too many login attempts", headers={"Retry-After": "60"})
        user = _user_by_email(db, email)
        password_hash = user["password_hash"] if user else _DUMMY_PASSWORD_HASH
        if not user or user["disabled"] or not verify_password(payload.password, password_hash):
            failures = _record_login_failure(db, account_key, now)
            _record_login_failure(db, source_key, now)
            if failures > 5:
                raise HTTPException(429, "too many login attempts", headers={"Retry-After": "60"})
            raise HTTPException(401, "invalid credentials")
        _clear_login_failures(db, account_key)
        _clear_login_failures(db, source_key)
        return _login_result(db, settings, user, email_verified=False)

    @app.post("/v1/auth/code/send")
    def send_verification_code(payload: VerificationCodeRequest, request: Request):
        email = _normalize_email(payload.email)
        now = int(time.time())
        source = request.client.host if request.client else "unknown"
        if _login_rate_limited(db, _login_key("otp", email), now, max_failures=3) or _login_rate_limited(db, _login_key("otp-source", source), now, max_failures=10):
            raise HTTPException(429, "too many verification code requests", headers={"Retry-After": "60"})
        code = settings.dev_otp_code if settings.otp_dev_mode else f"{secrets.randbelow(1_000_000):06d}"
        code_hash = _verification_digest(email, payload.purpose, code)
        with db.connect() as cx:
            cx.execute("UPDATE verification_codes SET used_at=? WHERE email=? AND purpose=? AND used_at IS NULL", (now, email, payload.purpose))
            cx.execute("INSERT INTO verification_codes(id,email,purpose,code_hash,expires_at,created_at,request_ip) VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), email, payload.purpose, code_hash, now + 600, now, source))
        response = {"email": email, "purpose": payload.purpose, "expires_in_seconds": 600, "delivery": "development"}
        if settings.otp_dev_mode:
            response["dev_code"] = code
        else:
            try:
                deliver_verification_code(host=settings.smtp_host or "", port=settings.smtp_port, username=settings.smtp_username, password=settings.smtp_password, sender=settings.smtp_sender or "", recipient=email, code=code, purpose=payload.purpose, starttls=settings.smtp_starttls)
            except MailDeliveryError as exc:
                with db.connect() as cx:
                    cx.execute("UPDATE verification_codes SET used_at=? WHERE email=? AND purpose=? AND used_at IS NULL", (now, email, payload.purpose))
                raise HTTPException(503, "verification email delivery failed") from exc
            response["delivery"] = "smtp"
        return {"code": 0, "msg": "success", "data": response}

    @app.post("/v1/auth/login/code")
    def login_by_code(payload: EmailCodeLogin):
        email = _normalize_email(payload.email)
        now = int(time.time())
        digest = _verification_digest(email, "login", payload.code)
        with db.connect() as cx:
            row = cx.execute("SELECT * FROM verification_codes WHERE email=? AND purpose='login' AND used_at IS NULL ORDER BY created_at DESC LIMIT 1", (email,)).fetchone()
            if not row or row["expires_at"] <= now or row["attempts"] >= 5:
                raise HTTPException(401, "invalid or expired verification code")
            if not secrets.compare_digest(row["code_hash"], digest):
                cx.execute("UPDATE verification_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
                raise HTTPException(401, "invalid or expired verification code")
            cx.execute("UPDATE verification_codes SET used_at=? WHERE id=?", (now, row["id"]))
            user = cx.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user or user["disabled"]:
            raise HTTPException(404, "account not found; request access first")
        return _login_result(db, settings, user, email_verified=True)

    @app.post("/v1/auth/password/reset")
    def reset_password(payload: PasswordReset):
        email = _normalize_email(payload.email)
        now = int(time.time())
        digest = _verification_digest(email, "password_reset", payload.code)
        with db.connect() as cx:
            row = cx.execute("SELECT * FROM verification_codes WHERE email=? AND purpose='password_reset' AND used_at IS NULL ORDER BY created_at DESC LIMIT 1", (email,)).fetchone()
            if not row or row["expires_at"] <= now or row["attempts"] >= 5:
                raise HTTPException(401, "invalid or expired verification code")
            if not secrets.compare_digest(row["code_hash"], digest):
                cx.execute("UPDATE verification_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
                raise HTTPException(401, "invalid or expired verification code")
            user = cx.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if not user:
                raise HTTPException(404, "account not found")
            cx.execute("UPDATE verification_codes SET used_at=? WHERE id=?", (now, row["id"]))
            cx.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(payload.password), user["id"]))
            cx.execute("UPDATE tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, user["id"]))
        _audit(db, user["id"], "auth.password.reset", user["id"], {})
        return {"code": 0, "msg": "success", "data": {"email": email, "password_reset": True}}

    @app.post("/v1/access-requests")
    def create_access_request(payload: AccessRequestCreate):
        email = _normalize_email(payload.email)
        if payload.password != payload.confirm_password:
            raise HTTPException(422, "password confirmation does not match")
        with db.connect() as cx:
            if cx.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                raise HTTPException(409, "account already exists")
            pending = cx.execute("SELECT 1 FROM access_requests WHERE email=? AND status='pending'", (email,)).fetchone()
            if pending:
                raise HTTPException(409, "an access request is already pending")
            request_id = str(uuid.uuid4())
            cx.execute("INSERT INTO access_requests(id,email,display_name,reason,password_hash,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)", (request_id, email, payload.display_name.strip(), payload.reason.strip(), hash_password(payload.password), "pending", int(time.time()), int(time.time()) + 7 * 86400))
        return {"code": 0, "msg": "success", "data": {"id": request_id, "email": email, "status": "pending"}}

    @app.post("/v1/admin/invitations")
    def create_invitation(payload: InvitationCreate, current=Depends(_auth_dependency(db, "admin", "admin"))):
        email = _normalize_email(payload.email)
        with db.connect() as cx:
            if cx.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                raise HTTPException(409, "account already exists")
            raw_token = secrets.token_urlsafe(32)
            invitation_id = str(uuid.uuid4())
            now = int(time.time())
            cx.execute("INSERT INTO invitations(id,email,display_name,role,token_hash,status,created_by,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?)", (invitation_id, email, payload.display_name.strip(), "user", hashlib.sha256(raw_token.encode()).hexdigest(), "pending", current["id"], now, now + 7 * 86400))
        if settings.otp_dev_mode:
            _audit(db, current["id"], "invitation.create", invitation_id, {"email": email, "delivery": "development"})
            return {"code": 0, "msg": "success", "data": {"id": invitation_id, "email": email, "status": "pending", "invite_token": raw_token, "expires_at": now + 7 * 86400, "delivery": "development"}}
        invite_url = f"{settings.invite_base_url}/invite/{raw_token}"
        try:
            deliver_invitation(host=settings.smtp_host or "", port=settings.smtp_port, username=settings.smtp_username, password=settings.smtp_password, sender=settings.smtp_sender or "", recipient=email, invite_url=invite_url, starttls=settings.smtp_starttls)
        except MailDeliveryError as exc:
            with db.connect() as cx:
                cx.execute("UPDATE invitations SET status='revoked' WHERE id=? AND status='pending'", (invitation_id,))
            _audit(db, current["id"], "invitation.delivery_failed", invitation_id, {"email": email})
            raise HTTPException(503, "invitation email delivery failed") from exc
        _audit(db, current["id"], "invitation.create", invitation_id, {"email": email, "delivery": "smtp"})
        return {"code": 0, "msg": "success", "data": {"id": invitation_id, "email": email, "status": "pending", "expires_at": now + 7 * 86400, "delivery": "smtp"}}

    @app.get("/v1/admin/invitations")
    def list_invitations(status: str | None = None, current=Depends(_auth_dependency(db, "admin", "admin"))):
        if status is not None and status not in {"pending", "accepted", "expired", "revoked"}:
            raise HTTPException(400, "invalid invitation status")
        now = int(time.time())
        with db.connect() as cx:
            query = "SELECT id,email,display_name,role,status,created_at,expires_at,accepted_at FROM invitations"
            params: tuple[object, ...] = ()
            if status:
                query += " WHERE status=?"
                params = (status,)
            rows = cx.execute(query + " ORDER BY created_at DESC", params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if item["status"] == "pending" and item["expires_at"] <= now:
                item["status"] = "expired"
            result.append(item)
        return {"code": 0, "msg": "success", "data": result}

    @app.post("/v1/invitations/{invite_token}/accept")
    def accept_invitation(invite_token: str, payload: InvitationAccept):
        digest = hashlib.sha256(invite_token.encode()).hexdigest()
        now = int(time.time())
        with db.connect() as cx:
            invitation = cx.execute("SELECT * FROM invitations WHERE token_hash=? AND status='pending'", (digest,)).fetchone()
            if not invitation or invitation["expires_at"] <= now:
                raise HTTPException(404, "invitation is invalid or expired")
            if cx.execute("SELECT 1 FROM users WHERE email=?", (invitation["email"],)).fetchone():
                raise HTTPException(409, "account already exists")
            user_id = str(uuid.uuid4())
            base = re.sub(r"[^A-Za-z0-9_-]+", "", invitation["email"].split("@", 1)[0]) or "user"
            username, suffix = base, 1
            while cx.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                suffix += 1
                username = f"{base}{suffix}"
            cx.execute("INSERT INTO users(id,username,email,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?,?)", (user_id, username, invitation["email"], payload.display_name.strip() or invitation["display_name"], hash_password(payload.password), "user", now))
            cx.execute("UPDATE invitations SET status='accepted',accepted_at=? WHERE id=?", (now, invitation["id"]))
        return {"code": 0, "msg": "success", "data": {"user_id": user_id, "username": username, "email": invitation["email"]}}

    @app.post("/v1/auth/revoke")
    def revoke_token(authorization: Annotated[str | None, Header()] = None):
        parsed = parse_token((authorization or "").removeprefix("Bearer ").removeprefix("bearer ").strip())
        if not parsed:
            raise HTTPException(401, "invalid token")
        token_id, secret = parsed
        with db.connect() as cx:
            result = cx.execute("UPDATE tokens SET revoked_at=? WHERE id=? AND digest=? AND revoked_at IS NULL", (int(time.time()), token_id, token_digest(token_id, secret)))
        if result.rowcount != 1:
            raise HTTPException(401, "invalid token")
        return {"code": 0, "msg": "success", "data": {"revoked": True}}

    @app.get("/v1/auth/me")
    def auth_me(current=Depends(_auth_dependency(db))):
        with db.connect() as cx:
            membership = cx.execute(
                "SELECT organization_id,role FROM organization_members WHERE user_id=? "
                "ORDER BY created_at ASC LIMIT 1",
                (current["id"],),
            ).fetchone()
        return {"code": 0, "msg": "success", "data": {"user_id": current["id"], "username": current["username"], "email": current["email"], "display_name": current["display_name"], "avatar": current["avatar"], "role": current["role"], "audience": current["audience"], "device_id": current["device_id"], "scopes": json.loads(current["scopes_json"]), "expires_at": current["expires_at"], "organization_id": membership["organization_id"] if membership else None, "organization_role": membership["role"] if membership else None}}

    @app.put("/v1/auth/me")
    def update_auth_me(payload: UserProfileUpdate, current=Depends(_auth_dependency(db))):
        changes = {key: value for key, value in payload.model_dump().items() if value is not None}
        if not changes:
            raise HTTPException(400, "no changes supplied")
        if "password" in changes:
            changes["password_hash"] = hash_password(str(changes.pop("password")))
        assignments = ", ".join(f"{key}=?" for key in changes)
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            cx.execute(f"UPDATE users SET {assignments} WHERE id=?", (*changes.values(), current["id"]))
            if "password_hash" in changes:
                cx.execute("UPDATE tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, current["id"]))
                cx.execute("COMMIT")
                _audit(db, current["id"], "auth.profile.password.update", current["id"], {})
                return {"code": 0, "msg": "success", "data": {"password_changed": True}}
            cx.execute("COMMIT")
        _audit(db, current["id"], "auth.profile.update", current["id"], {"fields": sorted(changes)})
        return {"code": 0, "msg": "success", "data": {"display_name": changes.get("display_name", current["display_name"]), "avatar": changes.get("avatar", current["avatar"])}}

    @app.get("/v1/preferences")
    def get_preferences(current=Depends(_auth_dependency(db))):
        with db.connect() as cx:
            user_row = cx.execute("SELECT preferences_json FROM user_preferences WHERE user_id=?", (current["id"],)).fetchone()
            organization = cx.execute("SELECT om.organization_id,op.preferences_json FROM organization_members om LEFT JOIN organization_preferences op ON op.organization_id=om.organization_id WHERE om.user_id=? ORDER BY om.created_at LIMIT 1", (current["id"],)).fetchone()
        user_preferences = json.loads(user_row["preferences_json"]) if user_row else {}
        organization_preferences = json.loads(organization["preferences_json"]) if organization and organization["preferences_json"] else {}
        effective = {**user_preferences, **organization_preferences}
        return {"code": 0, "msg": "success", "data": {**effective, "scopes": {"user": sorted(set(user_preferences) - ORGANIZATION_PREFERENCE_KEYS), "organization": sorted(set(organization_preferences) & ORGANIZATION_PREFERENCE_KEYS), "organization_id": organization["organization_id"] if organization else None}}}

    @app.put("/v1/preferences")
    def update_preferences(payload: PreferencesUpdate, current=Depends(_auth_dependency(db))):
        changes = {key: value for key, value in payload.model_dump().items() if value is not None}
        now = int(time.time())
        with db.connect() as cx:
            existing = cx.execute("SELECT preferences_json FROM user_preferences WHERE user_id=?", (current["id"],)).fetchone()
            preferences = json.loads(existing["preferences_json"]) if existing else {}
            preferences.update(changes)
            cx.execute("INSERT INTO user_preferences(user_id,preferences_json,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET preferences_json=excluded.preferences_json,updated_at=excluded.updated_at", (current["id"], json.dumps(preferences, ensure_ascii=False), now))
        _audit(db, current["id"], "preferences.update", current["id"], {"keys": sorted(changes)})
        return {"code": 0, "msg": "success", "data": preferences}

    @app.get("/v1/admin/organization/preferences")
    def get_organization_preferences(current=Depends(_auth_dependency(db, "admin", "admin"))):
        with db.connect() as cx:
            row = cx.execute("SELECT o.id,o.name,op.preferences_json FROM organizations o LEFT JOIN organization_preferences op ON op.organization_id=o.id JOIN organization_members om ON om.organization_id=o.id WHERE om.user_id=? ORDER BY om.created_at LIMIT 1", (current["id"],)).fetchone()
        if not row:
            raise HTTPException(404, "organization not found")
        return {"code": 0, "msg": "success", "data": {"organization_id": row["id"], "name": row["name"], "preferences": json.loads(row["preferences_json"]) if row["preferences_json"] else {}}}

    @app.put("/v1/admin/organization/preferences")
    def update_organization_preferences(payload: OrganizationPreferencesUpdate, current=Depends(_auth_dependency(db, "admin", "admin"))):
        changes = {key: value for key, value in payload.model_dump().items() if value is not None}
        now = int(time.time())
        with db.connect() as cx:
            organization = cx.execute("SELECT organization_id FROM organization_members WHERE user_id=? ORDER BY created_at LIMIT 1", (current["id"],)).fetchone()
            if not organization:
                raise HTTPException(404, "organization not found")
            existing = cx.execute("SELECT preferences_json FROM organization_preferences WHERE organization_id=?", (organization["organization_id"],)).fetchone()
            preferences = json.loads(existing["preferences_json"]) if existing else {}
            preferences.update(changes)
            cx.execute("INSERT INTO organization_preferences(organization_id,preferences_json,updated_at) VALUES(?,?,?) ON CONFLICT(organization_id) DO UPDATE SET preferences_json=excluded.preferences_json,updated_at=excluded.updated_at", (organization["organization_id"], json.dumps(preferences, ensure_ascii=False), now))
        _audit(db, current["id"], "organization.preferences.update", organization["organization_id"], {"keys": sorted(changes)})
        return {"code": 0, "msg": "success", "data": {"organization_id": organization["organization_id"], "preferences": preferences}}

    @app.get("/v1/admin/organization/memories")
    def get_organization_memories(current=Depends(_auth_dependency(db, "admin", "admin"))):
        with db.connect() as cx:
            organization = cx.execute("SELECT organization_id FROM organization_members WHERE user_id=? ORDER BY created_at LIMIT 1", (current["id"],)).fetchone()
            if not organization:
                raise HTTPException(404, "organization not found")
            rows = cx.execute("SELECT id,organization_id,content,source,created_at,updated_at FROM organization_memories WHERE organization_id=? ORDER BY updated_at DESC,id", (organization["organization_id"],)).fetchall()
        return {"code": 0, "msg": "success", "data": [dict(row) for row in rows]}

    @app.post("/v1/admin/organization/memories")
    def create_organization_memory(payload: OrganizationMemoryCreate, current=Depends(_auth_dependency(db, "admin", "admin"))):
        memory_id = f"orgmem_{uuid.uuid4().hex}"
        now = int(time.time())
        with db.connect() as cx:
            organization = cx.execute("SELECT organization_id FROM organization_members WHERE user_id=? ORDER BY created_at LIMIT 1", (current["id"],)).fetchone()
            if not organization:
                raise HTTPException(404, "organization not found")
            cx.execute("INSERT INTO organization_memories(id,organization_id,content,source,created_at,updated_at) VALUES(?,?,?,?,?,?)", (memory_id, organization["organization_id"], payload.content.strip(), payload.source.strip(), now, now))
        _audit(db, current["id"], "organization.memory.create", memory_id, {"organization_id": organization["organization_id"], "source": payload.source.strip()})
        return {"code": 0, "msg": "success", "data": {"id": memory_id, "organization_id": organization["organization_id"], "content": payload.content.strip(), "source": payload.source.strip(), "created_at": now, "updated_at": now}}

    @app.delete("/v1/admin/organization/memories/{memory_id}")
    def delete_organization_memory(memory_id: str, current=Depends(_auth_dependency(db, "admin", "admin"))):
        with db.connect() as cx:
            organization = cx.execute("SELECT organization_id FROM organization_members WHERE user_id=? ORDER BY created_at LIMIT 1", (current["id"],)).fetchone()
            if not organization:
                raise HTTPException(404, "organization not found")
            result = cx.execute("DELETE FROM organization_memories WHERE id=? AND organization_id=?", (memory_id, organization["organization_id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "organization memory not found")
        _audit(db, current["id"], "organization.memory.delete", memory_id, {"organization_id": organization["organization_id"]})
        return {"code": 0, "msg": "success", "data": {"deleted": True, "id": memory_id}}

    @app.post("/v1/auth/rotate")
    def rotate_token(authorization: Annotated[str | None, Header()] = None):
        current = _authenticate_token(db, authorization)
        if not current:
            raise HTTPException(401, "invalid token")
        parsed = parse_token(authorization[7:].strip())
        assert parsed is not None
        old_id, old_secret = parsed
        raw, digest = issue_token()
        now = int(time.time())
        new_id = raw[4:].split(".", 1)[0]
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            cx.execute("UPDATE tokens SET revoked_at=? WHERE id=? AND digest=?", (now, old_id, token_digest(old_id, old_secret)))
            cx.execute("INSERT INTO tokens(id,user_id,digest,expires_at,audience,scopes_json,device_id,created_at) VALUES(?,?,?,?,?,?,?,?)", (new_id, current["id"], digest, current["expires_at"], current["audience"], current["scopes_json"], current["device_id"], now))
            cx.execute("COMMIT")
        return {"code": 0, "msg": "success", "data": {"token": raw, "jti": new_id, "user_id": current["id"], "role": current["role"], "audience": current["audience"], "device_id": current["device_id"], "scopes": json.loads(current["scopes_json"]), "expires_at": current["expires_at"]}}

    @app.post("/v1/auth/tokens")
    def create_personal_token(payload: PersonalTokenCreate, current=Depends(_auth_dependency(db, required_scope="auth.token", required_audience="cloud-api"))):
        if payload.expires_at is not None and payload.expires_at <= int(time.time()):
            raise HTTPException(422, "expires_at must be in the future")
        raw, digest = issue_token()
        token_id = raw[4:].split(".", 1)[0]
        with db.connect() as cx:
            cx.execute("INSERT INTO tokens(id,user_id,digest,expires_at,audience,scopes_json,created_at) VALUES(?,?,?,?,?,?,?)", (token_id, current["id"], digest, payload.expires_at, "cloud-api", json.dumps(payload.scopes), int(time.time())))
        _audit(db, current["id"], "auth.token.create", token_id, {"scopes": payload.scopes, "permanent": payload.expires_at is None})
        return {"code": 0, "msg": "success", "data": {"token": raw, "jti": token_id, "audience": "cloud-api", "scopes": payload.scopes, "expires_at": payload.expires_at}}

    @app.get("/v1/auth/tokens")
    def list_personal_tokens(current=Depends(_auth_dependency(db, required_scope="auth.token"))):
        with db.connect() as cx:
            rows = cx.execute("SELECT id,audience,device_id,scopes_json,expires_at,revoked_at,created_at FROM tokens WHERE user_id=? ORDER BY created_at DESC", (current["id"],)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "scopes": json.loads(row["scopes_json"])} for row in rows]}

    @app.post("/v1/auth/tokens/{token_id}/revoke")
    def revoke_personal_token(token_id: str, current=Depends(_auth_dependency(db, required_scope="auth.token"))):
        with db.connect() as cx:
            result = cx.execute("UPDATE tokens SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (int(time.time()), token_id, current["id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "active token not found")
        _audit(db, current["id"], "auth.token.revoke", token_id, {})
        return {"code": 0, "msg": "success", "data": {"jti": token_id, "revoked": True}}

    @app.get("/v1/admin/users")
    def list_users(current=Depends(_auth_dependency(db, "admin", "admin"))):
        with db.connect() as cx:
            rows = cx.execute("SELECT id,username,email,display_name,role,disabled,created_at FROM users ORDER BY created_at").fetchall()
        return {"code": 0, "msg": "success", "data": [dict(row) for row in rows]}

    @app.get("/v1/admin/access-requests")
    def list_access_requests(status: str | None = None, current=Depends(_auth_dependency(db, "admin", "admin"))):
        if status is not None and status not in {"pending", "approved", "rejected", "expired"}:
            raise HTTPException(400, "invalid request status")
        with db.connect() as cx:
            if status:
                rows = cx.execute("SELECT id,email,display_name,reason,status,reviewed_by,reviewed_at,created_at,expires_at FROM access_requests WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
            else:
                rows = cx.execute("SELECT id,email,display_name,reason,status,reviewed_by,reviewed_at,created_at,expires_at FROM access_requests ORDER BY created_at DESC").fetchall()
        return {"code": 0, "msg": "success", "data": [dict(row) for row in rows]}

    @app.post("/v1/admin/access-requests/{request_id}/review")
    def review_access_request(request_id: str, payload: AccessRequestReview, current=Depends(_auth_dependency(db, "admin", "admin"))):
        now = int(time.time())
        with db.connect() as cx:
            request_row = cx.execute("SELECT * FROM access_requests WHERE id=?", (request_id,)).fetchone()
            if not request_row:
                raise HTTPException(404, "access request not found")
            if request_row["status"] != "pending":
                raise HTTPException(409, "access request has already been reviewed")
            if payload.status == "rejected":
                cx.execute("UPDATE access_requests SET status='rejected',reviewed_by=?,reviewed_at=? WHERE id=?", (current["id"], now, request_id))
                result = {"id": request_id, "status": "rejected"}
            else:
                base = re.sub(r"[^A-Za-z0-9_-]+", "", request_row["email"].split("@", 1)[0]) or "user"
                username = base
                suffix = 1
                while cx.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                    suffix += 1
                    username = f"{base}{suffix}"
                user_id = str(uuid.uuid4())
                cx.execute("INSERT INTO users(id,username,email,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?,?)", (user_id, username, request_row["email"], request_row["display_name"], request_row["password_hash"], "user", now))
                cx.execute("UPDATE access_requests SET status='approved',reviewed_by=?,reviewed_at=? WHERE id=?", (current["id"], now, request_id))
                result = {"id": request_id, "status": "approved", "user_id": user_id, "username": username}
        _audit(db, current["id"], f"admin.access_request.{payload.status}", request_id, result)
        return {"code": 0, "msg": "success", "data": result}

    @app.get("/v1/admin/audits")
    def list_audits(limit: int = 100, current=Depends(_auth_dependency(db, "admin", "admin"))):
        limit = max(1, min(limit, 500))
        with db.connect() as cx:
            rows = cx.execute("SELECT id,actor_user_id,action,resource_id,metadata_json,created_at FROM audits ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]}

    @app.get("/v1/audits")
    def list_my_audits(limit: int = 20, current=Depends(_auth_dependency(db))):
        limit = max(1, min(limit, 100))
        with db.connect() as cx:
            rows = cx.execute("SELECT id,action,resource_id,metadata_json,created_at FROM audits WHERE actor_user_id=? ORDER BY created_at DESC LIMIT ?", (current["id"], limit)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]}

    @app.post("/v1/admin/users")
    def create_user(payload: UserCreate, current=Depends(_auth_dependency(db, "admin", "admin"))):
        if payload.role != "user":
            raise HTTPException(400, "only user accounts can be created")
        user_id = str(uuid.uuid4())
        try:
            with db.connect() as cx:
                cx.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(?,?,?,?,?)", (user_id, payload.username, hash_password(payload.password), "user", int(time.time())))
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(409, "username already exists") from exc
            raise
        _audit(db, current["id"], "admin.user.create", user_id, {"role": "user"})
        return {"code": 0, "msg": "success", "data": {"id": user_id, "username": payload.username}}

    @app.put("/v1/admin/users/{user_id}")
    def update_user(user_id: str, payload: UserUpdate, current=Depends(_auth_dependency(db, "admin", "admin"))):
        changes: dict[str, object] = {}
        if payload.username is not None:
            changes["username"] = payload.username
        if payload.display_name is not None:
            changes["display_name"] = payload.display_name
        if payload.password is not None:
            changes["password_hash"] = hash_password(payload.password)
        if payload.disabled is not None:
            changes["disabled"] = int(payload.disabled)
        if not changes:
            raise HTTPException(400, "no changes supplied")
        assignments = ", ".join(f"{key}=?" for key in changes)
        try:
            with db.connect() as cx:
                cx.execute("BEGIN IMMEDIATE")
                result = cx.execute(f"UPDATE users SET {assignments} WHERE id=? AND role='user'", (*changes.values(), user_id))
                if result.rowcount == 1 and payload.password is not None:
                    cx.execute("UPDATE tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (int(time.time()), user_id))
                cx.execute("COMMIT")
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(409, "username already exists") from exc
            raise
        if result.rowcount != 1:
            raise HTTPException(404, "user not found")
        _audit(db, current["id"], "admin.user.update", user_id, {"fields": sorted(changes.keys())})
        return {"code": 0, "msg": "success", "data": {"id": user_id, **changes, "password_hash": None}}

    @app.delete("/v1/admin/users/{user_id}")
    def delete_user(user_id: str, current=Depends(_auth_dependency(db, "admin", "admin"))):
        with _user_lock(app, user_id):
            workspace_ids: list[str] = []
            with db.connect() as cx:
                cx.execute("BEGIN IMMEDIATE")
                workspace_ids = [str(row["workspace_id"]) for row in cx.execute("SELECT workspace_id FROM sessions WHERE user_id=?", (user_id,)).fetchall()]
                cx.execute("DELETE FROM share_tokens WHERE user_id=?", (user_id,))
                cx.execute("DELETE FROM grants WHERE user_id=?", (user_id,))
                cx.execute("DELETE FROM pairings WHERE user_id=?", (user_id,))
                cx.execute("DELETE FROM events WHERE session_id IN (SELECT id FROM sessions WHERE user_id=?)", (user_id,))
                cx.execute("DELETE FROM commands WHERE session_id IN (SELECT id FROM sessions WHERE user_id=?)", (user_id,))
                cx.execute("DELETE FROM session_import_requests WHERE user_id=?", (user_id,))
                cx.execute("DELETE FROM session_payloads WHERE session_id IN (SELECT id FROM sessions WHERE user_id=?)", (user_id,))
                cx.execute("DELETE FROM relay_cursors WHERE session_id IN (SELECT id FROM sessions WHERE user_id=?)", (user_id,))
                cx.execute("DELETE FROM session_archives WHERE user_id=?", (user_id,))
                cx.execute("DELETE FROM models WHERE user_id=?", (user_id,))
                cx.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
                cx.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))
                cx.execute("DELETE FROM devices WHERE user_id=?", (user_id,))
                result = cx.execute("DELETE FROM users WHERE id=? AND role='user'", (user_id,))
                cx.execute("COMMIT")
            if result.rowcount != 1:
                raise HTTPException(404, "user not found")
            for workspace_id in workspace_ids:
                shutil.rmtree(settings.workspaces_dir / user_id / workspace_id, ignore_errors=True)
                shutil.rmtree(settings.data_dir / "backups" / user_id / workspace_id, ignore_errors=True)
        _audit(db, current["id"], "admin.user.delete", user_id, {})
        return {"code": 0, "msg": "success", "data": {"deleted": True}}

    @app.post("/v1/models/discover")
    def discover_models(payload: ModelDiscoveryRequest, current=Depends(_auth_dependency(db, required_scope="model.write"))):
        del current
        _validate_provider_discovery_target(payload.base_url)
        if payload.provider not in {"openai-compatible", "openai", "deepseek", "volcengine"}:
            raise HTTPException(422, "provider does not support model discovery")
        headers = {"Accept": "application/json"}
        if payload.api_key:
            headers["Authorization"] = f"Bearer {payload.api_key}"
        endpoint = f"{payload.base_url.rstrip('/')}/models"
        try:
            with httpx.Client(timeout=12.0, trust_env=False, follow_redirects=False) as provider_client:
                response = provider_client.get(endpoint, headers=headers)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(502, f"provider models request failed with HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(502, "provider models request failed") from exc
        raw_items = body.get("data", body) if isinstance(body, dict) else body
        if not isinstance(raw_items, list):
            raise HTTPException(502, "provider models response is invalid")
        models: list[dict[str, str]] = []
        for item in raw_items[:200]:
            if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
                model_id = item["id"].strip()
                models.append({"id": model_id, "model": model_id, "name": str(item.get("name") or model_id)[:128]})
        return {"code": 0, "msg": "success", "data": models}

    @app.get("/v1/models")
    def list_models(current=Depends(_auth_dependency(db, required_scope="model.read"))):
        with db.connect() as cx:
            rows = cx.execute("SELECT id,name,provider,model,base_url,enabled,is_default,created_at,updated_at,api_key_ciphertext FROM models WHERE user_id=? ORDER BY created_at", (current["id"],)).fetchall()
        data = []
        for row in rows:
            credential_status = "not_configured"
            if row["api_key_ciphertext"]:
                if not app.state.settings.secret_key:
                    credential_status = "unavailable"
                else:
                    try:
                        decrypt_secret(row["api_key_ciphertext"], app.state.settings.secret_key)
                        credential_status = "configured"
                    except Exception:
                        credential_status = "unreadable"
            data.append({**{key: row[key] for key in ("id", "name", "provider", "model", "base_url", "enabled", "is_default", "created_at", "updated_at")}, "has_api_key": bool(row["api_key_ciphertext"]), "credential_status": credential_status})
        return {"code": 0, "msg": "success", "data": data}

    @app.post("/v1/models")
    def create_model(payload: ModelCreate, current=Depends(_auth_dependency(db, required_scope="model.write"))):
        if payload.base_url:
            _validate_model_base_url(payload.base_url)
        model_id = str(uuid.uuid4())
        now = int(time.time())
        master_key = app.state.settings.secret_key
        if payload.api_key and not master_key:
            raise HTTPException(503, "NOTEMELD_CLOUD_SECRET_KEY is required for provider credentials")
        try:
            encrypted_key = encrypt_secret(payload.api_key, master_key) if payload.api_key else None
        except RuntimeError as exc:
            raise HTTPException(503, "secret encryption is unavailable") from exc
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            default_row = cx.execute(
                "SELECT api_key_ciphertext FROM models WHERE user_id=? AND enabled=1 AND is_default=1 LIMIT 1",
                (current["id"],),
            ).fetchone()
            has_default = default_row is not None
            # A previous deployment may have used a different encryption key.
            # Do not keep an unreadable default in front of a newly supplied
            # provider credential; that would make every new session fail.
            if has_default and default_row["api_key_ciphertext"] and master_key:
                try:
                    decrypt_secret(default_row["api_key_ciphertext"], master_key)
                except Exception:
                    has_default = False
            # The Cloud Web form intentionally has no hidden default toggle:
            # the first usable provider must become the account default so a
            # newly configured Cloud cannot create sessions with no runner.
            make_default = payload.is_default or not has_default
            if make_default:
                cx.execute("UPDATE models SET is_default=0 WHERE user_id=?", (current["id"],))
            cx.execute("INSERT INTO models(id,user_id,name,provider,model,base_url,api_key_ciphertext,enabled,is_default,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (model_id, current["id"], payload.name, payload.provider, payload.model, payload.base_url, encrypted_key, int(payload.enabled), int(make_default), now, now))
            cx.execute("COMMIT")
        _audit(db, current["id"], "model.create", model_id, {"provider": payload.provider, "model": payload.model, "has_api_key": bool(payload.api_key)})
        return {"code": 0, "msg": "success", "data": {"id": model_id, "name": payload.name, "provider": payload.provider, "model": payload.model, "enabled": payload.enabled, "is_default": make_default, "has_api_key": bool(payload.api_key)}}

    @app.put("/v1/models/{model_id}")
    def update_model(model_id: str, payload: ModelUpdate, current=Depends(_auth_dependency(db, required_scope="model.write"))):
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(400, "no changes supplied")
        if changes.get("base_url"):
            _validate_model_base_url(changes["base_url"])
        master_key = app.state.settings.secret_key
        if "api_key" in changes:
            if changes["api_key"] and not master_key:
                raise HTTPException(503, "NOTEMELD_CLOUD_SECRET_KEY is required for provider credentials")
            try:
                changes["api_key_ciphertext"] = encrypt_secret(changes.pop("api_key"), master_key) if changes["api_key"] else None
            except RuntimeError as exc:
                raise HTTPException(503, "secret encryption is unavailable") from exc
        if "enabled" in changes:
            changes["enabled"] = int(changes["enabled"])
        if "is_default" in changes:
            changes["is_default"] = int(changes["is_default"])
        changes["updated_at"] = int(time.time())
        assignments = ",".join(f"{key}=?" for key in changes)
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            exists = cx.execute("SELECT id FROM models WHERE id=? AND user_id=?", (model_id, current["id"])).fetchone()
            if not exists:
                cx.execute("ROLLBACK")
                raise HTTPException(404, "model not found")
            if changes.get("is_default") == 1:
                cx.execute("UPDATE models SET is_default=0 WHERE user_id=?", (current["id"],))
            cx.execute(f"UPDATE models SET {assignments} WHERE id=? AND user_id=?", (*changes.values(), model_id, current["id"]))
            cx.execute("COMMIT")
        _audit(db, current["id"], "model.update", model_id, {"fields": sorted(changes)})
        return {"code": 0, "msg": "success", "data": {"id": model_id, "updated": True}}

    @app.delete("/v1/models/{model_id}")
    def delete_model(model_id: str, current=Depends(_auth_dependency(db, required_scope="model.write"))):
        with db.connect() as cx:
            result = cx.execute("DELETE FROM models WHERE id=? AND user_id=?", (model_id, current["id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "model not found")
        _audit(db, current["id"], "model.delete", model_id, {})
        return {"code": 0, "msg": "success", "data": {"id": model_id, "deleted": True}}

    _LOCAL_URL_RE = re.compile(r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(/|$)", re.IGNORECASE)

    # Anthropic 无标准公开模型列表接口，用内置常用目录兜底（context_window 200k）
    _ANTHROPIC_CATALOG_MODELS = (
        ("claude-opus-4-1", 200000),
        ("claude-sonnet-4-5", 200000),
        ("claude-3-5-haiku-latest", 200000),
    )

    class _ProviderTestError(Exception):
        """第三方协议测试/发现失败，消息可安全返回给调用者。"""

    def _is_local_url(base_url: str) -> bool:
        return bool(_LOCAL_URL_RE.match(base_url.strip()))

    def _discover_remote_models(protocol: str, base_url: str, api_key: str | None) -> list[dict[str, Any]]:
        """按协议拉取可选模型列表；仅返回 id/name/context_window，不触碰任何持久化。"""
        try:
            if protocol == "anthropic-messages":
                return [
                    {"id": model_id, "name": model_id, "context_window": context_window}
                    for model_id, context_window in _ANTHROPIC_CATALOG_MODELS
                ]
            with httpx.Client(timeout=12.0, trust_env=False, follow_redirects=False) as provider_client:
                if protocol == "ollama":
                    response = provider_client.get(f"{base_url}/api/tags")
                    response.raise_for_status()
                    body = response.json()
                    raw_items = body.get("models") if isinstance(body, dict) else None
                    if not isinstance(raw_items, list):
                        raise _ProviderTestError("ollama 模型列表响应无效")
                    models = []
                    for item in raw_items[:200]:
                        if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
                            model_id = item["name"].strip()
                            models.append({"id": model_id, "name": str(item.get("details", {}).get("family") or model_id)[:128]})
                    return models
                # openai-compatible：GET /models，兼容 data[] 与裸数组
                headers = {"Accept": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                response = provider_client.get(f"{base_url}/models", headers=headers)
                response.raise_for_status()
                body = response.json()
                raw_items = body.get("data", body) if isinstance(body, dict) else body
                if not isinstance(raw_items, list):
                    raise _ProviderTestError("provider models 响应无效")
                models = []
                for item in raw_items[:200]:
                    if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
                        model_id = item["id"].strip()
                        models.append({"id": model_id, "name": str(item.get("name") or model_id)[:128]})
                return models
        except _ProviderTestError:
            raise
        except httpx.HTTPStatusError as exc:
            raise _ProviderTestError(f"请求失败：HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise _ProviderTestError("无法连接或响应无法解析") from exc

    def _test_provider_connection(
        protocol: str, base_url: str, api_key: str | None, model_id: str | None
    ) -> None:
        """按协议做一次最小代价连通性验证；失败统一抛 _ProviderTestError。"""
        try:
            with httpx.Client(timeout=12.0, trust_env=False, follow_redirects=False) as provider_client:
                if protocol == "openai-compatible":
                    if not api_key:
                        raise _ProviderTestError("请先填写 API Key")
                    if model_id:
                        response = provider_client.post(
                            f"{base_url}/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                            json={"model": model_id, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
                        )
                    else:
                        response = provider_client.get(
                            f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"}
                        )
                    response.raise_for_status()
                elif protocol == "anthropic-messages":
                    if not api_key:
                        raise _ProviderTestError("请先填写 API Key")
                    if not model_id:
                        raise _ProviderTestError("请先选择一个 Claude 模型")
                    response = provider_client.post(
                        f"{base_url}/v1/messages",
                        headers={
                            "x-api-key": api_key,
                            "anthropic-version": "2023-06-01",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model_id,
                            "max_tokens": 1,
                            "messages": [{"role": "user", "content": "hi"}],
                        },
                    )
                    response.raise_for_status()
                elif protocol == "ollama":
                    response = provider_client.get(f"{base_url}/api/tags")
                    response.raise_for_status()
                else:  # 防御：未知协议 fail-closed
                    raise _ProviderTestError("不支持的协议")
        except _ProviderTestError:
            raise
        except httpx.HTTPStatusError as exc:
            raise _ProviderTestError(f"请求失败：HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise _ProviderTestError("无法连接到服务地址") from exc

    def _mask_key(value: str | None) -> str | None:
        if not value:
            return None
        return value[:4] + "****" if len(value) <= 4 else value[:3] + "****"

    def _serialize_provider(row: Any, secret_key: str | None) -> dict[str, Any]:
        masked_key: str | None = None
        if row["api_key_ciphertext"]:
            if not secret_key:
                masked_key = "****"
            else:
                try:
                    masked_key = _mask_key(decrypt_secret(row["api_key_ciphertext"], secret_key))
                except Exception:
                    masked_key = "****"
        return {
            "id": row["id"],
            "organization_id": row["organization_id"],
            "display_name": row["display_name"],
            "vendor_id": row["vendor_id"],
            "protocol": row["protocol"],
            "base_url": row["base_url"],
            "auth_type": row["auth_type"],
            "has_api_key": bool(row["api_key_ciphertext"]),
            "api_key_masked": masked_key,
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _serialize_catalog_model(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "organization_id": row["organization_id"],
            "provider_id": row["provider_id"],
            "model_id": row["model_id"] or row["model"],
            "display_name": row["display_name"] or row["model"],
            "context_window": row["context_window"],
            "modalities": row["modalities"],
            "enabled": bool(row["enabled"]),
            "is_default": bool(row["is_default"]),
            "test_status": row["test_status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @app.get("/v1/catalog/providers")
    def catalog_list_providers(current=Depends(_auth_dependency(db, required_scope="model.read"))):
        org_id, _role = _resolve_org(db, current, None, write=False)
        with db.connect() as cx:
            rows = cx.execute(
                "SELECT * FROM providers WHERE organization_id=? ORDER BY created_at ASC, id ASC",
                (org_id,),
            ).fetchall()
            model_rows = cx.execute(
                "SELECT * FROM models WHERE organization_id=? ORDER BY created_at ASC, id ASC",
                (org_id,),
            ).fetchall()
        data = []
        for row in rows:
            provider = _serialize_provider(row, app.state.settings.secret_key)
            provider["models"] = [
                _serialize_catalog_model(m)
                for m in model_rows
                if m["provider_id"] == row["id"]
            ]
            data.append(provider)
        return {"code": 0, "msg": "success", "data": data}

    @app.post("/v1/catalog/providers")
    def catalog_create_provider(
        payload: CatalogProviderCreate,
        current=Depends(_auth_dependency(db, required_scope="model.write")),
    ):
        org_id, _role = _resolve_org(db, current, payload.organization_id, write=True)
        base_url = payload.base_url.rstrip("/")
        _validate_model_base_url(base_url)
        if not _is_local_url(base_url) and not base_url.lower().startswith("https://"):
            raise HTTPException(422, "non-local base_url must use HTTPS")
        provider_id = f"prov_{uuid.uuid4().hex}"
        now = int(time.time())
        secret_key = app.state.settings.secret_key
        api_key = payload.api_key
        if payload.protocol != "ollama" and not api_key:
            raise HTTPException(422, "api_key is required for this protocol")
        if payload.protocol == "ollama" and not _is_local_url(base_url):
            raise HTTPException(422, "ollama provider must target the local host")
        if api_key and not secret_key:
            raise HTTPException(503, "NOTEMELD_CLOUD_SECRET_KEY is required for provider credentials")
        try:
            ciphertext = encrypt_secret(api_key, secret_key) if api_key else None
        except RuntimeError as exc:
            raise HTTPException(503, "secret encryption is unavailable") from exc
        auth_type = "none" if payload.protocol == "ollama" else (
            "x-api-key" if payload.protocol == "anthropic-messages" else "bearer"
        )
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            duplicate = cx.execute(
                "SELECT id FROM providers WHERE organization_id=? AND display_name=?",
                (org_id, payload.display_name),
            ).fetchone()
            if duplicate:
                cx.execute("ROLLBACK")
                raise HTTPException(409, "provider name already exists in this organization")
            cx.execute(
                "INSERT INTO providers(id,organization_id,display_name,vendor_id,protocol,base_url,"
                "auth_type,api_key_ciphertext,created_by,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (provider_id, org_id, payload.display_name, payload.vendor_id, payload.protocol,
                 base_url, auth_type, ciphertext, current["id"], now, now),
            )
            cx.execute("COMMIT")
        _audit(db, current["id"], "catalog.provider.create", provider_id,
                {"organization_id": org_id, "protocol": payload.protocol, "has_api_key": bool(api_key)})
        with db.connect() as cx:
            row = cx.execute("SELECT * FROM providers WHERE id=?", (provider_id,)).fetchone()
        return {"code": 0, "msg": "success", "data": _serialize_provider(row, secret_key)}

    @app.patch("/v1/catalog/providers/{provider_id}")
    def catalog_update_provider(
        provider_id: str,
        payload: CatalogProviderUpdate,
        current=Depends(_auth_dependency(db, required_scope="model.write")),
    ):
        org_id, _role = _resolve_org(db, current, payload.organization_id, write=True)
        changes = payload.model_dump(exclude_unset=True)
        changes.pop("organization_id", None)
        if "api_key" in changes:
            secret_value = changes.pop("api_key")
            if secret_value is not None and str(secret_value).strip():
                secret_key = app.state.settings.secret_key
                if not secret_key:
                    raise HTTPException(503, "NOTEMELD_CLOUD_SECRET_KEY is required for provider credentials")
                try:
                    changes["api_key_ciphertext"] = encrypt_secret(str(secret_value).strip(), secret_key)
                except RuntimeError as exc:
                    raise HTTPException(503, "secret encryption is unavailable") from exc
            elif secret_value is None:
                pass  # 未传/留空：保留原密钥
            else:
                changes["api_key_ciphertext"] = None  # 显式空串：移除密钥
        if "base_url" in changes:
            changes["base_url"] = changes["base_url"].rstrip("/")
            _validate_model_base_url(changes["base_url"])
        if not changes:
            raise HTTPException(400, "no changes supplied")
        changes["updated_at"] = int(time.time())
        assignments = ",".join(f"{key}=?" for key in changes)
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            exists = cx.execute(
                "SELECT id FROM providers WHERE id=? AND organization_id=?",
                (provider_id, org_id),
            ).fetchone()
            if not exists:
                cx.execute("ROLLBACK")
                raise HTTPException(404, "provider not found")
            if "display_name" in changes:
                duplicate = cx.execute(
                    "SELECT id FROM providers WHERE organization_id=? AND display_name=? AND id<>?",
                    (org_id, changes["display_name"], provider_id),
                ).fetchone()
                if duplicate:
                    cx.execute("ROLLBACK")
                    raise HTTPException(409, "provider name already exists in this organization")
            cx.execute(
                f"UPDATE providers SET {assignments} WHERE id=? AND organization_id=?",
                (*changes.values(), provider_id, org_id),
            )
            cx.execute("COMMIT")
        _audit(db, current["id"], "catalog.provider.update", provider_id,
                {"organization_id": org_id, "fields": sorted(changes)})
        with db.connect() as cx:
            row = cx.execute("SELECT * FROM providers WHERE id=?", (provider_id,)).fetchone()
        return {"code": 0, "msg": "success", "data": _serialize_provider(row, app.state.settings.secret_key)}

    @app.delete("/v1/catalog/providers/{provider_id}")
    def catalog_delete_provider(
        provider_id: str, current=Depends(_auth_dependency(db, required_scope="model.write"))
    ):
        org_id, _role = _resolve_org(db, current, None, write=True)
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            # 旧库的 models 表是先建表、后 ALTER 增加 provider_id，没有
            # ON DELETE CASCADE 外键，必须显式删除，否则留下 provider_id
            # 悬空的孤儿模型（JOIN providers 为 NULL，发送即报错）。
            cx.execute(
                "DELETE FROM models WHERE provider_id=? AND organization_id=?",
                (provider_id, org_id),
            )
            result = cx.execute(
                "DELETE FROM providers WHERE id=? AND organization_id=?",
                (provider_id, org_id),
            )
            if result.rowcount != 1:
                cx.execute("ROLLBACK")
                raise HTTPException(404, "provider not found")
            cx.execute("COMMIT")
        _audit(db, current["id"], "catalog.provider.delete", provider_id, {"organization_id": org_id})
        return {"code": 0, "msg": "success", "data": {"id": provider_id, "deleted": True}}

    @app.post("/v1/catalog/providers/{provider_id}/models/batch")
    def catalog_create_models(
        provider_id: str,
        payload: CatalogModelBatch,
        current=Depends(_auth_dependency(db, required_scope="model.write")),
    ):
        org_id, _role = _resolve_org(db, current, payload.organization_id, write=True)
        now = int(time.time())
        created: list[dict[str, Any]] = []
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            provider = cx.execute(
                "SELECT * FROM providers WHERE id=? AND organization_id=?",
                (provider_id, org_id),
            ).fetchone()
            if not provider:
                cx.execute("ROLLBACK")
                raise HTTPException(404, "provider not found")
            existing_ids = {
                row[0]
                for row in cx.execute(
                    "SELECT model_id FROM models WHERE provider_id=?", (provider_id,)
                ).fetchall()
            }
            any_default = any(item.is_default for item in payload.models)
            if any_default:
                cx.execute("UPDATE models SET is_default=0 WHERE organization_id=?", (org_id,))
            else:
                org_has_default = cx.execute(
                    "SELECT id FROM models WHERE organization_id=? AND is_default=1 LIMIT 1", (org_id,)
                ).fetchone()
                if not org_has_default:
                    first = payload.models[0]
                    # 首条模型自动成为组织默认
                    payload.models[0] = first.model_copy(update={"is_default": True})
            for item in payload.models:
                if item.model_id in existing_ids:
                    continue
                row_id = f"mdl_{uuid.uuid4().hex}"
                cx.execute(
                    "INSERT INTO models(id,user_id,name,provider,model,base_url,api_key_ciphertext,"
                    "enabled,is_default,created_at,updated_at,organization_id,provider_id,"
                    "display_name,context_window,modalities,test_status,model_id) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (row_id, provider["created_by"], provider["display_name"], provider["protocol"],
                     item.model_id, provider["base_url"], provider["api_key_ciphertext"],
                     int(item.enabled), int(item.is_default), now, now, org_id, provider_id,
                     item.display_name or item.model_id, item.context_window, item.modalities,
                     "unknown", item.model_id),
                )
                existing_ids.add(item.model_id)
                created.append({"id": row_id})
            cx.execute("COMMIT")
        _audit(db, current["id"], "catalog.models.batch", provider_id,
                {"organization_id": org_id, "model_count": len(created)})
        with db.connect() as cx:
            rows = cx.execute(
                "SELECT * FROM models WHERE organization_id=? AND provider_id=? ORDER BY created_at, id",
                (org_id, provider_id),
            ).fetchall()
        return {"code": 0, "msg": "success",
                "data": [_serialize_catalog_model(row) for row in rows]}

    @app.patch("/v1/catalog/models/{model_row_id}")
    def catalog_update_model(
        model_row_id: str,
        payload: CatalogModelUpdate,
        current=Depends(_auth_dependency(db, required_scope="model.write")),
    ):
        org_id, _role = _resolve_org(db, current, None, write=True)
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            raise HTTPException(400, "no changes supplied")
        if "enabled" in changes:
            changes["enabled"] = int(changes["enabled"])
        if "is_default" in changes:
            changes["is_default"] = int(changes["is_default"])
        changes["updated_at"] = int(time.time())
        assignments = ",".join(f"{key}=?" for key in changes)
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            exists = cx.execute(
                "SELECT id FROM models WHERE id=? AND organization_id=?",
                (model_row_id, org_id),
            ).fetchone()
            if not exists:
                cx.execute("ROLLBACK")
                raise HTTPException(404, "model not found")
            if changes.get("is_default") == 1:
                cx.execute("UPDATE models SET is_default=0 WHERE organization_id=?", (org_id,))
            cx.execute(
                f"UPDATE models SET {assignments} WHERE id=? AND organization_id=?",
                (*changes.values(), model_row_id, org_id),
            )
            cx.execute("COMMIT")
        _audit(db, current["id"], "catalog.model.update", model_row_id,
                {"organization_id": org_id, "fields": sorted(changes)})
        with db.connect() as cx:
            row = cx.execute("SELECT * FROM models WHERE id=?", (model_row_id,)).fetchone()
        return {"code": 0, "msg": "success", "data": _serialize_catalog_model(row)}

    @app.delete("/v1/catalog/models/{model_row_id}")
    def catalog_delete_model(
        model_row_id: str, current=Depends(_auth_dependency(db, required_scope="model.write"))
    ):
        org_id, _role = _resolve_org(db, current, None, write=True)
        with db.connect() as cx:
            result = cx.execute(
                "DELETE FROM models WHERE id=? AND organization_id=?",
                (model_row_id, org_id),
            )
        if result.rowcount != 1:
            raise HTTPException(404, "model not found")
        _audit(db, current["id"], "catalog.model.delete", model_row_id, {"organization_id": org_id})
        return {"code": 0, "msg": "success", "data": {"id": model_row_id, "deleted": True}}

    @app.post("/v1/catalog/models/{model_row_id}/default")
    def catalog_set_default_model(
        model_row_id: str, current=Depends(_auth_dependency(db, required_scope="model.write"))
    ):
        org_id, _role = _resolve_org(db, current, None, write=True)
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            exists = cx.execute(
                "SELECT id FROM models WHERE id=? AND organization_id=? AND enabled=1",
                (model_row_id, org_id),
            ).fetchone()
            if not exists:
                cx.execute("ROLLBACK")
                raise HTTPException(404, "model not found or disabled")
            cx.execute("UPDATE models SET is_default=0 WHERE organization_id=?", (org_id,))
            cx.execute("UPDATE models SET is_default=1,updated_at=? WHERE id=?", (now, model_row_id))
            cx.execute("COMMIT")
        _audit(db, current["id"], "catalog.model.default", model_row_id, {"organization_id": org_id})
        with db.connect() as cx:
            row = cx.execute("SELECT * FROM models WHERE id=?", (model_row_id,)).fetchone()
        return {"code": 0, "msg": "success", "data": _serialize_catalog_model(row)}

    @app.post("/v1/catalog/discover")
    def catalog_discover(
        payload: CatalogDiscoverRequest,
        current=Depends(_auth_dependency(db, required_scope="model.read")),
    ):
        _resolve_org(db, current, payload.organization_id, write=False)
        base_url = payload.base_url.rstrip("/")
        protocol = payload.protocol
        _validate_model_base_url(base_url)
        if protocol == "ollama":
            if not _is_local_url(base_url):
                raise HTTPException(422, "ollama discovery must target the local host")
        else:
            _validate_provider_discovery_target(base_url)
        return {"code": 0, "msg": "success",
                "data": _discover_remote_models(protocol, base_url, payload.api_key)}

    @app.post("/v1/catalog/test-connection")
    def catalog_test_connection(
        payload: CatalogTestConnectionRequest,
        current=Depends(_auth_dependency(db, required_scope="model.read")),
    ):
        _resolve_org(db, current, payload.organization_id, write=False)
        base_url = payload.base_url.rstrip("/")
        protocol = payload.protocol
        _validate_model_base_url(base_url)
        if protocol == "ollama":
            if not _is_local_url(base_url):
                raise HTTPException(422, "ollama test must target the local host")
        else:
            _validate_provider_discovery_target(base_url)
        try:
            _test_provider_connection(protocol, base_url, payload.api_key, payload.model_id)
        except _ProviderTestError as exc:
            return {"code": 0, "msg": "success",
                    "data": {"ok": False, "status": "failed", "message": str(exc)}}
        return {"code": 0, "msg": "success",
                "data": {"ok": True, "status": "ok", "message": "连接成功"}}

    @app.post("/v1/devices")
    @app.post("/v1/devices/register")
    def register_device(payload: DeviceCreate, current=Depends(_auth_dependency(db, required_scope="device.write", required_audience="cloud-api"))):
        if payload.public_key is not None and not _valid_public_key(payload.public_key):
            raise HTTPException(422, "public_key must be URL-safe base64 Ed25519 key")
        now = int(time.time())
        with db.connect() as cx:
            try:
                cx.execute("INSERT INTO devices(id,user_id,public_key,platform,display_name,connectivity_json,last_seen_at,created_at) VALUES(?,?,?,?,?,?,?,?)", (payload.device_id, current["id"], payload.public_key, payload.platform, payload.display_name, json.dumps({"lan_endpoints": payload.lan_endpoints}, separators=(",", ":")), now, now))
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    existing = cx.execute("SELECT user_id,revoked_at,public_key FROM devices WHERE id=?", (payload.device_id,)).fetchone()
                    if not existing or existing["user_id"] != current["id"]:
                        raise HTTPException(409, "device already registered") from exc
                    public_key = payload.public_key or existing["public_key"]
                    cx.execute("UPDATE devices SET public_key=?,platform=?,display_name=?,connectivity_json=?,revoked_at=NULL,last_seen_at=? WHERE id=? AND user_id=?", (public_key, payload.platform, payload.display_name, json.dumps({"lan_endpoints": payload.lan_endpoints}, separators=(",", ":")), now, payload.device_id, current["id"]))
                    if payload.public_key and existing["public_key"] != payload.public_key:
                        cx.execute("UPDATE tokens SET revoked_at=? WHERE user_id=? AND device_id=? AND revoked_at IS NULL", (now, current["id"], payload.device_id))
                        app.state.device_proofs.pop((current["id"], payload.device_id), None)
                else:
                    raise
        return {"code": 0, "msg": "success", "data": {"device_id": payload.device_id}}

    @app.get("/v1/devices")
    def list_devices(current=Depends(_auth_dependency(db, required_scope="device.read"))):
        with db.connect() as cx:
            rows = cx.execute("SELECT id,public_key,platform,display_name,connectivity_json,revoked_at,last_seen_at,created_at FROM devices WHERE user_id=? AND revoked_at IS NULL ORDER BY created_at", (current["id"],)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["connectivity"] = json.loads(item.pop("connectivity_json") or "{}")
            item["online"] = bool(item["last_seen_at"] and int(time.time()) - int(item["last_seen_at"]) <= settings.device_online_ttl_seconds and not item["revoked_at"])
            result.append(item)
        return {"code": 0, "msg": "success", "data": result}

    @app.get("/v1/devices/{device_id}/permissions")
    def get_device_permissions(device_id: str, current=Depends(_auth_dependency(db, required_scope="device.read"))):
        _require_bound_device(current, device_id)
        with db.connect() as cx:
            row = cx.execute("SELECT connectivity_json FROM devices WHERE id=? AND user_id=?", (device_id, current["id"])).fetchone()
        if not row:
            raise HTTPException(404, "device not found")
        connectivity = json.loads(row["connectivity_json"] or "{}")
        return {"code": 0, "msg": "success", "data": connectivity.get("permissions", {"workspace_read": True, "remote_execute": False, "session_read": True, "artifact_download": True, "approval_required": True})}

    @app.put("/v1/devices/{device_id}/permissions")
    def update_device_permissions(device_id: str, payload: DevicePermissionsUpdate, current=Depends(_auth_dependency(db, required_scope="device.write"))):
        _require_bound_device(current, device_id)
        with db.connect() as cx:
            row = cx.execute("SELECT connectivity_json FROM devices WHERE id=? AND user_id=? AND revoked_at IS NULL", (device_id, current["id"])).fetchone()
            if not row:
                raise HTTPException(404, "active device not found")
            connectivity = json.loads(row["connectivity_json"] or "{}")
            permissions = payload.model_dump()
            connectivity["permissions"] = permissions
            cx.execute("UPDATE devices SET connectivity_json=? WHERE id=? AND user_id=?", (json.dumps(connectivity, separators=(",", ":")), device_id, current["id"]))
        _audit(db, current["id"], "device.permissions.update", device_id, {"permissions": permissions})
        return {"code": 0, "msg": "success", "data": permissions}

    @app.post("/v1/devices/{device_id}/revoke")
    @app.delete("/v1/devices/{device_id}")
    def revoke_device(device_id: str, current=Depends(_auth_dependency(db, required_scope="device.write"))):
        _require_bound_device(current, device_id)
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            result = cx.execute("UPDATE devices SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (now, device_id, current["id"]))
            if result.rowcount == 1:
                cx.execute("UPDATE grants SET revoked_at=? WHERE user_id=? AND (controller_device_id=? OR host_device_id=?) AND revoked_at IS NULL", (now, current["id"], device_id, device_id))
                cx.execute("UPDATE tokens SET revoked_at=? WHERE user_id=? AND device_id=? AND revoked_at IS NULL", (now, current["id"], device_id))
            cx.execute("COMMIT")
        if result.rowcount != 1:
            raise HTTPException(404, "active device not found")
        app.state.device_proofs.pop((current["id"], device_id), None)
        _audit(db, current["id"], "device.revoke", device_id, {"grants_revoked": True, "device_tokens_revoked": True})
        return {"code": 0, "msg": "success", "data": {"device_id": device_id, "revoked": True}}

    @app.post("/v1/devices/{device_id}/rotate-key")
    def rotate_device_key(device_id: str, payload: DeviceKeyRotate, current=Depends(_auth_dependency(db, required_scope="device.write"))):
        _require_bound_device(current, device_id)
        if not _valid_public_key(payload.public_key):
            raise HTTPException(422, "public_key must be URL-safe base64 Ed25519 key")
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            result = cx.execute("UPDATE devices SET public_key=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (payload.public_key, device_id, current["id"]))
            if result.rowcount == 1:
                cx.execute("UPDATE tokens SET revoked_at=? WHERE user_id=? AND device_id=? AND revoked_at IS NULL", (now, current["id"], device_id))
            cx.execute("COMMIT")
        if result.rowcount != 1:
            raise HTTPException(404, "active device not found")
        app.state.device_proofs.pop((current["id"], device_id), None)
        _audit(db, current["id"], "device.key.rotate", device_id, {"device_tokens_revoked": True})
        return {"code": 0, "msg": "success", "data": {"device_id": device_id, "rotated": True}}

    @app.post("/v1/devices/{device_id}/heartbeat")
    def device_heartbeat(device_id: str, payload: DeviceHeartbeat | None = None, current=Depends(_auth_dependency(db, required_scope="device.write"))):
        _require_bound_device(current, device_id)
        now = int(time.time())
        with db.connect() as cx:
            if payload and payload.lan_endpoints is not None:
                result = cx.execute("UPDATE devices SET last_seen_at=?,connectivity_json=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (now, json.dumps({"lan_endpoints": payload.lan_endpoints}, separators=(",", ":")), device_id, current["id"]))
            else:
                result = cx.execute("UPDATE devices SET last_seen_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (now, device_id, current["id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "active device not found")
        return {"code": 0, "msg": "success", "data": {"device_id": device_id, "last_seen_at": now}}

    @app.post("/v1/devices/{device_id}/challenge")
    def device_challenge(device_id: str, current=Depends(_auth_dependency(db, required_scope="device.read"))):
        _require_bound_device(current, device_id)
        with db.connect() as cx:
            row = cx.execute("SELECT public_key FROM devices WHERE id=? AND user_id=? AND revoked_at IS NULL", (device_id, current["id"])).fetchone()
        if not row or not row["public_key"]:
            raise HTTPException(409, "active device public key is required")
        challenge = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + 300
        app.state.device_challenges[challenge] = (current["id"], device_id, expires_at)
        return {"code": 0, "msg": "success", "data": {"device_id": device_id, "challenge": challenge, "expires_at": expires_at}}

    @app.post("/v1/devices/{device_id}/challenge/verify")
    def verify_device_challenge(device_id: str, payload: DeviceProof, current=Depends(_auth_dependency(db, required_scope="device.write"))):
        _require_bound_device(current, device_id)
        challenge_data = app.state.device_challenges.pop(payload.challenge, None)
        now = int(time.time())
        if not challenge_data or challenge_data[0] != current["id"] or challenge_data[1] != device_id or challenge_data[2] <= now:
            raise HTTPException(401, "invalid device challenge")
        with db.connect() as cx:
            row = cx.execute("SELECT public_key FROM devices WHERE id=? AND user_id=? AND revoked_at IS NULL", (device_id, current["id"])).fetchone()
        if not row or not row["public_key"] or not _verify_device_proof(row["public_key"], payload.signature, payload.challenge, device_id):
            raise HTTPException(401, "invalid device proof")
        app.state.device_proofs[(current["id"], device_id)] = now + 300
        return {"code": 0, "msg": "success", "data": {"device_id": device_id, "verified_until": now + 300}}

    @app.post("/v1/devices/{device_id}/token")
    def create_device_token(device_id: str, payload: DeviceTokenCreate, current=Depends(_auth_dependency(db, required_scope="device.write", required_audience="cloud-api"))):
        now = int(time.time())
        if app.state.device_proofs.get((current["id"], device_id), 0) <= now:
            raise HTTPException(403, "recent device proof is required")
        with db.connect() as cx:
            device = cx.execute("SELECT id FROM devices WHERE id=? AND user_id=? AND revoked_at IS NULL", (device_id, current["id"])).fetchone()
        if not device:
            raise HTTPException(404, "active device not found")
        expires_at = now + payload.expires_in_seconds
        if current["expires_at"] is not None:
            expires_at = min(expires_at, int(current["expires_at"]))
        if expires_at <= now:
            raise HTTPException(401, "account token expired")
        raw, digest = issue_token()
        token_id = raw[4:].split(".", 1)[0]
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            cx.execute("INSERT INTO tokens(id,user_id,digest,expires_at,audience,scopes_json,device_id,created_at) VALUES(?,?,?,?,?,?,?,?)", (token_id, current["id"], digest, expires_at, "device-api", json.dumps(payload.scopes), device_id, now))
            if payload.revoke_source_token:
                revoked = cx.execute("UPDATE tokens SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (now, current["token_id"]))
                if revoked.rowcount != 1:
                    cx.execute("ROLLBACK")
                    raise HTTPException(409, "source token changed during exchange")
            cx.execute("COMMIT")
        _audit(db, current["id"], "device.token.create", device_id, {"jti": token_id, "scopes": payload.scopes, "expires_at": expires_at, "source_token_revoked": payload.revoke_source_token})
        return {"code": 0, "msg": "success", "data": {"token": raw, "jti": token_id, "user_id": current["id"], "device_id": device_id, "audience": "device-api", "scopes": payload.scopes, "expires_at": expires_at, "source_token_revoked": payload.revoke_source_token}}

    @app.post("/v1/pairings/start")
    def start_pairing(current=Depends(_auth_dependency(db, required_scope="device.write", required_audience="cloud-api"))):
        raw_code = f"{secrets.token_urlsafe(9)}"
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("INSERT INTO pairings(id,user_id,code_hash,expires_at,status,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), current["id"], hashlib.sha256(raw_code.encode()).hexdigest(), now + 300, "pending", now))
        return {"code": 0, "msg": "success", "data": {"code": raw_code, "expires_at": now + 300}}

    @app.post("/v1/pairings/confirm")
    def confirm_pairing(payload: PairingConfirm, current=Depends(_auth_dependency(db, required_scope="device.write", required_audience="cloud-api"))):
        if payload.public_key is not None and not _valid_public_key(payload.public_key):
            raise HTTPException(422, "public_key must be URL-safe base64 Ed25519 key")
        digest = hashlib.sha256(payload.code.encode()).hexdigest()
        now = int(time.time())
        model_bundle: list[dict[str, Any]] = []
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            pairing = cx.execute("SELECT * FROM pairings WHERE code_hash=? AND status='pending' AND expires_at>? AND user_id=?", (digest, now, current["id"])).fetchone()
            if not pairing:
                cx.execute("ROLLBACK")
                raise HTTPException(400, "pairing code expired or invalid")
            existing_device = cx.execute("SELECT user_id,public_key FROM devices WHERE id=?", (payload.device_id,)).fetchone()
            if existing_device and existing_device["user_id"] != current["id"]:
                cx.execute("ROLLBACK")
                raise HTTPException(409, "device id is already registered to another account")
            if existing_device:
                public_key = payload.public_key or existing_device["public_key"]
                cx.execute("UPDATE devices SET public_key=?,platform=?,display_name=?,revoked_at=NULL,last_seen_at=? WHERE id=? AND user_id=?", (public_key, payload.platform, payload.display_name, now, payload.device_id, current["id"]))
                if payload.public_key and existing_device["public_key"] != payload.public_key:
                    cx.execute("UPDATE tokens SET revoked_at=? WHERE user_id=? AND device_id=? AND revoked_at IS NULL", (now, current["id"], payload.device_id))
                    app.state.device_proofs.pop((current["id"], payload.device_id), None)
            else:
                cx.execute("INSERT INTO devices(id,user_id,public_key,platform,display_name,last_seen_at,created_at) VALUES(?,?,?,?,?,?,?)", (payload.device_id, current["id"], payload.public_key, payload.platform, payload.display_name, now, now))
            cx.execute("UPDATE pairings SET status='confirmed',device_id=? WHERE id=?", (payload.device_id, pairing["id"]))
            # 安全红线：配对仅下发模型元数据（model_id/model/provider/base_url/protocol），
            # 绝不下发 api_key/ciphertext/credential_status；客户端选定后回传 model_id。
            models = cx.execute(
                "SELECT m.model_id AS catalog_model_id,m.display_name AS catalog_display,m.model AS legacy_model,"
                "m.name AS legacy_name,m.provider AS legacy_provider,m.base_url AS legacy_base_url,"
                "p.display_name AS provider_name,p.protocol AS protocol,p.base_url AS provider_base_url "
                "FROM models m LEFT JOIN providers p ON p.id=m.provider_id "
                "WHERE m.enabled=1 AND ("
                "m.organization_id IN (SELECT organization_id FROM organization_members WHERE user_id=?)"
                " OR (m.organization_id IS NULL AND m.user_id=?))"
                " ORDER BY m.is_default DESC,m.created_at ASC",
                (current["id"], current["id"]),
            ).fetchall()
            for model in models:
                model_id = model["catalog_model_id"] or model["legacy_model"]
                model_bundle.append({
                    "model_id": model_id,
                    "model": model["catalog_display"] or model["legacy_model"],
                    "provider": model["provider_name"] or model["legacy_name"],
                    "base_url": model["provider_base_url"] if model["provider_base_url"] is not None else model["legacy_base_url"],
                    "protocol": model["protocol"] or "openai-compatible",
                })
            cx.execute("COMMIT")
        _audit(db, current["id"], "device.pairing.confirm", payload.device_id, {"model_count": len(model_bundle), "models_metadata_sent": len(model_bundle)})
        return {"code": 0, "msg": "success", "data": {"device_id": payload.device_id, "paired": True, "models": model_bundle}}

    @app.post("/v1/grants")
    def create_grant(payload: GrantCreate, current=Depends(_auth_dependency(db, required_scope="grant.write", required_audience="cloud-api"))):
        if payload.role == "super_admin" and current["role"] != "admin":
            raise HTTPException(403, "permission denied")
        elevated_scopes = {"dangerous.approve", "approval.remote.resolve", "session.permission.manage", "session.full_access", "full_access"}
        if payload.role != "super_admin" and elevated_scopes.intersection(payload.scopes):
            raise HTTPException(403, "elevated scopes require a super_admin grant")
        if payload.expires_at is not None and payload.expires_at <= int(time.time()):
            raise HTTPException(422, "expires_at must be in the future")
        with db.connect() as cx:
            devices = cx.execute("SELECT id,public_key FROM devices WHERE user_id=? AND id IN (?,?) AND revoked_at IS NULL", (current["id"], payload.controller_device_id, payload.host_device_id)).fetchall()
        if len(devices) != 2:
            raise HTTPException(404, "active devices not found")
        if any(not device["public_key"] for device in devices):
            raise HTTPException(409, "device public key is required before granting remote control")
        grant_id = str(uuid.uuid4())
        with db.connect() as cx:
            cx.execute("INSERT INTO grants(id,user_id,controller_device_id,host_device_id,role,scopes_json,workspace_refs_json,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (grant_id, current["id"], payload.controller_device_id, payload.host_device_id, payload.role, json.dumps(payload.scopes), json.dumps(payload.workspace_refs), payload.expires_at, int(time.time())))
        _audit(db, current["id"], "grant.create", grant_id, {"role": payload.role, "scopes": payload.scopes})
        return {"code": 0, "msg": "success", "data": {"grant_id": grant_id, "role": payload.role, "expires_at": payload.expires_at}}

    @app.get("/v1/grants")
    def list_grants(current=Depends(_auth_dependency(db, required_scope="grant.read"))):
        with db.connect() as cx:
            rows = cx.execute("SELECT id,controller_device_id,host_device_id,role,scopes_json,workspace_refs_json,expires_at,revoked_at,created_at FROM grants WHERE user_id=? ORDER BY created_at DESC", (current["id"],)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "scopes": json.loads(row["scopes_json"]), "workspace_refs": json.loads(row["workspace_refs_json"])} for row in rows]}

    @app.post("/v1/lan/authorize")
    def authorize_lan_peer(
        payload: LanAuthorizationRequest,
        current=Depends(
            _auth_dependency(
                db,
                required_scope="grant.read",
                required_audience="device-api",
            )
        ),
    ):
        if current["device_id"] != payload.host_device_id:
            raise HTTPException(403, "LAN authorization requires the bound host device")
        now = int(time.time())
        with db.connect() as cx:
            row = cx.execute(
                "SELECT g.id AS grant_id,g.role,g.scopes_json,"
                "g.workspace_refs_json,g.expires_at,s.workspace_id,"
                "s.authority_epoch,controller.public_key AS controller_public_key "
                "FROM grants g "
                "JOIN sessions s ON s.user_id=g.user_id AND s.id=? "
                "AND s.kind='device_remote' "
                "JOIN devices controller ON controller.id=g.controller_device_id "
                "AND controller.user_id=g.user_id AND controller.revoked_at IS NULL "
                "JOIN devices host ON host.id=g.host_device_id "
                "AND host.user_id=g.user_id AND host.revoked_at IS NULL "
                "WHERE g.user_id=? AND g.controller_device_id=? "
                "AND g.host_device_id=? AND g.revoked_at IS NULL "
                "AND (g.expires_at IS NULL OR g.expires_at>?) "
                "ORDER BY g.created_at DESC LIMIT 1",
                (
                    payload.session_id,
                    current["id"],
                    payload.controller_device_id,
                    payload.host_device_id,
                    now,
                ),
            ).fetchone()
        if not row or not row["controller_public_key"]:
            raise HTTPException(403, "active LAN control grant not found")
        workspace_refs = json.loads(row["workspace_refs_json"])
        if workspace_refs and row["workspace_id"] not in workspace_refs:
            raise HTTPException(403, "workspace is outside the LAN control grant")
        scopes = set(json.loads(row["scopes_json"]))
        if row["role"] == "super_admin":
            scopes.update({"message.send", "context.select", "model.select", "tool.invoke", "event.receive"})
        # Keep a one-second boundary margin so a caller observing the value
        # immediately before this request cannot see a window longer than the
        # advertised 60 seconds when the wall clock crosses an integer second.
        valid_until = min(
            int(row["expires_at"]) if row["expires_at"] is not None else now + 59,
            now + 59,
        )
        result = {
            "session_id": payload.session_id,
            "controller_device_id": payload.controller_device_id,
            "host_device_id": payload.host_device_id,
            "controller_public_key": row["controller_public_key"],
            "grant_id": row["grant_id"],
            "role": row["role"],
            "scopes": sorted(scopes),
            "workspace_id": row["workspace_id"],
            "authority_epoch": row["authority_epoch"],
            "valid_until": valid_until,
            "ttl_seconds": valid_until - now,
        }
        _audit(
            db,
            current["id"],
            "lan.authorize",
            row["grant_id"],
            {
                "session_id": payload.session_id,
                "controller_device_id": payload.controller_device_id,
                "host_device_id": payload.host_device_id,
                "valid_until": valid_until,
            },
        )
        return {"code": 0, "msg": "success", "data": result}

    @app.post("/v1/grants/{grant_id}/revoke")
    @app.delete("/v1/grants/{grant_id}")
    def revoke_grant(grant_id: str, current=Depends(_auth_dependency(db, required_scope="grant.write", required_audience="cloud-api"))):
        with db.connect() as cx:
            result = cx.execute("UPDATE grants SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (int(time.time()), grant_id, current["id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "active grant not found")
        _audit(db, current["id"], "grant.revoke", grant_id, {})
        return {"code": 0, "msg": "success", "data": {"grant_id": grant_id, "revoked": True}}

    @app.post("/v1/share-tokens")
    def create_share_token(payload: ShareTokenCreate, current=Depends(_auth_dependency(db, required_scope="share.write"))):
        _owned_session(db, payload.session_id, current["id"])
        if payload.role == "super_admin" and current["role"] != "admin":
            raise HTTPException(403, "permission denied")
        if payload.role == "viewer" and "message.send" in payload.scopes:
            raise HTTPException(422, "viewer share token cannot send messages")
        if payload.expires_at is not None and payload.expires_at <= int(time.time()):
            raise HTTPException(422, "expires_at must be in the future")
        raw = "nms_" + secrets.token_urlsafe(32)
        token_id = str(uuid.uuid4())
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("INSERT INTO share_tokens(id,user_id,session_id,token_digest,role,scopes_json,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?)", (token_id, current["id"], payload.session_id, hashlib.sha256(raw.encode()).hexdigest(), payload.role, json.dumps(payload.scopes), payload.expires_at, now))
        _audit(db, current["id"], "share_token.create", token_id, {"session_id": payload.session_id, "role": payload.role, "scopes": payload.scopes, "permanent": payload.expires_at is None})
        return {"code": 0, "msg": "success", "data": {"id": token_id, "token": raw, "session_id": payload.session_id, "role": payload.role, "scopes": payload.scopes, "expires_at": payload.expires_at}}

    @app.get("/v1/share-tokens")
    def list_share_tokens(session_id: str | None = None, current=Depends(_auth_dependency(db, required_scope="share.read"))):
        with db.connect() as cx:
            if session_id is None:
                rows = cx.execute("SELECT id,session_id,role,scopes_json,expires_at,revoked_at,created_at FROM share_tokens WHERE user_id=? ORDER BY created_at DESC, rowid ASC", (current["id"],)).fetchall()
            else:
                rows = cx.execute("SELECT id,session_id,role,scopes_json,expires_at,revoked_at,created_at FROM share_tokens WHERE user_id=? AND session_id=? ORDER BY created_at DESC, rowid ASC", (current["id"], session_id)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "scopes": json.loads(row["scopes_json"])} for row in rows]}

    @app.post("/v1/share-tokens/{token_id}/revoke")
    def revoke_share_token(token_id: str, current=Depends(_auth_dependency(db, required_scope="share.write"))):
        with db.connect() as cx:
            result = cx.execute("UPDATE share_tokens SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (int(time.time()), token_id, current["id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "active share token not found")
        _audit(db, current["id"], "share_token.revoke", token_id, {})
        return {"code": 0, "msg": "success", "data": {"id": token_id, "revoked": True}}

    @app.post("/v1/sessions")
    @app.post("/v1/cloud/sessions")
    def create_session(payload: SessionCreate, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        session_id = str(uuid.uuid4())
        now = int(time.time())
        resolved_workspace_id = payload.workspace_id
        resolved_model_id = payload.model_id
        workspace_uses_preference = payload.workspace_id in (None, "", "default")
        if not resolved_model_id or workspace_uses_preference:
            with db.connect() as cx:
                user_preferences_row = cx.execute("SELECT preferences_json FROM user_preferences WHERE user_id=?", (current["id"],)).fetchone()
                organization_row = cx.execute("SELECT op.preferences_json FROM organization_members om JOIN organization_preferences op ON op.organization_id=om.organization_id WHERE om.user_id=? ORDER BY om.created_at LIMIT 1", (current["id"],)).fetchone()
            user_preferences = json.loads(user_preferences_row["preferences_json"]) if user_preferences_row else {}
            organization_preferences = json.loads(organization_row["preferences_json"]) if organization_row else {}
            effective_preferences = {**user_preferences, **organization_preferences}
            if workspace_uses_preference:
                resolved_workspace_id = effective_preferences.get("default_workspace") or resolved_workspace_id
            resolved_model_id = resolved_model_id or effective_preferences.get("default_model")
        if not resolved_model_id:
            # A newly configured Cloud model is the user's runtime default even
            # when the non-sensitive preference snapshot has not been synced
            # yet.  Keeping this fallback server-side prevents a session from
            # silently using the process-wide (often uncredentialed) provider.
            with db.connect() as cx:
                default_model = cx.execute(
                    "SELECT m.id FROM models m "
                    "LEFT JOIN organization_members om ON om.organization_id=m.organization_id AND om.user_id=? "
                    "WHERE m.enabled=1 AND m.is_default=1 AND ("
                    "om.user_id IS NOT NULL OR (m.organization_id IS NULL AND m.user_id=?))"
                    " ORDER BY m.created_at LIMIT 1",
                    (current["id"], current["id"]),
                ).fetchone()
            resolved_model_id = default_model["id"] if default_model else None
        if resolved_model_id:
            with db.connect() as cx:
                # 组织目录对 member 只读但可用；旧私有行仅本人可用
                model = cx.execute(
                    "SELECT m.id FROM models m "
                    "LEFT JOIN organization_members om ON om.organization_id=m.organization_id AND om.user_id=? "
                    "WHERE m.id=? AND m.enabled=1 AND ("
                    "om.user_id IS NOT NULL OR (m.organization_id IS NULL AND m.user_id=?))",
                    (current["id"], resolved_model_id, current["id"]),
                ).fetchone()
            if not model:
                if payload.model_id:
                    raise HTTPException(404, "enabled model not found")
                resolved_model_id = None
        Workspace(settings.workspaces_dir / current["id"] / resolved_workspace_id)
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            cx.execute("INSERT INTO sessions(id,user_id,kind,title,workspace_id,status,model_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (session_id, current["id"], payload.kind, payload.title, resolved_workspace_id, "idle", resolved_model_id, now, now))
            cx.execute("COMMIT")
        return {"code": 0, "msg": "success", "data": {"id": session_id, "kind": payload.kind, "workspace_id": resolved_workspace_id, "model_id": resolved_model_id}}

    @app.post("/v1/cloud/sessions/import")
    def import_session(payload: SessionImport, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        if not _active_device_owned(db, payload.source_device_id, current["id"]):
            raise HTTPException(403, "source device is not active for this account")
        manifest = payload.model_dump(mode="json", exclude={"files"})
        manifest["files"] = [item.model_dump(mode="json", exclude={"content_base64"}) for item in payload.files]
        _reject_sensitive_fields(manifest)
        manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(manifest_json.encode()).hexdigest()
        with db.connect() as cx:
            existing = cx.execute("SELECT session_id,payload_hash FROM session_import_requests WHERE user_id=? AND request_id=?", (current["id"], payload.request_id)).fetchone()
        if existing:
            if not secrets.compare_digest(existing["payload_hash"], payload_hash):
                raise HTTPException(409, "import request payload conflict")
            session = _owned_session(db, existing["session_id"], current["id"])
            return {"code": 0, "msg": "success", "data": {"id": session["id"], "kind": session["kind"], "workspace_id": session["workspace_id"], "idempotent": True}}

        decoded_files = _decode_import_files(payload.files, settings.max_workspace_bytes, settings.max_workspace_files)
        session_id = str(uuid.uuid4())
        workspace_id = f"import-{session_id[:12]}"
        user_workspace_root = settings.workspaces_dir / current["id"]
        user_workspace_root.mkdir(parents=True, exist_ok=True)
        staging_path = user_workspace_root / f".{workspace_id}.{secrets.token_urlsafe(6)}.staging"
        target_path = user_workspace_root / workspace_id
        staging = Workspace(staging_path)
        target_moved = False
        try:
            for logical_path, content in decoded_files:
                staging.write_bytes(logical_path, content)
            now = int(time.time())
            cx = db.connect()
            try:
                cx.execute("BEGIN IMMEDIATE")
                existing = cx.execute("SELECT session_id,payload_hash FROM session_import_requests WHERE user_id=? AND request_id=?", (current["id"], payload.request_id)).fetchone()
                if existing:
                    cx.execute("COMMIT")
                    if not secrets.compare_digest(existing["payload_hash"], payload_hash):
                        raise HTTPException(409, "import request payload conflict")
                    session = _owned_session(db, existing["session_id"], current["id"])
                    return {"code": 0, "msg": "success", "data": {"id": session["id"], "kind": session["kind"], "workspace_id": session["workspace_id"], "idempotent": True}}
                if target_path.exists():
                    raise RuntimeError("import workspace collision")
                os.replace(staging_path, target_path)
                target_moved = True
                cx.execute("INSERT INTO sessions(id,user_id,kind,title,workspace_id,status,next_event_sequence,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (session_id, current["id"], "cloud_native", payload.title, workspace_id, "idle", len(payload.events) + 1, now, now))
                for sequence, event in enumerate(payload.events, start=1):
                    cx.execute("INSERT INTO events(id,session_id,sequence,event_type,payload_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), session_id, sequence, event.event_type, json.dumps(event.payload, separators=(",", ":")), event.created_at or now))
                cx.execute("INSERT INTO session_payloads(session_id,payload_json,created_at) VALUES(?,?,?)", (session_id, manifest_json, now))
                cx.execute("INSERT INTO session_import_requests(user_id,request_id,payload_hash,session_id,created_at) VALUES(?,?,?,?,?)", (current["id"], payload.request_id, payload_hash, session_id, now))
                cx.execute("COMMIT")
            except Exception:
                if cx.in_transaction:
                    cx.execute("ROLLBACK")
                raise
            finally:
                cx.close()
        except HTTPException:
            if target_moved:
                shutil.rmtree(target_path, ignore_errors=True)
            raise
        except Exception as exc:
            if target_moved:
                shutil.rmtree(target_path, ignore_errors=True)
            raise HTTPException(400, "session import failed") from exc
        finally:
            shutil.rmtree(staging_path, ignore_errors=True)
        _audit(db, current["id"], "session.import", session_id, {"source_device_id": payload.source_device_id, "source_session_id": payload.source_session_id, "file_count": len(decoded_files)})
        return {"code": 0, "msg": "success", "data": {"id": session_id, "kind": "cloud_native", "workspace_id": workspace_id, "file_count": len(decoded_files), "bytes_imported": sum(len(content) for _, content in decoded_files), "idempotent": False}}

    @app.post("/v1/sessions/{session_id}/copy")
    @app.post("/v1/cloud/sessions/{session_id}/copy")
    def copy_session(session_id: str, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        source = _owned_session(db, session_id, current["id"])
        new_id = str(uuid.uuid4())
        workspace_id = f"copy-{new_id[:12]}"
        now = int(time.time())
        source_workspace = Workspace(settings.workspaces_dir / current["id"] / source["workspace_id"])
        destination_workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        try:
            copied_files = source_workspace.copy_to(destination_workspace, settings.max_workspace_bytes)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        try:
            with db.connect() as cx:
                cx.execute("BEGIN IMMEDIATE")
                cx.execute("INSERT INTO sessions(id,user_id,kind,title,workspace_id,status,copied_from,model_id,created_at,updated_at,next_sequence,next_event_sequence,authority_epoch) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (new_id, current["id"], source["kind"], f"Copy of {source['title']}", workspace_id, "idle", session_id, source["model_id"], now, now, source["next_sequence"], source["next_event_sequence"], 1))
                command_rows = cx.execute("SELECT request_id,payload_hash,sequence,input_text,attachments_json,options_json,status,created_at FROM commands WHERE session_id=? ORDER BY sequence", (session_id,)).fetchall()
                for row in command_rows:
                    cx.execute("INSERT INTO commands(id,session_id,request_id,payload_hash,sequence,input_text,attachments_json,options_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), new_id, row["request_id"], row["payload_hash"], row["sequence"], row["input_text"], row["attachments_json"], row["options_json"], row["status"], row["created_at"]))
                rows = cx.execute("SELECT sequence,event_type,payload_json,created_at FROM events WHERE session_id=? ORDER BY sequence", (session_id,)).fetchall()
                for row in rows:
                    cx.execute("INSERT INTO events(id,session_id,sequence,event_type,payload_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), new_id, row["sequence"], row["event_type"], row["payload_json"], row["created_at"]))
                payload_row = cx.execute("SELECT payload_json FROM session_payloads WHERE session_id=?", (session_id,)).fetchone()
                if payload_row:
                    cx.execute("INSERT INTO session_payloads(session_id,payload_json,created_at) VALUES(?,?,?)", (new_id, payload_row["payload_json"], now))
                cx.execute("COMMIT")
        except Exception:
            shutil.rmtree(destination_workspace.root, ignore_errors=True)
            raise
        return {"code": 0, "msg": "success", "data": {"id": new_id, "copied_from": session_id, "workspace_id": workspace_id, **copied_files}}

    @app.post("/v1/sessions/{session_id}/authority/rotate")
    @app.post("/v1/cloud/sessions/{session_id}/authority/rotate")
    def rotate_authority(session_id: str, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            cx.execute("UPDATE sessions SET authority_epoch=authority_epoch+1,updated_at=? WHERE id=?", (int(time.time()), session_id))
            epoch = cx.execute("SELECT authority_epoch FROM sessions WHERE id=?", (session_id,)).fetchone()[0]
        _audit(db, current["id"], "session.authority.rotate", session_id, {"authority_epoch": epoch})
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "authority_epoch": epoch}}

    @app.post("/v1/sessions/{session_id}/authority/lease")
    @app.post("/v1/cloud/sessions/{session_id}/authority/lease")
    def acquire_authority_lease(session_id: str, payload: AuthorityLease, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        _owned_session(db, session_id, current["id"])
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            row = cx.execute("SELECT lease_owner,lease_expires_at,authority_epoch FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row["lease_owner"] and row["lease_expires_at"] and row["lease_expires_at"] > now and row["lease_owner"] != payload.owner:
                cx.execute("ROLLBACK")
                raise HTTPException(409, "authority lease is held")
            expires = now + payload.ttl_seconds
            cx.execute("UPDATE sessions SET lease_owner=?,lease_expires_at=?,updated_at=? WHERE id=?", (payload.owner, expires, now, session_id))
            cx.execute("COMMIT")
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "owner": payload.owner, "lease_expires_at": expires, "authority_epoch": row["authority_epoch"]}}

    @app.delete("/v1/sessions/{session_id}/authority/lease")
    @app.delete("/v1/cloud/sessions/{session_id}/authority/lease")
    def release_authority_lease(session_id: str, owner: str, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            result = cx.execute("UPDATE sessions SET lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=? AND lease_owner=?", (int(time.time()), session_id, owner))
        if result.rowcount != 1:
            raise HTTPException(409, "lease owner mismatch or lease is not held")
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "released": True}}

    @app.get("/v1/workspaces")
    def list_workspaces(current=Depends(_auth_dependency(db, required_scope="workspace.read"))):
        root = settings.workspaces_dir / current["id"]
        root.mkdir(parents=True, exist_ok=True)
        result = []
        for child in sorted(root.iterdir()):
            if child.is_dir() and not child.is_symlink() and re.fullmatch(r"[A-Za-z0-9_-]+", child.name):
                workspace = Workspace(child)
                _ensure_workspace_metadata(db, current["id"], child.name)
                result.append({"id": child.name, **workspace.stats()})
        return {"code": 0, "msg": "success", "data": result}

    @app.get("/v1/workspaces/{workspace_id}/stats")
    def workspace_stats(workspace_id: str, current=Depends(_auth_dependency(db, required_scope="workspace.read"))):
        _validate_workspace_id(workspace_id)
        _ensure_workspace_metadata(db, current["id"], workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        return {"code": 0, "msg": "success", "data": {"workspace_id": workspace_id, **workspace.stats()}}

    @app.get("/v1/workspaces/{workspace_id}/capacity")
    def workspace_capacity(workspace_id: str, current=Depends(_auth_dependency(db, required_scope="workspace.read"))):
        """Expose quota and volume capacity so clients can render warnings."""
        _validate_workspace_id(workspace_id)
        _ensure_workspace_metadata(db, current["id"], workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        stats = workspace.stats()
        capacity = workspace.capacity()
        quota = settings.max_workspace_bytes
        quota_percent = min(100, (stats["bytes_used"] * 100 + quota - 1) // quota)
        return {
            "code": 0,
            "msg": "success",
            "data": {
                "workspace_id": workspace_id,
                **stats,
                **capacity,
                "quota_bytes": quota,
                "quota_percent": quota_percent,
                "warning": quota_percent >= settings.workspace_warning_percent,
                "warning_percent": settings.workspace_warning_percent,
            },
        }

    @app.get("/v1/workspaces/{workspace_id}/files/{logical_path:path}")
    def read_workspace_file(workspace_id: str, logical_path: str, current=Depends(_auth_dependency(db, required_scope="workspace.read"))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        try:
            content, truncated = workspace.read_text_bounded(logical_path, settings.max_workspace_read_bytes)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"code": 0, "msg": "success", "data": {"workspace_id": workspace_id, "path": logical_path, "content": content, "truncated": truncated}}

    @app.get("/v1/workspaces/{workspace_id}/files")
    def list_workspace_files(workspace_id: str, prefix: str = "", limit: int = 500, current=Depends(_auth_dependency(db, required_scope="workspace.read"))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        try:
            limit = max(1, min(limit, settings.max_workspace_list_items))
            files = workspace.list_files(prefix, limit=limit + 1)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"code": 0, "msg": "success", "data": {"workspace_id": workspace_id, "files": files[:limit], "truncated": len(files) > limit}}

    @app.put("/v1/workspaces/{workspace_id}/files/{logical_path:path}")
    def write_workspace_file(workspace_id: str, logical_path: str, payload: WorkspaceWrite, current=Depends(_auth_dependency(db, required_scope="workspace.write"))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        with _workspace_lock(app, current["id"], workspace_id):
            try:
                existing_size = workspace.path(logical_path).stat().st_size if workspace.path(logical_path).is_file() else 0
                projected = workspace.stats()["bytes_used"] - existing_size + len(payload.content.encode("utf-8"))
                if projected > settings.max_workspace_bytes:
                    raise HTTPException(413, "workspace quota exceeded")
                if existing_size == 0 and not workspace.path(logical_path).exists() and workspace.stats()["file_count"] >= settings.max_workspace_files:
                    raise HTTPException(413, "workspace file-count quota exceeded")
                workspace.write_text(logical_path, payload.content)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(400, str(exc)) from exc
        _audit(db, current["id"], "workspace.file.write", logical_path, {"workspace_id": workspace_id, "bytes": len(payload.content.encode("utf-8"))})
        return {"code": 0, "msg": "success", "data": {"workspace_id": workspace_id, "path": logical_path, "bytes_written": len(payload.content.encode("utf-8"))}}

    @app.delete("/v1/workspaces/{workspace_id}/files/{logical_path:path}")
    def delete_workspace_file(workspace_id: str, logical_path: str, current=Depends(_auth_dependency(db, required_scope="workspace.write"))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        with _workspace_lock(app, current["id"], workspace_id):
            try:
                workspace.delete_file(logical_path)
            except Exception as exc:
                raise HTTPException(400, str(exc)) from exc
        _audit(db, current["id"], "workspace.file.delete", logical_path, {"workspace_id": workspace_id})
        return {"code": 0, "msg": "success", "data": {"workspace_id": workspace_id, "path": logical_path, "deleted": True}}

    @app.post("/v1/workspaces/{workspace_id}/backups")
    def backup_workspace(workspace_id: str, current=Depends(_auth_dependency(db, required_scope="workspace.write"))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        backup_id = f"{int(time.time())}-{secrets.token_urlsafe(8)}"
        with _workspace_lock(app, current["id"], workspace_id):
            record = backup_storage.create(workspace, user_id=current["id"], workspace_id=workspace_id, backup_id=backup_id)
        _ensure_workspace_metadata(db, current["id"], workspace_id)
        with db.connect() as cx:
            cx.execute("INSERT OR REPLACE INTO workspace_backups(user_id,workspace_id,id,archive_path,bytes,created_at) VALUES(?,?,?,?,?,?)", (current["id"], workspace_id, backup_id, record.location, record.bytes, record.created_at))
        _audit(db, current["id"], "workspace.backup.create", backup_id, {"workspace_id": workspace_id, "bytes": record.bytes, "storage": settings.backup_storage_backend})
        return {"code": 0, "msg": "success", "data": {"backup_id": backup_id, "workspace_id": workspace_id, "bytes": record.bytes, "created_at": record.created_at, "storage": settings.backup_storage_backend}}

    @app.get("/v1/workspaces/{workspace_id}/backups")
    def list_backups(workspace_id: str, limit: int = 100, current=Depends(_auth_dependency(db, required_scope="workspace.read"))):
        _validate_workspace_id(workspace_id)
        limit = max(1, min(limit, settings.max_backup_list_items))
        records = backup_storage.list(user_id=current["id"], workspace_id=workspace_id, limit=limit)
        _ensure_workspace_metadata(db, current["id"], workspace_id)
        with db.connect() as cx:
            for record in records:
                cx.execute("INSERT OR REPLACE INTO workspace_backups(user_id,workspace_id,id,archive_path,bytes,created_at) VALUES(?,?,?,?,?,?)", (current["id"], workspace_id, record.backup_id, record.location, record.bytes, record.created_at))
        return {"code": 0, "msg": "success", "data": [{"backup_id": record.backup_id, "bytes": record.bytes, "created_at": record.created_at, "storage": settings.backup_storage_backend} for record in records]}

    @app.get("/v1/workspaces/{workspace_id}/backups/{backup_id}/download")
    def download_backup(workspace_id: str, backup_id: str, current=Depends(_auth_dependency(db, required_scope="workspace.read"))):
        _validate_workspace_id(workspace_id)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", backup_id):
            raise HTTPException(422, "invalid backup id")
        try:
            content = backup_storage.read(user_id=current["id"], workspace_id=workspace_id, backup_id=backup_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "backup not found") from exc
        _audit(db, current["id"], "workspace.backup.download", backup_id, {"workspace_id": workspace_id, "bytes": len(content)})
        return Response(content=content, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="notemeld-{workspace_id}-{backup_id}.zip"'})

    @app.delete("/v1/workspaces/{workspace_id}/backups/{backup_id}")
    def delete_backup(workspace_id: str, backup_id: str, current=Depends(_auth_dependency(db, required_scope="workspace.write"))):
        _validate_workspace_id(workspace_id)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", backup_id):
            raise HTTPException(422, "invalid backup id")
        with _workspace_lock(app, current["id"], workspace_id):
            try:
                backup_storage.delete(user_id=current["id"], workspace_id=workspace_id, backup_id=backup_id)
            except FileNotFoundError as exc:
                raise HTTPException(404, "backup not found") from exc
        with db.connect() as cx:
            cx.execute("DELETE FROM workspace_backups WHERE user_id=? AND workspace_id=? AND id=?", (current["id"], workspace_id, backup_id))
        _audit(db, current["id"], "workspace.backup.delete", backup_id, {"workspace_id": workspace_id})
        return {"code": 0, "msg": "success", "data": {"backup_id": backup_id, "workspace_id": workspace_id, "deleted": True}}

    @app.post("/v1/workspaces/{workspace_id}/backups/restore")
    def restore_workspace(workspace_id: str, payload: WorkspaceRestore, current=Depends(_auth_dependency(db, required_scope="workspace.write"))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        with _workspace_lock(app, current["id"], workspace_id):
            try:
                restored = backup_storage.restore(workspace, user_id=current["id"], workspace_id=workspace_id, backup_id=payload.backup_id, max_bytes=settings.max_workspace_bytes, max_files=settings.max_workspace_files)
            except Exception as exc:
                raise HTTPException(400, str(exc)) from exc
        _audit(db, current["id"], "workspace.backup.restore", payload.backup_id, {"workspace_id": workspace_id, **restored})
        return {"code": 0, "msg": "success", "data": {"backup_id": payload.backup_id, "workspace_id": workspace_id, **restored}}

    @app.get("/v1/sessions")
    @app.get("/v1/cloud/sessions")
    def list_sessions(archived: bool | None = None, device_id: Annotated[str | None, Header(alias="X-Device-Id")] = None, current=Depends(_auth_dependency(db, required_scope="session.read"))):
        device_id = _effective_device_id(current, device_id)
        _validate_device_header(db, device_id, current["id"])
        with db.connect() as cx:
            rows = cx.execute("SELECT s.*, COALESCE((SELECT archived_at FROM session_archives WHERE session_id=s.id AND user_id=? AND device_id=?), (SELECT archived_at FROM session_archives WHERE session_id=s.id AND user_id=? AND device_id IS NULL)) AS archived_at FROM sessions s WHERE s.user_id=? ORDER BY s.updated_at DESC", (current["id"], device_id, current["id"], current["id"])).fetchall()
        result = [dict(row) for row in rows]
        if archived is not None:
            result = [item for item in result if bool(item["archived_at"]) is archived]
        return {"code": 0, "msg": "success", "data": result}

    @app.post("/v1/sessions/{session_id}/archive")
    @app.post("/v1/cloud/sessions/{session_id}/archive")
    def archive_session(session_id: str, device_id: Annotated[str | None, Header(alias="X-Device-Id")] = None, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        device_id = _effective_device_id(current, device_id)
        _owned_session(db, session_id, current["id"])
        _validate_device_header(db, device_id, current["id"])
        with db.connect() as cx:
            if device_id is None:
                cx.execute("DELETE FROM session_archives WHERE session_id=? AND user_id=? AND device_id IS NULL", (session_id, current["id"]))
            else:
                cx.execute("DELETE FROM session_archives WHERE session_id=? AND user_id=? AND device_id=?", (session_id, current["id"], device_id))
            cx.execute("INSERT OR REPLACE INTO session_archives(user_id,session_id,device_id,archived_at) VALUES(?,?,?,?)", (current["id"], session_id, device_id, int(time.time())))
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "archived": True}}

    @app.post("/v1/sessions/{session_id}/restore")
    @app.post("/v1/cloud/sessions/{session_id}/restore")
    def restore_session(session_id: str, device_id: Annotated[str | None, Header(alias="X-Device-Id")] = None, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        device_id = _effective_device_id(current, device_id)
        _owned_session(db, session_id, current["id"])
        _validate_device_header(db, device_id, current["id"])
        with db.connect() as cx:
            if device_id is None:
                result = cx.execute("DELETE FROM session_archives WHERE session_id=? AND user_id=? AND device_id IS NULL", (session_id, current["id"]))
            else:
                result = cx.execute("DELETE FROM session_archives WHERE session_id=? AND user_id=? AND device_id=?", (session_id, current["id"], device_id))
        if result.rowcount != 1:
            raise HTTPException(404, "archived session not found")
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "archived": False}}

    @app.patch("/v1/sessions/{session_id}")
    @app.patch("/v1/cloud/sessions/{session_id}")
    def rename_session(session_id: str, payload: SessionRename, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        _owned_session(db, session_id, current["id"])
        title = payload.title.strip()
        now = int(time.time())
        with db.connect() as cx:
            result = cx.execute("UPDATE sessions SET title=?, updated_at=? WHERE id=? AND user_id=?", (title, now, session_id, current["id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "session not found")
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "title": title}}

    @app.delete("/v1/sessions/{session_id}")
    @app.delete("/v1/cloud/sessions/{session_id}")
    def delete_session(session_id: str, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        session = _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            cx.execute("DELETE FROM events WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM commands WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM share_tokens WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM session_archives WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM session_import_requests WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM session_payloads WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM relay_cursors WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM sessions WHERE id=? AND user_id=?", (session_id, current["id"]))
            workspace_references = cx.execute("SELECT COUNT(*) FROM sessions WHERE user_id=? AND workspace_id=?", (current["id"], session["workspace_id"])).fetchone()[0]
            cx.execute("COMMIT")
        workspace_purged = workspace_references == 0
        if workspace_purged:
            shutil.rmtree(settings.workspaces_dir / current["id"] / session["workspace_id"], ignore_errors=True)
            shutil.rmtree(settings.data_dir / "backups" / current["id"] / session["workspace_id"], ignore_errors=True)
        _audit(db, current["id"], "session.delete", session_id, {"workspace_id": session["workspace_id"], "workspace_purged": workspace_purged})
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "deleted": True, "workspace_purged": workspace_purged}}

    @app.get("/v1/sessions/{session_id}/approvals")
    @app.get("/v1/cloud/sessions/{session_id}/approvals")
    def list_approvals(session_id: str, current=Depends(_auth_dependency(db, required_scope="session.read"))):
        _owned_session(db, session_id, current["id"])
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("UPDATE approvals SET status='expired',resolved_at=?,resolution_note='approval expired' WHERE session_id=? AND user_id=? AND status='pending' AND created_at<?", (now, session_id, current["id"], now - max(1, app.state.settings.approval_ttl_seconds)))
        with db.connect() as cx:
            rows = cx.execute("SELECT id,session_id,command_id,tool_name,arguments_json,status,requested_by,resolved_by,resolution_note,created_at,resolved_at FROM approvals WHERE session_id=? AND user_id=? ORDER BY created_at DESC", (session_id, current["id"])).fetchall()
        items = []
        for row in rows:
            arguments = json.loads(row["arguments_json"])
            if "content" in arguments and isinstance(arguments["content"], str):
                arguments["content_preview"] = arguments.pop("content")[:1000]
                arguments["content_truncated"] = True
            item = dict(row)
            item.pop("arguments_json", None)
            items.append({**item, "arguments": arguments})
        return {"code": 0, "msg": "success", "data": items}

    @app.post("/v1/sessions/{session_id}/approvals/{approval_id}/resolve")
    @app.post("/v1/cloud/sessions/{session_id}/approvals/{approval_id}/resolve")
    def resolve_approval(session_id: str, approval_id: str, payload: ApprovalResolve, device_id: Annotated[str | None, Header(alias="X-Device-Id")] = None, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        device_id = _effective_device_id(current, device_id)
        session = _owned_session(db, session_id, current["id"])
        _validate_device_header(db, device_id, current["id"])
        if session["kind"] == "device_remote":
            if not device_id or not _remote_approval_allowed(db, session_id, current["id"], device_id):
                raise HTTPException(403, "remote approval requires an authorized controller device")
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            row = cx.execute("SELECT status,requested_by FROM approvals WHERE id=? AND session_id=? AND user_id=?", (approval_id, session_id, current["id"])).fetchone()
            if not row:
                cx.execute("ROLLBACK")
                raise HTTPException(404, "approval not found")
            if row["status"] != "pending":
                cx.execute("COMMIT")
                return {"code": 0, "msg": "success", "data": {"approval_id": approval_id, "status": row["status"], "idempotent": True}}
            approval = cx.execute("SELECT tool_name,arguments_json,requested_by FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if approval is None:
                cx.execute("ROLLBACK")
                raise HTTPException(404, "approval not found")
            created_at = cx.execute("SELECT created_at FROM approvals WHERE id=?", (approval_id,)).fetchone()[0]
            if created_at < now - max(1, app.state.settings.approval_ttl_seconds):
                cx.execute("UPDATE approvals SET status='expired',resolved_by=?,resolution_note='approval expired',resolved_at=? WHERE id=? AND status='pending'", (current["id"], now, approval_id))
                cx.execute("COMMIT")
                return {"code": 0, "msg": "success", "data": {"approval_id": approval_id, "status": "expired", "idempotent": True}}
            if approval["requested_by"] == "cloud-agent-native":
                with app.state.native_approval_lock:
                    native_runner = app.state.native_approval_runtimes.get(approval_id)
                LOGGER.info("canonical approval resolve lookup: found=%s", native_runner is not None)
                if native_runner is None:
                    cx.execute("ROLLBACK")
                    raise HTTPException(409, "approval runtime unavailable")
                decision = "approve" if payload.status == "approved" else "deny"
                try:
                    native_runner.resolve_approval(approval_id, decision)
                except Exception as exc:
                    cx.execute("ROLLBACK")
                    LOGGER.error("canonical approval resolve failed: type=%s code=%s", type(exc).__name__, getattr(exc, "code", None))
                    _audit(db, current["id"], "approval.resolve_failed", approval_id, {"session_id": session_id, "requested_by": "cloud-agent-native"})
                    raise HTTPException(409, "approval could not be resolved") from exc
            elif payload.status == "approved":
                try:
                    _execute_approved_tool(app=app, settings=app.state.settings, session=session, user_id=current["id"], tool_name=approval["tool_name"], arguments=json.loads(approval["arguments_json"]))
                except Exception as exc:
                    cx.execute("UPDATE approvals SET status='rejected',resolved_by=?,resolution_note=?,resolved_at=? WHERE id=? AND status='pending'", (current["id"], "execution failed", now, approval_id))
                    cx.execute("COMMIT")
                    _audit(db, current["id"], "approval.execution_failed", approval_id, {"session_id": session_id, "error_type": type(exc).__name__})
                    raise HTTPException(409, "approved operation could not be executed") from exc
            cx.execute("UPDATE approvals SET status=?,resolved_by=?,resolution_note=?,resolved_at=? WHERE id=? AND status='pending'", (payload.status, current["id"], payload.note, now, approval_id))
            cx.execute("COMMIT")
        _audit(db, current["id"], f"approval.{payload.status}", approval_id, {"session_id": session_id})
        return {"code": 0, "msg": "success", "data": {"approval_id": approval_id, "status": payload.status, "resolved_at": now}}

    @app.post("/v1/sessions/{session_id}/commands")
    @app.post("/v1/cloud/sessions/{session_id}/commands")
    def submit_command(session_id: str, payload: CommandCreate, response: Response, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        result = _submit_cloud_command(app, db, session_id, payload, current["id"])
        if result.get("data", {}).get("status") in {"queued", "running"}:
            response.status_code = 202
        return result

    @app.post("/v1/cloud/sessions/{session_id}/terminal")
    def terminal_exec(session_id: str, payload: TerminalExec, current=Depends(_auth_dependency(db, required_scope="workspace.write"))):
        """在分配文件夹内执行一条 shell 命令并真实返回结果。"""
        session = _owned_session(db, session_id, current["id"])
        shell = open_workspace_shell(
            app.state.settings.workspaces_dir, current["id"], str(session["workspace_id"])
        )
        try:
            data = shell.run(payload.command, payload.cwd)
        except TerminalError as exc:
            raise HTTPException(400, str(exc))
        return {"code": 0, "msg": "success", "data": data}

    @app.post("/v1/cloud/sessions/{session_id}/stream")
    async def stream_turn(
        session_id: str,
        payload: StreamCreate,
        current=Depends(_auth_dependency(db, required_scope="session.write")),
    ):
        """流式发送一轮：先持久化命令（running），再以 SSE 推送思考/正文增量。"""
        from starlette.concurrency import run_in_threadpool, iterate_in_threadpool

        session = await run_in_threadpool(_owned_session, db, session_id, current["id"])
        command_id, sequence = await run_in_threadpool(
            _persist_running_command, db, session_id, payload, current["id"]
        )
        history = await run_in_threadpool(_cloud_history, db, session_id)
        messages = history + [{"role": "user", "content": payload.input}]

        def blocking_events():
            # provider I/O 全部阻塞：整体放到线程池迭代，避免卡住事件循环。
            status = "completed"
            error_message: str | None = None
            answer = ""
            reasoning_parts: list[str] = []
            current_reasoning = ""
            try:
                stream = _open_model_stream(app, db, session, command_model_id=payload.model_id)
                for event in stream(messages):
                    # reasoning 是思考过程（独立持久化），delta 才是正式回复。
                    if event["type"] == "reasoning":
                        current_reasoning += event["text"]
                    if event["type"] == "delta":
                        if current_reasoning:
                            reasoning_parts.append(current_reasoning)
                            current_reasoning = ""
                        answer += event["text"]
                    yield event
                if current_reasoning:
                    reasoning_parts.append(current_reasoning)
            except Exception as exc:  # noqa: BLE001 - 失败也要落库并告知前端
                status = "failed"
                error_message = str(exc) or "cloud agent provider unavailable"
                yield {"type": "error", "message": error_message}
            finally:
                _finalize_command_records(
                    db, session_id, command_id, sequence,
                    status=status, output=answer, error=error_message,
                    reasoning=reasoning_parts,
                )
            yield {"type": "done", "status": status}

        async def event_generator():
            async for event in iterate_in_threadpool(blocking_events()):
                yield _sse(event)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/v1/sessions/{session_id}/commands/{command_id}")
    @app.get("/v1/cloud/sessions/{session_id}/commands/{command_id}")
    def command_status(session_id: str, command_id: str, current=Depends(_auth_dependency(db, required_scope="session.read"))):
        _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            row = cx.execute("SELECT id,session_id,request_id,sequence,status,lease_owner,lease_expires_at,attempt_count,created_at FROM commands WHERE id=? AND session_id=?", (command_id, session_id)).fetchone()
        if not row:
            raise HTTPException(404, "command not found")
        return {"code": 0, "msg": "success", "data": dict(row)}

    @app.get("/v1/sessions/{session_id}/commands")
    @app.get("/v1/cloud/sessions/{session_id}/commands")
    def list_commands(session_id: str, after: int = 0, limit: int = 100, current=Depends(_auth_dependency(db, required_scope="session.read"))):
        if after < 0:
            raise HTTPException(422, "after must be non-negative")
        _owned_session(db, session_id, current["id"])
        limit = max(1, min(limit, 500))
        with db.connect() as cx:
            rows = cx.execute("SELECT id,session_id,request_id,sequence,input_text,attachments_json,options_json,status,lease_owner,lease_expires_at,attempt_count,created_at FROM commands WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT ?", (session_id, after, limit)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "attachments": json.loads(row["attachments_json"] or "[]"), **json.loads(row["options_json"] or "{}")} for row in rows]}

    @app.post("/v1/sessions/{session_id}/commands/{command_id}/recover")
    @app.post("/v1/cloud/sessions/{session_id}/commands/{command_id}/recover")
    def recover_command(session_id: str, command_id: str, payload: CommandRecover, current=Depends(_auth_dependency(db, required_scope="session.write"))):
        _owned_session(db, session_id, current["id"])
        now = int(time.time())
        new_status = "queued" if payload.mode == "resume" else "abandoned"
        event_type = "command.requeued" if payload.mode == "resume" else "command.abandoned"
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            row = cx.execute("SELECT sequence,status FROM commands WHERE id=? AND session_id=?", (command_id, session_id)).fetchone()
            if not row:
                cx.execute("ROLLBACK")
                raise HTTPException(404, "command not found")
            if row["status"] != "needs_attention":
                cx.execute("COMMIT")
                return {"code": 0, "msg": "success", "data": {"command_id": command_id, "status": row["status"], "idempotent": True}}
            event_sequence = cx.execute("SELECT next_event_sequence FROM sessions WHERE id=?", (session_id,)).fetchone()[0]
            cx.execute("UPDATE commands SET status=?,lease_owner=NULL,lease_expires_at=NULL WHERE id=? AND status='needs_attention'", (new_status, command_id))
            cx.execute("INSERT INTO events(id,session_id,sequence,event_type,payload_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), session_id, event_sequence, event_type, json.dumps({"command_id": command_id, "command_sequence": row["sequence"], "status": new_status, "recovered_by": current["id"]}, separators=(",", ":")), now))
            has_queued = cx.execute("SELECT 1 FROM commands WHERE session_id=? AND status='queued' LIMIT 1", (session_id,)).fetchone() is not None
            cx.execute("UPDATE sessions SET next_event_sequence=?,status=? WHERE id=?", (event_sequence + 1, "queued" if has_queued else "idle", session_id))
            cx.execute("COMMIT")
        if has_queued:
            _ensure_session_worker(app, db, session_id, current["id"])
        _audit(db, current["id"], f"command.{payload.mode}", command_id, {"session_id": session_id})
        return {"code": 0, "msg": "success", "data": {"command_id": command_id, "status": new_status, "mode": payload.mode}}

    @app.get("/v1/sessions/{session_id}/snapshot")
    @app.get("/v1/cloud/sessions/{session_id}/snapshot")
    def snapshot(session_id: str, limit: int = 500, current=Depends(_auth_dependency(db, required_scope="session.read"))):
        session = _owned_session(db, session_id, current["id"])
        limit = max(1, min(limit, 5000))
        with db.connect() as cx:
            events = cx.execute("SELECT sequence,event_type,payload_json,created_at FROM events WHERE session_id=? ORDER BY sequence LIMIT ?", (session_id, limit)).fetchall()
            imported = cx.execute("SELECT payload_json FROM session_payloads WHERE session_id=?", (session_id,)).fetchone()
        return {"code": 0, "msg": "success", "data": {"session": dict(session), "snapshot_seq": events[-1]["sequence"] if events else 0, "events": [{**dict(row), "payload": json.loads(row["payload_json"])} for row in events], "imported_snapshot": json.loads(imported["payload_json"]) if imported else None}}

    @app.get("/v1/shared/{session_id}/snapshot")
    def shared_snapshot(session_id: str, limit: int = 500, share_token: Annotated[str | None, Header(alias="X-Share-Token")] = None):
        access = _authenticate_share_token(db, share_token, session_id)
        if not access:
            raise HTTPException(401, "invalid share token")
        return snapshot(session_id, limit=limit, current={"id": access["user_id"]})

    @app.get("/v1/shared/{session_id}/commands")
    def shared_commands(session_id: str, after: int = 0, limit: int = 100, share_token: Annotated[str | None, Header(alias="X-Share-Token")] = None):
        if after < 0:
            raise HTTPException(422, "after must be non-negative")
        access = _authenticate_share_token(db, share_token, session_id)
        if not access:
            raise HTTPException(401, "invalid share token")
        _owned_session(db, session_id, access["user_id"])
        limit = max(1, min(limit, 500))
        with db.connect() as cx:
            rows = cx.execute("SELECT id,session_id,sequence,input_text,status,created_at FROM commands WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT ?", (session_id, after, limit)).fetchall()
        return {"code": 0, "msg": "success", "data": [dict(row) for row in rows]}

    @app.get("/v1/shared/{session_id}/events")
    def shared_events(session_id: str, after: int = 0, limit: int = 500, share_token: Annotated[str | None, Header(alias="X-Share-Token")] = None):
        if after < 0:
            raise HTTPException(422, "after must be non-negative")
        access = _authenticate_share_token(db, share_token, session_id)
        if not access:
            raise HTTPException(401, "invalid share token")
        _owned_session(db, session_id, access["user_id"])
        limit = max(1, min(limit, 5000))
        with db.connect() as cx:
            rows = cx.execute("SELECT sequence,event_type,payload_json,created_at FROM events WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT ?", (session_id, after, limit)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]}

    @app.post("/v1/shared/{session_id}/commands")
    def shared_command(session_id: str, payload: CommandCreate, share_token: Annotated[str | None, Header(alias="X-Share-Token")] = None):
        access = _authenticate_share_token(db, share_token, session_id)
        if not access:
            raise HTTPException(401, "invalid share token")
        scopes = json.loads(access["scopes_json"])
        if access["role"] == "viewer" or "message.send" not in scopes:
            raise HTTPException(403, "share token cannot send messages")
        return submit_command(session_id, payload, Response(), current={"id": access["user_id"]})

    @app.get("/v1/sessions/{session_id}/events")
    @app.get("/v1/cloud/sessions/{session_id}/events")
    def events(session_id: str, after: int = 0, limit: int = 500, current=Depends(_auth_dependency(db, required_scope="session.read"))):
        if after < 0:
            raise HTTPException(422, "after must be non-negative")
        _owned_session(db, session_id, current["id"])
        limit = max(1, min(limit, 5000))
        with db.connect() as cx:
            rows = cx.execute("SELECT sequence,event_type,payload_json,created_at FROM events WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT ?", (session_id, after, limit)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]}

    @app.websocket("/v1/relay/connect/{session_id}")
    async def relay(websocket: WebSocket, session_id: str):
        auth_header, selected_subprotocol = _websocket_auth(websocket)
        current = _authenticate_token(db, auth_header)
        device_id = websocket.query_params.get("device_id")
        if not current or not device_id or (current["device_id"] is not None and current["device_id"] != device_id) or not _session_owned_by(db, session_id, current["id"]) or not _active_device_owned(db, device_id, current["id"]):
            await websocket.close(code=4401)
            return
        if settings.require_device_proof and app.state.device_proofs.get((current["id"], device_id), 0) <= int(time.time()):
            await websocket.close(code=4403)
            return
        await websocket.accept(subprotocol=selected_subprotocol)
        with db.connect() as cx:
            cx.execute("UPDATE devices SET last_seen_at=? WHERE id=?", (int(time.time()), device_id))
        previous = await _maybe_await(app.state.relay_broker.register(session_id, device_id, websocket))
        if previous is not None and previous is not websocket:
            await previous.close(code=4009, reason="replaced by a newer connection")
        await websocket.send_json({"type": "relay_ready", "next_sequence": _relay_next_sequence(db, session_id, device_id)})
        frame_times: list[int] = []
        try:
            while True:
                message = await websocket.receive_text()
                now = int(time.time())
                frame_times[:] = [stamp for stamp in frame_times if stamp > now - 60]
                if len(frame_times) >= 120:
                    await websocket.send_json({"type": "rejected", "error": "relay_rate_limited"})
                    continue
                frame_times.append(now)
                if len(message.encode()) > min(settings.relay_max_frame_bytes, settings.max_request_bytes):
                    await websocket.send_json({"type": "rejected", "error": "frame_too_large"})
                    continue
                try:
                    envelope = json.loads(message)
                    if not isinstance(envelope, dict):
                        raise ValueError("invalid relay envelope")
                    sequence = envelope.get("sequence")
                    frame_type = envelope.get("frame_type", "command")
                    if envelope.get("protocol_version") != "notemeld.sync.v1" or envelope.get("session_id") != session_id or envelope.get("sender_device_id") != device_id or not envelope.get("recipient_device_id") or not envelope.get("ciphertext") or not envelope.get("frame_id") or not _valid_nonce(envelope.get("nonce")) or frame_type not in {"command", "receipt", "event", "handshake"} or not isinstance(sequence, int) or sequence < 1:
                        raise ValueError("invalid relay envelope")
                    with db.connect() as cx:
                        session_row = cx.execute("SELECT authority_epoch,workspace_id FROM sessions WHERE id=?", (session_id,)).fetchone()
                        if session_row is None:
                            raise ValueError("session unavailable")
                        epoch = session_row["authority_epoch"]
                    if envelope.get("authority_epoch") != epoch:
                        raise ValueError("stale authority epoch")
                    required_scope = {"command": "message.send", "event": "event.receive", "receipt": None, "handshake": "message.send"}[frame_type]
                    if not _grant_allows(db, session_id, current["id"], device_id, envelope["recipient_device_id"], required_scope, session_row["workspace_id"]):
                        raise ValueError("relay grant missing")
                    if not _accept_relay_sequence(db, session_id, device_id, sequence):
                        raise ValueError("replayed relay envelope")
                except (ValueError, json.JSONDecodeError, TypeError, AttributeError):
                    await websocket.send_json({"type": "rejected", "error": "invalid_envelope"})
                    continue
                delivered = await _relay_deliver(
                    app.state.relay_broker,
                    session_id,
                    envelope["recipient_device_id"],
                    message,
                    websocket,
                )
                if not delivered:
                    await websocket.send_json({"type": "failed", "error": "host_offline", "frame_id": envelope["frame_id"]})
                    continue
                await websocket.send_json({"type": "relay_accepted", "frame_id": envelope["frame_id"]})
        except WebSocketDisconnect:
            pass
        finally:
            # Clean up on disconnects as well as broker/socket failures. The
            # broker unregister operation is identity-checked, so a replaced
            # connection cannot remove the newer presence marker.
            await _maybe_await(app.state.relay_broker.unregister(session_id, device_id, websocket))

    _start_queued_workers(app, db)
    return app


def _restore_startup_backup(db: CloudDB, settings: CloudSettings) -> None:
    image = settings.startup_backup_image
    if image is None:
        return
    if not image.is_file() or image.suffix.lower() != ".zip":
        raise ValueError("NOTEMELD_CLOUD_STARTUP_BACKUP_IMAGE must point to a ZIP backup image")
    with db.connect() as cx:
        admin = cx.execute("SELECT id FROM users WHERE username=?", (settings.admin_username,)).fetchone()
    if not admin:
        raise RuntimeError("bootstrap admin is unavailable for startup backup restore")
    workspace_id = settings.startup_backup_workspace
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", workspace_id):
        raise ValueError("NOTEMELD_CLOUD_STARTUP_BACKUP_WORKSPACE is invalid")
    workspace = Workspace(settings.workspaces_dir / admin["id"] / workspace_id)
    workspace.restore_backup(image, settings.max_workspace_bytes, settings.max_workspace_files)
    _ensure_workspace_metadata(db, admin["id"], workspace_id)


def _bootstrap_admin(db: CloudDB, settings: CloudSettings) -> None:
    if not settings.admin_password:
        raise RuntimeError("NOTEMELD_CLOUD_ADMIN_PASSWORD must be set")
    with db.connect() as cx:
        existing = cx.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
        if not existing:
            admin_id = str(uuid.uuid4())
            now = int(time.time())
            cx.execute("INSERT INTO users(id,username,email,display_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?,?)", (admin_id, settings.admin_username, settings.admin_email, settings.admin_username, hash_password(settings.admin_password), "admin", now))
            cx.execute("INSERT OR IGNORE INTO organization_members(organization_id,user_id,role,created_at) VALUES('default',?,?,?)", (admin_id, "owner", now))
        else:
            cx.execute("INSERT OR IGNORE INTO organization_members(organization_id,user_id,role,created_at) SELECT 'default',id,CASE WHEN role='admin' THEN 'owner' ELSE 'member' END,? FROM users", (int(time.time()),))


def _user_by_username(db: CloudDB, username: str):
    with db.connect() as cx:
        rows = cx.execute("SELECT * FROM users WHERE username=? ORDER BY created_at", (username,)).fetchall()
    return rows[0] if len(rows) == 1 else None


def _user_by_account_id(db: CloudDB, account_id: str | None):
    if not account_id:
        return None
    with db.connect() as cx:
        return cx.execute("SELECT * FROM users WHERE id=?", (account_id,)).fetchone()


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 320 or re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is None:
        raise HTTPException(422, "valid email is required")
    return email


def _user_by_email(db: CloudDB, email: str):
    with db.connect() as cx:
        return cx.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()


def _verification_digest(email: str, purpose: str, code: str) -> str:
    return hashlib.sha256(f"notemeld:verification:{purpose}:{email}:{code}".encode()).hexdigest()


def _login_result(db: CloudDB, settings: CloudSettings, user: Any, email_verified: bool) -> dict:
    raw, digest = issue_token()
    now = int(time.time())
    token_id = raw[4:].split(".", 1)[0]
    expires_at = token_expiry(settings.token_ttl_seconds)
    with db.connect() as cx:
        cx.execute("INSERT INTO tokens(id,user_id,digest,expires_at,audience,scopes_json,created_at) VALUES(?,?,?,?,?,?,?)", (token_id, user["id"], digest, expires_at, "cloud-api", '["*"]', now))
        if email_verified:
            cx.execute("UPDATE users SET email_verified_at=?,last_login_at=? WHERE id=?", (now, now, user["id"]))
        else:
            cx.execute("UPDATE users SET last_login_at=? WHERE id=?", (now, user["id"]))
    _audit(db, user["id"], "auth.login", user["id"], {"role": user["role"], "method": "email_code" if email_verified else "email_password"})
    return {"code": 0, "msg": "success", "data": {"token": raw, "jti": token_id, "user_id": user["id"], "role": user["role"], "audience": "cloud-api", "scopes": ["*"], "expires_at": expires_at}}


def _auth_dependency(db: CloudDB, required_role: str | None = None, required_scope: str | None = None, required_audience: str | None = None):
    def dependency(authorization: Annotated[str | None, Header()] = None):
        row = _authenticate_token(db, authorization)
        if not row:
            raise HTTPException(401, "invalid token")
        if required_role and row["role"] != required_role:
            raise HTTPException(403, "permission denied")
        if required_audience and row["audience"] != required_audience:
            raise HTTPException(403, "token audience denied")
        scopes = json.loads(row["scopes_json"])
        if required_scope and "*" not in scopes and required_scope not in scopes:
            raise HTTPException(403, "token scope denied")
        return row
    return dependency


def _resolve_org(db: CloudDB, current: Any, requested_org_id: str | None, *, write: bool) -> tuple[str, str]:
    """解析调用者所属组织并校验目录权限；返回 (organization_id, role)。"""
    with db.connect() as cx:
        memberships = cx.execute(
            "SELECT organization_id,role FROM organization_members WHERE user_id=?",
            (current["id"],),
        ).fetchall()
    if not memberships:
        raise HTTPException(403, "organization membership required")
    if requested_org_id:
        match = next((row for row in memberships if row["organization_id"] == requested_org_id), None)
        if not match:
            raise HTTPException(403, "organization access denied")
        org_id, role = match["organization_id"], match["role"]
    else:
        org_id, role = memberships[0]["organization_id"], memberships[0]["role"]
    if write and role not in ("owner", "admin"):
        raise HTTPException(403, "only organization owner or admin can write the model catalog")
    return org_id, role


def _catalog_auth(db: CloudDB, *, write: bool, required_scope: str | None = None):
    """组织目录鉴权依赖：member 只读，owner/admin 可写。"""
    def dependency(payload_org_id: str | None, current=Depends(_auth_dependency(db, required_scope=required_scope))):
        return _resolve_org(db, current, payload_org_id, write=write)
    return dependency


def _require_bound_device(current: Any, target_device_id: str) -> None:
    bound_device_id = current["device_id"]
    if bound_device_id is not None and bound_device_id != target_device_id:
        raise HTTPException(403, "device token cannot act as another device")


def _effective_device_id(current: Any, requested_device_id: str | None) -> str | None:
    bound_device_id = current["device_id"]
    if bound_device_id is None:
        return requested_device_id
    if requested_device_id is not None and requested_device_id != bound_device_id:
        raise HTTPException(403, "device token cannot act as another device")
    return str(bound_device_id)


def _authenticate_token(db: CloudDB, authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    parsed = parse_token(authorization[7:].strip())
    if not parsed:
        return None
    token_id, secret = parsed
    with db.connect() as cx:
        row = cx.execute("SELECT u.*,t.id AS token_id,t.expires_at,t.revoked_at,t.audience,t.scopes_json,t.device_id,d.id AS bound_device_exists,d.revoked_at AS device_revoked_at FROM tokens t JOIN users u ON u.id=t.user_id LEFT JOIN devices d ON d.id=t.device_id AND d.user_id=t.user_id WHERE t.id=? AND t.digest=?", (token_id, token_digest(token_id, secret))).fetchone()
    if not row or row["revoked_at"] or row["disabled"] or (row["expires_at"] is not None and row["expires_at"] <= int(time.time())):
        return None
    if row["device_id"] is not None and (row["bound_device_exists"] is None or row["device_revoked_at"] is not None):
        return None
    return row


def _websocket_auth(websocket: WebSocket) -> tuple[str | None, str | None]:
    """Read normal Authorization or browser-compatible bearer subprotocol."""
    authorization = websocket.headers.get("authorization")
    if authorization:
        return authorization, None
    protocols = [item.strip() for item in websocket.headers.get("sec-websocket-protocol", "").split(",") if item.strip()]
    for protocol in protocols:
        if protocol.startswith("bearer.") and len(protocol) > len("bearer."):
            selected = "notemeld.v1" if "notemeld.v1" in protocols else None
            return f"Bearer {protocol[len('bearer.'):]}" , selected
    return None, "notemeld.v1" if "notemeld.v1" in protocols else None


async def _maybe_await(value):
    """Allow the default synchronous broker and async distributed brokers."""
    if hasattr(value, "__await__"):
        return await value
    return value


async def _relay_deliver(broker: Any, session_id: str, recipient_device_id: str, message: str, sender: Any) -> bool:
    deliver = getattr(broker, "deliver", None)
    if callable(deliver):
        return bool(await _maybe_await(deliver(session_id, recipient_device_id, message, sender)))
    peer = broker.peer(session_id, recipient_device_id)
    if peer is None or peer is sender:
        return False
    try:
        await peer.send_text(message)
    except Exception:  # noqa: BLE001 - a peer can disconnect between lookup and delivery
        await _maybe_await(broker.unregister(session_id, recipient_device_id, peer))
        return False
    return True


def _login_rate_limited(db: CloudDB, key: str, now: int, window_seconds: int = 60, max_failures: int = 5) -> bool:
    with db.connect() as cx:
        row = cx.execute("SELECT window_started,failed_count FROM login_attempts WHERE key=?", (key,)).fetchone()
    return bool(row and row["window_started"] > now - window_seconds and row["failed_count"] >= max_failures)


def _login_key(namespace: str, *parts: str) -> str:
    material = "\0".join((namespace, *parts)).encode("utf-8", "strict")
    return hashlib.sha256(material).hexdigest()


def _record_login_failure(db: CloudDB, key: str, now: int, window_seconds: int = 60) -> int:
    with db.connect() as cx:
        cx.execute("BEGIN IMMEDIATE")
        row = cx.execute("SELECT window_started,failed_count FROM login_attempts WHERE key=?", (key,)).fetchone()
        if not row or row["window_started"] <= now - window_seconds:
            cx.execute("INSERT INTO login_attempts(key,window_started,failed_count) VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET window_started=excluded.window_started,failed_count=excluded.failed_count", (key, now))
            failed_count = 1
        else:
            cx.execute("UPDATE login_attempts SET failed_count=failed_count+1 WHERE key=?", (key,))
            failed_count = int(row["failed_count"]) + 1
        cx.execute("DELETE FROM login_attempts WHERE window_started<=?", (now - window_seconds,))
        cx.execute("COMMIT")
    return failed_count


def _clear_login_failures(db: CloudDB, key: str) -> None:
    with db.connect() as cx:
        cx.execute("DELETE FROM login_attempts WHERE key=?", (key,))


def _owned_session(db: CloudDB, session_id: str, user_id: str):
    with db.connect() as cx:
        row = cx.execute("SELECT * FROM sessions WHERE id=? AND user_id=?", (session_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, "session not found")
    return row


def _session_owned_by(db: CloudDB, session_id: str, user_id: str) -> bool:
    with db.connect() as cx:
        return cx.execute("SELECT 1 FROM sessions WHERE id=? AND user_id=?", (session_id, user_id)).fetchone() is not None


def _active_device_owned(db: CloudDB, device_id: str, user_id: str) -> bool:
    with db.connect() as cx:
        return cx.execute("SELECT 1 FROM devices WHERE id=? AND user_id=? AND revoked_at IS NULL", (device_id, user_id)).fetchone() is not None


def _validate_device_header(db: CloudDB, device_id: str | None, user_id: str) -> None:
    if device_id is not None and not _active_device_owned(db, device_id, user_id):
        raise HTTPException(403, "device is not active for this account")


def _validate_workspace_id(workspace_id: str) -> None:
    if not workspace_id or len(workspace_id) > 128 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in workspace_id):
        raise HTTPException(400, "invalid workspace id")


def _ensure_workspace_metadata(db: CloudDB, user_id: str, workspace_id: str) -> None:
    now = int(time.time())
    with db.connect() as cx:
        cx.execute(
            "INSERT INTO workspaces(user_id,id,display_name,created_at,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(user_id,id) DO UPDATE SET updated_at=excluded.updated_at",
            (user_id, workspace_id, workspace_id, now, now),
        )


def _reject_sensitive_fields(value: Any, path: str = "snapshot") -> None:
    forbidden_names = {"secret", "secrets", "api_key", "token", "cookie", "cookies", "password", "credential", "credentials", "authorization", "private_key", "environment", "env"}
    forbidden_suffixes = ("_secret", "_api_key", "_access_token", "_refresh_token", "_password", "_cookie", "_private_key")
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in forbidden_names or normalized.endswith(forbidden_suffixes):
                raise HTTPException(400, f"sensitive field is not allowed: {path}.{key}")
            _reject_sensitive_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_fields(child, f"{path}[{index}]")


def _decode_import_files(files: list[SessionImportFile], max_bytes: int, max_files: int) -> list[tuple[str, bytes]]:
    if len(files) > max_files:
        raise HTTPException(413, "workspace file count limit exceeded")
    decoded: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    total = 0
    for item in files:
        logical_path = item.path
        parts = logical_path.split("/")
        if "\\" in logical_path or ":" in logical_path or logical_path.startswith("/") or len(parts) > 32 or any(part in ("", ".", "..") for part in parts):
            raise HTTPException(400, "invalid imported workspace path")
        if _non_shareable_path(parts):
            raise HTTPException(400, "imported workspace path is not shareable")
        if logical_path in seen:
            raise HTTPException(409, "duplicate imported workspace path")
        seen.add(logical_path)
        if item.size > max_bytes or len(item.content_base64) > ((max_bytes + 2) // 3) * 4 + 4:
            raise HTTPException(413, "workspace quota exceeded")
        try:
            content = base64.b64decode(item.content_base64 + "=" * (-len(item.content_base64) % 4), altchars=b"-_", validate=True)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, "invalid imported file content") from exc
        if len(content) != item.size or not secrets.compare_digest(hashlib.sha256(content).hexdigest(), item.sha256):
            raise HTTPException(400, "imported file integrity check failed")
        total += len(content)
        if total > max_bytes:
            raise HTTPException(413, "workspace quota exceeded")
        decoded.append((logical_path, content))
    return decoded


def _non_shareable_path(parts: list[str]) -> bool:
    """Identify local-only credentials and extension packages by path."""
    local_only_dirs = {".git", ".ssh", ".aws", ".azure", ".gnupg", "skills", "plugins", "applications", "app-packages"}
    for part in parts:
        name = part.casefold()
        if name in local_only_dirs:
            return True
        if name == ".env" or name.startswith(".env."):
            return True
        if any(fnmatch.fnmatch(name, pattern) for pattern in ("*.pem", "*.key", "*.p12", "*.pfx", "credentials*", "secrets*", "cookies*")):
            return True
    return False


def _recover_running_commands(db: CloudDB) -> list[tuple[str, str]]:
    """Fail closed only for commands whose execution lease is stale.

    A second API process may start while another process is still executing a
    command.  Recovering every ``running`` row at startup would incorrectly
    interrupt that live execution, so active leases remain untouched.
    """
    now = int(time.time())
    recovered: list[tuple[str, str]] = []
    with db.connect() as cx:
        cx.execute("BEGIN IMMEDIATE")
        rows = cx.execute("SELECT c.id,c.session_id,c.sequence FROM commands c WHERE c.status='running' AND (c.lease_expires_at IS NULL OR c.lease_expires_at<=?)", (now,)).fetchall()
        for row in rows:
            event_sequence = int(cx.execute("SELECT next_event_sequence FROM sessions WHERE id=?", (row["session_id"],)).fetchone()[0])
            payload = {"command_id": row["id"], "command_sequence": row["sequence"], "status": "needs_attention", "error": {"code": "process_restarted", "message": "Agent execution requires operator recovery"}}
            cx.execute("UPDATE commands SET status='needs_attention',lease_owner=NULL,lease_expires_at=NULL WHERE id=? AND status='running'", (row["id"],))
            cx.execute("INSERT INTO events(id,session_id,sequence,event_type,payload_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), row["session_id"], event_sequence, "turn.needs_attention", json.dumps(payload, separators=(",", ":")), now))
            cx.execute("UPDATE sessions SET next_event_sequence=?,status='idle',updated_at=? WHERE id=?", (event_sequence + 1, now, row["session_id"]))
            recovered.append((str(row["session_id"]), str(row["id"])))
        cx.execute("COMMIT")
    return recovered


def _finalize_cloud_command(db: CloudDB, session_id: str, command_id: str, status: str, payload: dict[str, Any], lease_owner: str) -> None:
    now = int(time.time())
    event_type = "turn.completed" if status == "completed" else "turn.failed"
    with db.connect() as cx:
        cx.execute("BEGIN IMMEDIATE")
        row = cx.execute("SELECT status,lease_owner FROM commands WHERE id=? AND session_id=?", (command_id, session_id)).fetchone()
        if not row or row["status"] != "running" or row["lease_owner"] != lease_owner:
            cx.execute("ROLLBACK")
            return
        event_sequence = cx.execute("SELECT next_event_sequence FROM sessions WHERE id=?", (session_id,)).fetchone()[0]
        cx.execute("UPDATE commands SET status=?,lease_owner=NULL,lease_expires_at=NULL WHERE id=? AND session_id=? AND lease_owner=?", (status, command_id, session_id, lease_owner))
        cx.execute("INSERT INTO events(id,session_id,sequence,event_type,payload_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), session_id, event_sequence, event_type, json.dumps(payload, separators=(",", ":")), now))
        usage = payload.get("usage") or {}
        if status == "completed" and usage.get("total_tokens") is not None:
            session = cx.execute("SELECT user_id,model_id FROM sessions WHERE id=?", (session_id,)).fetchone()
            if session:
                cx.execute("INSERT INTO model_usage_records(id,user_id,session_id,command_id,model_id,provider,model,prompt_tokens,completion_tokens,total_tokens,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), session["user_id"], session_id, command_id, session["model_id"], None, str(payload.get("model") or "unknown"), int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)), int(usage.get("total_tokens", 0)), now))
        cx.execute("UPDATE sessions SET next_event_sequence=?,status='idle',updated_at=? WHERE id=?", (event_sequence + 1, now, session_id))
        cx.execute("COMMIT")


def _ensure_session_worker(app: FastAPI, db: CloudDB, session_id: str, user_id: str) -> None:
    with app.state.command_locks_guard:
        worker = app.state.queue_workers.get(session_id)
        if worker is not None and worker.is_alive():
            return
        worker = threading.Thread(target=_run_session_worker, args=(app, db, session_id, user_id), name=f"notemeld-cloud-{session_id[:8]}", daemon=True)
        app.state.queue_workers[session_id] = worker
        worker.start()


@contextmanager
def _user_lock(app: FastAPI, user_id: str):
    with app.state.user_locks_guard:
        lock = app.state.user_locks.setdefault(user_id, threading.RLock())
    with lock:
        yield


@contextmanager
def _workspace_lock(app: FastAPI, user_id: str, workspace_id: str):
    """Serialize quota check and filesystem mutation within one worker.

    Filesystem writes are atomic, but quota accounting spans multiple reads and
    would otherwise admit concurrent requests that each observe stale usage.
    Multi-worker deployments still rely on the API's per-process isolation and
    should use a single writer or an external coordination layer for strict
    cross-process quota enforcement.
    """
    key = f"{user_id}\0{workspace_id}"
    with app.state.workspace_locks_guard:
        lock = app.state.workspace_locks.setdefault(key, threading.RLock())
    with _user_lock(app, user_id):
        with lock:
            root = app.state.settings.workspaces_dir / user_id / workspace_id
            with workspace_mutation_lock(root):
                yield


def _start_queued_workers(app: FastAPI, db: CloudDB) -> None:
    with db.connect() as cx:
        rows = cx.execute("SELECT DISTINCT s.id,s.user_id FROM sessions s JOIN commands c ON c.session_id=s.id WHERE c.status='queued'").fetchall()
    for row in rows:
        _ensure_session_worker(app, db, row["id"], row["user_id"])


def _start_command_reconciler(app: FastAPI, db: CloudDB) -> None:
    """Continuously fail closed commands whose worker lease has expired."""
    current = getattr(app.state, "command_reconciler", None)
    if current is not None and current.is_alive():
        return
    lease_seconds = max(1, int(getattr(app.state.settings, "command_lease_seconds", 300)))
    interval = max(1.0, min(30.0, lease_seconds / 3))

    def reconcile() -> None:
        while not app.state.worker_shutdown.wait(interval):
            try:
                recovered = _recover_running_commands(db)
            except Exception:
                LOGGER.exception("cloud command lease reconciliation failed")
                continue
            for session_id, command_id in recovered:
                _notify_command_waiter(app, session_id, command_id)

    worker = threading.Thread(
        target=reconcile,
        name="notemeld-cloud-command-reconciler",
        daemon=True,
    )
    app.state.command_reconciler = worker
    worker.start()


def _run_session_worker(app: FastAPI, db: CloudDB, session_id: str, user_id: str) -> None:
    worker_id = f"{os.getpid()}-{uuid.uuid4()}"
    try:
        shutdown = getattr(app.state, "worker_shutdown", None)
        while shutdown is None or not shutdown.is_set():
            command = _claim_next_cloud_command(db, session_id, worker_id, int(getattr(app.state.settings, "command_lease_seconds", 300)))
            if command is None:
                return
            command_id = command["id"]
            heartbeat_stop = threading.Event()
            heartbeat = threading.Thread(target=_lease_heartbeat, args=(db, session_id, command_id, worker_id, int(getattr(app.state.settings, "command_lease_seconds", 300)), heartbeat_stop), daemon=True)
            heartbeat.start()
            runner = app.state.agent_runner
            try:
                session = _owned_session(db, session_id, user_id)
                messages = _cloud_history(db, session_id, exclude_command_id=command_id)
                options = json.loads(command["options_json"] or "{}")
                tools, tool_handler = _cloud_workspace_tools(settings=app.state.settings, session=session, user_id=user_id, db=db, command_id=command_id, authorization_mode=options.get("authorization_mode", "default"), app=app)
                runner = _runner_for_session(app, db, session, command_model_id=options.get("model_id"))
                def on_native_approval(payload: dict[str, Any]) -> None:
                    _persist_native_approval(app=app, db=db, session_id=session_id, user_id=user_id, command_id=command_id, runner=runner, payload=payload)

                complete_kwargs = {
                    "input_text": command["input_text"],
                    "messages": messages + [{"role": "user", "content": command["input_text"]}],
                    "tools": tools,
                    "tool_handler": tool_handler,
                }
                if getattr(runner, "native_library", None):
                    complete_kwargs["on_approval"] = on_native_approval
                result = runner.complete(**complete_kwargs)
            except Exception as exc:
                LOGGER.exception("cloud session worker failed")
                if str(exc) == "cloud model is not configured":
                    error = {"code": "model_not_configured", "message": "configure a Cloud model before sending messages"}
                else:
                    error = {"code": "provider_unavailable", "message": "cloud agent provider unavailable"}
                _finalize_cloud_command(db, session_id, command_id, "failed", {"command_id": command_id, "command_sequence": command["sequence"], "status": "failed", "error": error}, worker_id)
            else:
                _finalize_cloud_command(db, session_id, command_id, "completed", {"command_id": command_id, "command_sequence": command["sequence"], "status": "completed", "output": result.content, "model": result.model, "usage": result.usage or {}}, worker_id)
            finally:
                heartbeat_stop.set()
                heartbeat.join(timeout=1)
                if runner is not app.state.agent_runner:
                    close = getattr(runner, "close", None)
                    if callable(close):
                        close()
                with app.state.native_approval_lock:
                    for approval_id, approval_runner in list(app.state.native_approval_runtimes.items()):
                        if approval_runner is runner:
                            app.state.native_approval_runtimes.pop(approval_id, None)
                _notify_command_waiter(app, session_id, command_id)
    finally:
        with app.state.command_locks_guard:
            current = app.state.queue_workers.get(session_id)
            if current is threading.current_thread():
                app.state.queue_workers.pop(session_id, None)


def _persist_native_approval(*, app: FastAPI, db: CloudDB, session_id: str, user_id: str, command_id: str, runner: Any, payload: dict[str, Any]) -> None:
    """Persist one canonical SDK approval without storing tool arguments."""
    approval_id = payload.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id or len(approval_id) > 128:
        LOGGER.error("canonical SDK emitted an invalid approval id")
        return
    now = int(time.time())
    with app.state.native_approval_lock:
        app.state.native_approval_runtimes[approval_id] = runner
    with db.connect() as cx:
        cx.execute(
            "INSERT OR IGNORE INTO approvals(id,user_id,session_id,command_id,tool_name,arguments_json,status,requested_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (approval_id, user_id, session_id, command_id, "agent.tool", "{}", "pending", "cloud-agent-native", now),
        )
    _audit(db, user_id, "approval.request", approval_id, {"session_id": session_id, "requested_by": "cloud-agent-native"})


def _stop_queued_workers(app: FastAPI, timeout_seconds: float = 5.0) -> None:
    """Signal cloud command workers to stop and wait for a bounded interval."""
    shutdown = getattr(app.state, "worker_shutdown", None)
    if shutdown is None:
        return
    shutdown.set()
    with app.state.command_locks_guard:
        workers = list(app.state.queue_workers.values())
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    for worker in workers:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        worker.join(timeout=remaining)
    reconciler = getattr(app.state, "command_reconciler", None)
    if reconciler is not None and reconciler is not threading.current_thread():
        reconciler.join(timeout=max(0.0, deadline - time.monotonic()))
    app.state.command_reconciler = None


def _claim_next_cloud_command(db: CloudDB, session_id: str, worker_id: str, lease_seconds: int):
    with db.connect() as cx:
        cx.execute("BEGIN IMMEDIATE")
        active = cx.execute(
            "SELECT 1 FROM commands WHERE session_id=? AND status IN ('running','needs_attention') LIMIT 1",
            (session_id,),
        ).fetchone()
        if active:
            cx.execute("COMMIT")
            return None
        row = cx.execute("SELECT id,input_text,options_json,sequence FROM commands WHERE session_id=? AND status='queued' ORDER BY sequence LIMIT 1", (session_id,)).fetchone()
        if not row:
            cx.execute("COMMIT")
            return None
        cx.execute("UPDATE commands SET status='running',lease_owner=?,lease_expires_at=?,attempt_count=attempt_count+1 WHERE id=? AND session_id=? AND status='queued'", (worker_id, int(time.time()) + max(30, lease_seconds), row["id"], session_id))
        cx.execute("UPDATE sessions SET status='running',updated_at=? WHERE id=?", (int(time.time()), session_id))
        cx.execute("COMMIT")
        return row


def _lease_heartbeat(db: CloudDB, session_id: str, command_id: str, worker_id: str, lease_seconds: int, stop: threading.Event) -> None:
    interval = max(1.0, min(30.0, lease_seconds / 3))
    while not stop.wait(interval):
        with db.connect() as cx:
            cx.execute("UPDATE commands SET lease_expires_at=? WHERE id=? AND session_id=? AND status='running' AND lease_owner=?", (int(time.time()) + max(30, lease_seconds), command_id, session_id, worker_id))


def _notify_command_waiter(app: FastAPI, session_id: str, command_id: str) -> None:
    condition = app.state.queue_conditions.get((session_id, command_id))
    if condition is not None:
        with condition:
            condition.notify_all()


def _drop_command_waiter(app: FastAPI, session_id: str, command_id: str) -> None:
    app.state.queue_conditions.pop((session_id, command_id), None)


def _submit_cloud_command(app: FastAPI, db: CloudDB, session_id: str, payload: CommandCreate, user_id: str) -> dict[str, Any]:
    session = _owned_session(db, session_id, user_id)
    if session["kind"] == "device_remote":
        raise HTTPException(409, "device_remote commands must be delivered through the host relay")
    if payload.model_id:
        with db.connect() as cx:
            if not cx.execute(
                "SELECT 1 FROM models m "
                "LEFT JOIN organization_members om ON om.organization_id=m.organization_id AND om.user_id=? "
                "WHERE m.id=? AND m.enabled=1 AND ("
                "om.user_id IS NOT NULL OR (m.organization_id IS NULL AND m.user_id=?))",
                (user_id, payload.model_id, user_id),
            ).fetchone():
                raise HTTPException(404, "enabled model not found")
    attachments = [{"name": str(item.get("name", ""))[:255], "size": int(item.get("size", 0)), "type": str(item.get("type", ""))[:128], "content_base64": item.get("content_base64")} for item in payload.attachments]
    if any(item["size"] < 0 or not item["name"] for item in attachments):
        raise HTTPException(422, "attachments must include a valid name and non-negative size")
    stored_attachments: list[dict[str, Any]] = []
    if any(item.get("content_base64") for item in attachments):
        workspace = Workspace(app.state.settings.workspaces_dir / user_id / session["workspace_id"])
        total_bytes = 0
        with workspace_mutation_lock(workspace.root):
            for index, item in enumerate(attachments):
                encoded = item.pop("content_base64", None)
                if not encoded:
                    stored_attachments.append(item)
                    continue
                try:
                    content = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise HTTPException(422, "attachment content is not valid base64") from exc
                if len(content) != item["size"] or len(content) > 10 * 1024 * 1024:
                    raise HTTPException(413, "attachment size is invalid or exceeds 10 MiB")
                total_bytes += len(content)
                if total_bytes > 20 * 1024 * 1024:
                    raise HTTPException(413, "attachments exceed the 20 MiB command limit")
                safe_name = Path(item["name"]).name
                logical_path = f"attachments/{uuid.uuid4().hex[:12]}-{safe_name}"
                workspace.write_bytes(logical_path, content)
                stored_attachments.append({**item, "path": logical_path})
    else:
        stored_attachments = [{key: value for key, value in item.items() if key != "content_base64"} for item in attachments]
    options = {"model_id": payload.model_id, "authorization_mode": payload.authorization_mode}
    digest = hashlib.sha256(json.dumps({"input": payload.input, "attachments": stored_attachments, "options": options}, sort_keys=True).encode()).hexdigest()
    now = int(time.time())
    with db.connect() as cx:
        cx.execute("BEGIN IMMEDIATE")
        existing = cx.execute("SELECT * FROM commands WHERE session_id=? AND request_id=?", (session_id, payload.request_id)).fetchone()
        if existing:
            if existing["payload_hash"] != digest:
                raise HTTPException(409, "payload conflict")
            cx.execute("COMMIT")
            return {"code": 0, "msg": "success", "data": {"command_id": existing["id"], "sequence": existing["sequence"], "status": existing["status"], "idempotent": True}}
        active = cx.execute(
            "SELECT COUNT(*) FROM commands c JOIN sessions s ON s.id=c.session_id "
            "WHERE s.user_id=? AND c.status IN ('queued','running')",
            (user_id,),
        ).fetchone()[0]
        if active >= app.state.settings.max_active_commands_per_user:
            cx.execute("ROLLBACK")
            raise HTTPException(429, "active command limit reached", headers={"Retry-After": "5"})
        sequence, event_sequence = cx.execute("SELECT next_sequence,next_event_sequence FROM sessions WHERE id=?", (session_id,)).fetchone()
        command_id = str(uuid.uuid4())
        cx.execute("UPDATE sessions SET next_sequence=?,next_event_sequence=?,status='queued',updated_at=? WHERE id=?", (sequence + 1, event_sequence + 1, now, session_id))
        cx.execute("INSERT INTO commands(id,session_id,request_id,payload_hash,sequence,input_text,attachments_json,options_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (command_id, session_id, payload.request_id, digest, sequence, payload.input, json.dumps(stored_attachments, ensure_ascii=False), json.dumps(options), "queued", now))
        queued_event = {"command_id": command_id, "command_sequence": sequence, "status": "queued"}
        cx.execute("INSERT INTO events(id,session_id,sequence,event_type,payload_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), session_id, event_sequence, "command.queued", json.dumps(queued_event), now))
        cx.execute("COMMIT")
    _ensure_session_worker(app, db, session_id, user_id)
    condition = threading.Condition()
    app.state.queue_conditions[(session_id, command_id)] = condition
    deadline = time.monotonic() + float(getattr(app.state.settings, "command_wait_seconds", 20.0))
    with condition:
        while time.monotonic() < deadline:
            with db.connect() as cx:
                row = cx.execute("SELECT sequence,status FROM commands WHERE id=? AND session_id=?", (command_id, session_id)).fetchone()
            if row and row["status"] in {"completed", "failed", "needs_attention", "abandoned"}:
                _drop_command_waiter(app, session_id, command_id)
                if row["status"] == "failed":
                    raise HTTPException(502, "cloud agent provider unavailable")
                return {"code": 0, "msg": "success", "data": {"command_id": command_id, "sequence": row["sequence"], "status": row["status"]}}
            condition.wait(timeout=max(0.01, deadline - time.monotonic()))
    with db.connect() as cx:
        row = cx.execute("SELECT sequence,status FROM commands WHERE id=? AND session_id=?", (command_id, session_id)).fetchone()
    _drop_command_waiter(app, session_id, command_id)
    return {"code": 0, "msg": "success", "data": {"command_id": command_id, "sequence": row["sequence"], "status": row["status"] if row else "queued"}}


def _open_model_stream(app: FastAPI, db: CloudDB, session: Any, command_model_id: str | None):
    """解析模型并返回 stream(messages) 生成器（OpenAI 兼容 SSE）。"""
    from .agent import stream_openai_compatible

    user_id = session["user_id"]
    selected = command_model_id or (
        session["model_id"] if "model_id" in session.keys() else None
    )
    if not selected:
        with db.connect() as cx:
            row = cx.execute(
                "SELECT m.id FROM models m "
                "LEFT JOIN organization_members om ON om.organization_id=m.organization_id AND om.user_id=? "
                "WHERE m.enabled=1 AND m.is_default=1 AND ("
                "om.user_id IS NOT NULL OR (m.organization_id IS NULL AND m.user_id=?))"
                " ORDER BY m.created_at LIMIT 1",
                (user_id, user_id),
            ).fetchone()
        if not row:
            raise RuntimeError("cloud model is not configured")
        selected = row["id"]
    with db.connect() as cx:
        model = cx.execute(
            "SELECT m.model_id AS catalog_model_id,m.model AS legacy_model,"
            "m.base_url AS legacy_base_url,m.api_key_ciphertext AS model_ciphertext,"
            "m.enabled AS enabled,p.protocol AS protocol,p.base_url AS provider_base_url,"
            "p.api_key_ciphertext AS provider_ciphertext "
            "FROM models m LEFT JOIN providers p ON p.id=m.provider_id "
            "LEFT JOIN organization_members om ON om.organization_id=m.organization_id AND om.user_id=? "
            "WHERE m.id=? AND ("
            "om.user_id IS NOT NULL OR (m.organization_id IS NULL AND m.user_id=?))",
            (user_id, selected, user_id),
        ).fetchone()
    if not model or not model["enabled"]:
        raise RuntimeError("configured session model is unavailable")
    if model["protocol"]:
        base_url = model["provider_base_url"]
        ciphertext = (
            model["model_ciphertext"]
            if model["model_ciphertext"] is not None
            else model["provider_ciphertext"]
        )
    else:
        # 旧私有行：仅接受 openai-compatible（_runner_for_session 同样约束）。
        base_url = model["legacy_base_url"]
        ciphertext = model["model_ciphertext"]
    if not base_url:
        raise RuntimeError("configured session model is unavailable")
    master_key = app.state.settings.secret_key
    if ciphertext and not master_key:
        raise RuntimeError("cloud secret key is unavailable")
    api_key = decrypt_secret(ciphertext, master_key) if ciphertext else None
    resolved_model_id = model["catalog_model_id"] or model["legacy_model"]

    def stream(messages):
        return stream_openai_compatible(
            base_url=base_url,
            model=resolved_model_id,
            api_key=api_key,
            messages=messages,
            timeout_seconds=app.state.settings.agent_timeout_seconds,
        )

    return stream


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _persist_running_command(
    db: CloudDB, session_id: str, payload: Any, user_id: str
) -> tuple[str, int]:
    """为流式轮次插入 running 命令（幂等：相同 request_id 复用）。"""
    options = {"model_id": payload.model_id, "authorization_mode": payload.authorization_mode}
    digest = hashlib.sha256(
        json.dumps({"input": payload.input, "options": options}, sort_keys=True).encode()
    ).hexdigest()
    now = int(time.time())
    with db.connect() as cx:
        cx.execute("BEGIN IMMEDIATE")
        existing = cx.execute(
            "SELECT * FROM commands WHERE session_id=? AND request_id=?",
            (session_id, payload.request_id),
        ).fetchone()
        if existing:
            cx.execute("COMMIT")
            return existing["id"], existing["sequence"]
        sequence, event_sequence = cx.execute(
            "SELECT next_sequence,next_event_sequence FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        command_id = str(uuid.uuid4())
        cx.execute(
            "UPDATE sessions SET next_sequence=?,next_event_sequence=?,status='running',updated_at=? WHERE id=?",
            (sequence + 1, event_sequence + 1, now, session_id),
        )
        cx.execute(
            "INSERT INTO commands(id,session_id,request_id,payload_hash,sequence,input_text,"
            "attachments_json,options_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (command_id, session_id, payload.request_id, digest, sequence, payload.input,
             "[]", json.dumps(options), "running", now),
        )
        queued = {"command_id": command_id, "command_sequence": sequence, "status": "running"}
        cx.execute(
            "INSERT INTO events(id,session_id,sequence,event_type,payload_json,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (str(uuid.uuid4()), session_id, event_sequence, "command.queued",
             json.dumps(queued), now),
        )
        cx.execute("COMMIT")
    return command_id, sequence


def _finalize_command_records(
    db: CloudDB, session_id: str, command_id: str, sequence: int,
    *, status: str, output: str, error: str | None,
    reasoning: list[str] | None = None,
) -> None:
    """把流式轮次落库为终态命令 + turn.completed/failed 事件。"""
    now = int(time.time())
    with db.connect() as cx:
        cx.execute("BEGIN IMMEDIATE")
        cx.execute(
            "UPDATE commands SET status=? WHERE id=? AND session_id=?",
            (status, command_id, session_id),
        )
        event_sequence = cx.execute(
            "SELECT next_event_sequence FROM sessions WHERE id=?", (session_id,)
        ).fetchone()[0]
        cx.execute(
            "UPDATE sessions SET next_event_sequence=?,status=?,updated_at=? WHERE id=?",
            (event_sequence + 1, status, now, session_id),
        )
        base = {"command_id": command_id, "command_sequence": sequence}
        if status == "completed":
            event_type = "turn.completed"
            base.update({"status": "completed", "output": output})
            if reasoning:
                base["reasoning"] = reasoning
        else:
            event_type = "turn.failed"
            base.update({"status": "failed", "error": {"code": "provider_unavailable", "message": error}})
        cx.execute(
            "INSERT INTO events(id,session_id,sequence,event_type,payload_json,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (str(uuid.uuid4()), session_id, event_sequence, event_type,
             json.dumps(base), now),
        )
        cx.execute("COMMIT")


def _cloud_history(db: CloudDB, session_id: str, *, exclude_command_id: str | None = None) -> list[dict[str, str]]:
    """Build a bounded provider history from imported messages and cloud turns."""
    messages: list[dict[str, str]] = []
    with db.connect() as cx:
        payload_row = cx.execute("SELECT payload_json FROM session_payloads WHERE session_id=?", (session_id,)).fetchone()
        commands = cx.execute("SELECT id,input_text FROM commands WHERE session_id=? ORDER BY sequence", (session_id,)).fetchall()
        events = cx.execute("SELECT payload_json FROM events WHERE session_id=? AND event_type='turn.completed' ORDER BY sequence", (session_id,)).fetchall()
    if payload_row:
        try:
            imported = json.loads(payload_row["payload_json"])
            candidate = imported.get("conversation", {}).get("messages", [])
            if isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, dict) and item.get("role") in {"system", "user", "assistant"} and isinstance(item.get("content"), str):
                        messages.append({"role": str(item["role"]), "content": item["content"]})
        except (TypeError, ValueError, AttributeError):
            messages = []
    outputs: dict[str, str] = {}
    for event in events:
        try:
            payload = json.loads(event["payload_json"])
            if isinstance(payload, dict) and isinstance(payload.get("command_id"), str) and isinstance(payload.get("output"), str):
                outputs[payload["command_id"]] = payload["output"]
        except (TypeError, ValueError):
            continue
    for command in commands:
        if exclude_command_id and command["id"] == exclude_command_id:
            continue
        messages.append({"role": "user", "content": str(command["input_text"])})
        if command["id"] in outputs:
            messages.append({"role": "assistant", "content": outputs[command["id"]]})
    # Provider requests must remain bounded even if a client imported a very
    # large historical transcript. Build from the newest messages backwards so
    # a large old import cannot crowd out the current turn context.
    bounded: list[dict[str, str]] = []
    total_chars = 0
    for message in reversed(messages):
        content = message["content"][:_MAX_HISTORY_MESSAGE_CHARS]
        remaining = _MAX_HISTORY_CHARS - total_chars
        if remaining <= 0:
            break
        content = content[:remaining]
        bounded.append({"role": message["role"], "content": content})
        total_chars += len(content)
        if len(bounded) >= _MAX_HISTORY_MESSAGES:
            break
    bounded.reverse()
    return bounded


def _execute_approved_tool(*, app: FastAPI, settings: CloudSettings, session: Any, user_id: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    workspace = Workspace(settings.workspaces_dir / user_id / str(session["workspace_id"]))
    path = arguments.get("path")
    if not isinstance(path, str) or len(path) > 1024:
        raise ValueError("invalid workspace path")
    with _workspace_lock(app, user_id, str(session["workspace_id"])):
        if tool_name == "workspace.write":
            content = arguments.get("content")
            if not isinstance(content, str):
                raise ValueError("content must be text")
            existing = workspace.path(path).stat().st_size if workspace.path(path).is_file() else 0
            projected = workspace.stats()["bytes_used"] - existing + len(content.encode("utf-8"))
            if projected > settings.max_workspace_bytes:
                raise ValueError("workspace quota exceeded")
            if existing == 0 and not workspace.path(path).exists() and workspace.stats()["file_count"] >= settings.max_workspace_files:
                raise ValueError("workspace file-count quota exceeded")
            workspace.write_text(path, content)
            return {"ok": True, "path": path, "bytes_written": len(content.encode("utf-8"))}
        if tool_name == "workspace.delete":
            workspace.delete_file(path)
            return {"ok": True, "path": path, "deleted": True}
    raise ValueError("unsupported approval tool")


def _runner_for_session(app: FastAPI, db: CloudDB, session: Any, command_model_id: str | None = None):
    """按 model_row_id（命令覆盖优先，其次会话绑定）JOIN providers 解析协议并构造 runner。

    组织目录对 member 可用；无可用模型时回退进程级 runner（仅当未配置模型凭据）。
    """
    user_id = session["user_id"]
    selected_row_id = command_model_id or (
        session["model_id"] if "model_id" in session.keys() else None
    )
    if not selected_row_id:
        with db.connect() as cx:
            default_model = cx.execute(
                "SELECT m.id FROM models m "
                "LEFT JOIN organization_members om ON om.organization_id=m.organization_id AND om.user_id=? "
                "WHERE m.enabled=1 AND m.is_default=1 AND ("
                "om.user_id IS NOT NULL OR (m.organization_id IS NULL AND m.user_id=?))"
                " ORDER BY m.created_at LIMIT 1",
                (user_id, user_id),
            ).fetchone()
        selected_row_id = default_model["id"] if default_model else None
        if not selected_row_id:
            if getattr(app.state.agent_runner, "native_library", None):
                raise RuntimeError("cloud model is not configured")
            return app.state.agent_runner
    with db.connect() as cx:
        model = cx.execute(
            "SELECT m.id,m.model_id AS catalog_model_id,m.model AS legacy_model,"
            "m.provider_id AS provider_id,m.provider AS legacy_provider,m.base_url AS legacy_base_url,"
            "m.api_key_ciphertext AS model_ciphertext,m.enabled AS enabled,"
            "p.protocol AS protocol,p.base_url AS provider_base_url,"
            "p.api_key_ciphertext AS provider_ciphertext "
            "FROM models m LEFT JOIN providers p ON p.id=m.provider_id "
            "LEFT JOIN organization_members om ON om.organization_id=m.organization_id AND om.user_id=? "
            "WHERE m.id=? AND ("
            "om.user_id IS NOT NULL OR (m.organization_id IS NULL AND m.user_id=?))",
            (user_id, selected_row_id, user_id),
        ).fetchone()
    if not model or not model["enabled"]:
        raise RuntimeError("configured session model is unavailable")
    protocol = model["protocol"]
    if protocol:
        base_url = model["provider_base_url"]
        ciphertext = (
            model["model_ciphertext"]
            if model["model_ciphertext"] is not None
            else model["provider_ciphertext"]
        )
    else:
        # 旧私有行（无 provider）：映射旧 provider 名并 fail-closed
        if model["legacy_provider"] not in {"openai", "openai-compatible"}:
            raise RuntimeError("configured session model is unavailable")
        protocol = "openai-compatible"
        base_url = model["legacy_base_url"]
        ciphertext = model["model_ciphertext"]
    if not base_url:
        raise RuntimeError("configured session model is unavailable")
    master_key = app.state.settings.secret_key
    if ciphertext and not master_key:
        raise RuntimeError("cloud secret key is unavailable")
    api_key = decrypt_secret(ciphertext, master_key) if ciphertext else None
    resolved_model_id = model["catalog_model_id"] or model["legacy_model"]
    timeout_seconds = app.state.settings.agent_timeout_seconds
    max_retries = getattr(app.state.settings, "agent_max_retries", 2)
    canonical_library = getattr(app.state.agent_runner, "native_library", None)
    if canonical_library:
        # 仅 openai-compatible 具备 canonical SDK 适配；其余协议在 SDK 模式 fail-closed
        if protocol != "openai-compatible":
            raise RuntimeError("configured session protocol is unavailable")
        from .agent import CanonicalSdkAgentRunner
        return CanonicalSdkAgentRunner(
            native_library=canonical_library,
            base_url=base_url,
            model=resolved_model_id,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
    if protocol == "openai-compatible":
        return OpenAICompatibleAgentRunner(
            base_url=base_url, model=resolved_model_id, api_key=api_key,
            timeout_seconds=timeout_seconds, max_retries=max_retries,
        )
    if protocol == "anthropic-messages":
        from .agent import AnthropicMessagesRunner
        return AnthropicMessagesRunner(
            base_url=base_url, model=resolved_model_id, api_key=api_key,
            timeout_seconds=timeout_seconds, max_retries=max_retries,
        )
    if protocol == "ollama":
        from .agent import OllamaAgentRunner
        return OllamaAgentRunner(
            base_url=base_url, model=resolved_model_id, api_key=None,
            timeout_seconds=timeout_seconds, max_retries=max_retries,
        )
    raise RuntimeError("configured session protocol is unavailable")


def _validate_model_base_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise HTTPException(422, "model base_url must be an absolute HTTP(S) URL without embedded credentials")
    if any(key.lower() in {"api_key", "apikey", "token", "password", "secret"} for key in (part.split("=", 1)[0] for part in parsed.query.split("&") if part)):
        raise HTTPException(422, "model base_url query must not contain credentials")


def _validate_provider_discovery_target(value: str) -> None:
    """Reject local/private discovery targets before making a server-side request."""
    _validate_model_base_url(value)
    parsed = urlparse(value)
    host = parsed.hostname
    if not host or host.lower() in {"localhost", "localhost.localdomain"}:
        raise HTTPException(422, "provider discovery target must be public")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(422, "provider discovery target could not be resolved") from exc
    for address_info in addresses:
        address = ipaddress.ip_address(address_info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise HTTPException(422, "provider discovery target must be public")


def _validate_lan_endpoints(value: list[str]) -> list[str]:
    if len(set(value)) != len(value):
        raise ValueError("duplicate LAN endpoint")
    result: list[str] = []
    for endpoint in value:
        if len(endpoint) > 128 or ":" not in endpoint:
            raise ValueError("LAN endpoint must be host:port")
        host, port_text = endpoint.rsplit(":", 1)
        try:
            address = ipaddress.ip_address(host.strip("[]"))
            port = int(port_text)
        except ValueError as exc:
            raise ValueError("LAN endpoint must contain a valid IP and port") from exc
        is_lan = any(
            address in network
            for network in LAN_ENDPOINT_NETWORKS
            if address.version == network.version
        )
        if (
            (address.version == 6 and not host.startswith("["))
            or "%" in host
            or not is_lan
            or address.is_unspecified
            or address.is_multicast
            or not 1 <= port <= 65535
        ):
            raise ValueError("LAN endpoint must be a private or local address")
        result.append(endpoint)
    return result


def _cloud_workspace_tools(*, settings: CloudSettings, session: Any, user_id: str, db: CloudDB | None = None, command_id: str | None = None, authorization_mode: str = "default", app: FastAPI | None = None) -> tuple[list[dict[str, Any]], Any]:
    workspace = Workspace(settings.workspaces_dir / user_id / str(session["workspace_id"]))
    tools = [
        {
            "name": "workspace.list",
            "description": "List files in the current cloud workspace.",
            "parameters": {"type": "object", "properties": {"prefix": {"type": "string"}}, "additionalProperties": False},
            "risk": "safe",
            "safe": True,
        },
        {
            "name": "workspace.read",
            "description": "Read a UTF-8 text file from the current cloud workspace.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
            "risk": "safe",
            "safe": True,
        },
    ]
    if db is not None:
        tools.extend([
            {
                "name": "workspace.write",
                "description": "Write a UTF-8 text file; always requires explicit approval.",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False},
                "risk": "high",
                "safe": False,
            },
            {
                "name": "workspace.delete",
                "description": "Delete a workspace file; always requires explicit approval.",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
                "risk": "high",
                "safe": False,
            },
        ])

    def handle(name: str, arguments: dict[str, Any]) -> Any:
        if name == "workspace.list":
            prefix = arguments.get("prefix", "")
            if not isinstance(prefix, str) or len(prefix) > 1024:
                return {"ok": False, "error": {"code": "invalid_arguments", "message": "invalid workspace prefix"}}
            files = workspace.list_files(prefix, limit=201)
            return {"ok": True, "files": files[:200], "truncated": len(files) > 200}
        if name == "workspace.read":
            path = arguments.get("path")
            if not isinstance(path, str) or len(path) > 1024:
                return {"ok": False, "error": {"code": "invalid_arguments", "message": "invalid workspace path"}}
            content, truncated = workspace.read_text_bounded(path, 100_000)
            return {"ok": True, "path": path, "content": content, "truncated": truncated}
        if name in {"workspace.write", "workspace.delete"}:
            path = arguments.get("path")
            if not isinstance(path, str) or len(path) > 1024:
                return {"ok": False, "error": {"code": "invalid_arguments", "message": "invalid workspace path"}}
            if name == "workspace.write" and not isinstance(arguments.get("content"), str):
                return {"ok": False, "error": {"code": "invalid_arguments", "message": "content must be text"}}
            if authorization_mode == "full" and app is not None:
                try:
                    result = _execute_approved_tool(app=app, settings=settings, session=session, user_id=user_id, tool_name=name, arguments=arguments)
                    _audit(db, user_id, "tool.auto_approved", command_id, {"tool_name": name, "authorization_mode": "full"})
                    return result
                except Exception as exc:
                    return {"ok": False, "error": {"code": "tool_failed", "message": str(exc)}}
            if db is None or command_id is None:
                return {"ok": False, "error": {"code": "approval_unavailable", "message": "dangerous tool approval is unavailable"}}
            arguments_json = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
            approval_id = str(uuid.uuid4())
            with db.connect() as cx:
                cx.execute("INSERT OR IGNORE INTO approvals(id,user_id,session_id,command_id,tool_name,arguments_json,status,requested_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (approval_id, user_id, str(session["id"]), command_id, name, arguments_json, "pending", "cloud-agent", int(time.time())))
                row = cx.execute("SELECT id FROM approvals WHERE session_id=? AND command_id=? AND tool_name=? AND arguments_json=?", (str(session["id"]), command_id, name, arguments_json)).fetchone()
            actual_id = row["id"] if row else approval_id
            _audit(db, user_id, "approval.request", actual_id, {"session_id": str(session["id"]), "tool_name": name})
            return {"ok": False, "requires_approval": True, "approval_id": actual_id, "error": {"code": "approval_required", "message": "explicit approval is required before this tool can execute"}}
        return {"ok": False, "error": {"code": "unknown_tool", "message": "workspace tool unavailable"}}

    return tools, handle


def _authenticate_share_token(db: CloudDB, raw: str | None, session_id: str):
    if not raw or not raw.startswith("nms_"):
        return None
    with db.connect() as cx:
        row = cx.execute("SELECT st.user_id,st.session_id,st.role,st.scopes_json,st.expires_at,st.revoked_at FROM share_tokens st JOIN users u ON u.id=st.user_id WHERE st.token_digest=? AND st.session_id=? AND u.disabled=0", (hashlib.sha256(raw.encode()).hexdigest(), session_id)).fetchone()
    if not row or row["revoked_at"] or (row["expires_at"] is not None and row["expires_at"] <= int(time.time())):
        return None
    return row


def _valid_public_key(value: str) -> bool:
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ImportError, ValueError, TypeError):
        return False
    return len(decoded) == 32


def _verify_device_proof(public_key: str, signature: str, challenge: str, device_id: str) -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        key_bytes = base64.urlsafe_b64decode(public_key + "=" * (-len(public_key) % 4))
        signature_bytes = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        message = b"notemeld-device-proof-v1\0" + device_id.encode() + b"\0" + challenge.encode()
        Ed25519PublicKey.from_public_bytes(key_bytes).verify(signature_bytes, message)
        return True
    except (ValueError, TypeError):
        return False


def _valid_nonce(value: str | None) -> bool:
    if not value or len(value) > 32 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return False
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError, TypeError):
        return False
    return len(decoded) == 12


def _audit(db: CloudDB, actor_user_id: str | None, action: str, resource_id: str | None, metadata: dict) -> None:
    with db.connect() as cx:
        cx.execute("INSERT INTO audits(id,actor_user_id,action,resource_id,metadata_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), actor_user_id, action, resource_id, json.dumps(metadata, separators=(",", ":")), int(time.time())))


def _accept_relay_sequence(db: CloudDB, session_id: str, sender_device_id: str, sequence: int) -> bool:
    now = int(time.time())
    with db.connect() as cx:
        cx.execute("BEGIN IMMEDIATE")
        row = cx.execute("SELECT last_sequence FROM relay_cursors WHERE session_id=? AND sender_device_id=?", (session_id, sender_device_id)).fetchone()
        if row and sequence <= row["last_sequence"]:
            cx.execute("ROLLBACK")
            return False
        cx.execute("INSERT INTO relay_cursors(session_id,sender_device_id,last_sequence,updated_at) VALUES(?,?,?,?) ON CONFLICT(session_id,sender_device_id) DO UPDATE SET last_sequence=excluded.last_sequence,updated_at=excluded.updated_at", (session_id, sender_device_id, sequence, now))
        cx.execute("COMMIT")
        return True


def _relay_next_sequence(db: CloudDB, session_id: str, sender_device_id: str) -> int:
    with db.connect() as cx:
        row = cx.execute(
            "SELECT last_sequence FROM relay_cursors WHERE session_id=? AND sender_device_id=?",
            (session_id, sender_device_id),
        ).fetchone()
    return int(row["last_sequence"]) + 1 if row else 1


def _grant_allows(db: CloudDB, session_id: str, user_id: str, controller: str, host: str, required_scope: str | None = None, workspace_id: str | None = None) -> bool:
    with db.connect() as cx:
        query = "SELECT g.role,g.expires_at,g.revoked_at,g.scopes_json,g.workspace_refs_json,s.kind FROM grants g JOIN sessions s ON s.user_id=g.user_id JOIN devices controller_device ON controller_device.id=g.controller_device_id AND controller_device.user_id=g.user_id AND controller_device.revoked_at IS NULL JOIN devices host_device ON host_device.id=g.host_device_id AND host_device.user_id=g.user_id AND host_device.revoked_at IS NULL WHERE g.user_id=? AND s.id=? AND g.controller_device_id=? AND g.host_device_id=? ORDER BY g.created_at DESC LIMIT 1"
        row = cx.execute(query, (user_id, session_id, controller, host)).fetchone()
        if not row and required_scope is None:
            row = cx.execute(query, (user_id, session_id, host, controller)).fetchone()
    scopes = json.loads(row["scopes_json"]) if row else []
    if row and row["role"] == "super_admin":
        scopes = list(set(scopes) | {"message.send", "context.select", "model.select", "tool.invoke", "event.receive"})
    workspace_refs = json.loads(row["workspace_refs_json"]) if row else []
    workspace_allowed = not workspace_refs or (workspace_id is not None and workspace_id in workspace_refs)
    return bool(row and row["kind"] == "device_remote" and workspace_allowed and not row["revoked_at"] and (row["expires_at"] is None or row["expires_at"] > int(time.time())) and (required_scope is None or required_scope in scopes))


def _remote_approval_allowed(db: CloudDB, session_id: str, user_id: str, controller_device_id: str) -> bool:
    """Check that a remote controller may approve host-side mutations."""
    with db.connect() as cx:
        rows = cx.execute(
            "SELECT g.expires_at,g.revoked_at,g.scopes_json FROM grants g JOIN sessions s ON s.user_id=g.user_id JOIN devices controller_device ON controller_device.id=g.controller_device_id AND controller_device.user_id=g.user_id AND controller_device.revoked_at IS NULL JOIN devices host_device ON host_device.id=g.host_device_id AND host_device.user_id=g.user_id AND host_device.revoked_at IS NULL WHERE g.user_id=? AND s.id=? AND s.kind='device_remote' AND g.controller_device_id=? ORDER BY g.created_at DESC",
            (user_id, session_id, controller_device_id),
        ).fetchall()
    now = int(time.time())
    for row in rows:
        if row["revoked_at"] or (row["expires_at"] is not None and row["expires_at"] <= now):
            continue
        scopes = set(json.loads(row["scopes_json"]))
        if "full_access" in scopes or "dangerous.approve" in scopes or "approval.remote.resolve" in scopes:
            return True
    return False
