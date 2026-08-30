from __future__ import annotations

import hashlib
import base64
import binascii
import heapq
from contextlib import asynccontextmanager
import json
import os
import secrets
import shutil
import threading
import time
import uuid
import fnmatch
import ipaddress
import re
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import CloudSettings, load_settings
from .db import CloudDB
from .agent import OpenAICompatibleAgentRunner, create_agent_runner
from .security import decrypt_secret, encrypt_secret, hash_password, issue_token, parse_token, token_digest, token_expiry, verify_password
from .workspace import Workspace
from .relay import InMemoryRelayBroker, RedisRelayBroker


TOKEN_SCOPES = frozenset({"*", "auth.token", "admin", "device.read", "device.write", "grant.read", "grant.write", "session.read", "session.write", "share.read", "share.write", "workspace.read", "workspace.write", "model.read", "model.write"})
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


class LoginRequest(BaseModel):
    username: str | None = Field(default=None, max_length=256)
    account_id: str | None = Field(default=None, max_length=128)
    password: str = Field(max_length=4096)


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


class ModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=256)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    enabled: bool = True
    is_default: bool = False


class ModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider: str | None = Field(default=None, min_length=1, max_length=64)
    model: str | None = Field(default=None, min_length=1, max_length=256)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    enabled: bool | None = None
    is_default: bool | None = None


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
    _bootstrap_admin(db, settings)
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.worker_shutdown.clear()
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
    @app.middleware("http")
    async def request_size_guard(request: Request, call_next):
        raw_length = request.headers.get("content-length")
        try:
            content_length = int(raw_length) if raw_length is not None else 0
        except ValueError:
            return JSONResponse(status_code=400, content={"code": 400, "msg": "invalid content length"})
        if content_length < 0 or content_length > settings.max_request_bytes:
            return JSONResponse(status_code=413, content={"code": 413, "msg": "request body too large"})
        original_receive = request._receive
        if raw_length is None:
            body = bytearray()
            while True:
                message = await original_receive()
                if message.get("type") != "http.request":
                    break
                body.extend(message.get("body", b""))
                if len(body) > settings.max_request_bytes:
                    return JSONResponse(status_code=413, content={"code": 413, "msg": "request body too large"})
                if not message.get("more_body", False):
                    break
            request._body = bytes(body)

            async def replay_body():
                return {"type": "http.request", "body": request._body, "more_body": False}

            request._receive = replay_body
        return await call_next(request)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Share-Token", "X-Device-Id", "X-Request-Id"])
    app.state.db = db
    app.state.settings = settings
    app.state.agent_runner = create_agent_runner(settings)
    app.state.command_locks: dict[str, threading.RLock] = {}
    app.state.command_locks_guard = threading.RLock()
    app.state.queue_workers: dict[str, threading.Thread] = {}
    app.state.queue_conditions: dict[tuple[str, str], threading.Condition] = {}
    app.state.worker_shutdown = threading.Event()

    if settings.relay_backend == "memory":
        app.state.relay_broker = InMemoryRelayBroker()
    elif settings.relay_backend == "redis":
        app.state.relay_broker = RedisRelayBroker(settings.relay_url or "", online_ttl_seconds=settings.device_online_ttl_seconds)
    else:
        raise RuntimeError(f"relay backend '{settings.relay_backend}' is not installed in this build")
    app.state.relay_sequences: dict[tuple[str, str], int] = {}
    app.state.device_challenges: dict[str, tuple[str, str, int]] = {}
    app.state.device_proofs: dict[tuple[str, str], int] = {}

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "notemeld-cloud"}

    @app.get("/ready")
    async def readiness() -> dict:
        checks: dict[str, str] = {}
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
        if any(value != "ok" for value in checks.values()):
            raise HTTPException(503, detail={"service": "notemeld-cloud", "ready": False, "checks": checks})
        return {"service": "notemeld-cloud", "ready": True, "checks": checks}

    @app.get("/v1/capabilities")
    def capabilities(current=Depends(_auth_dependency(db))):
        return {"code": 0, "msg": "success", "data": {
            "protocol_version": "notemeld.sync.v1",
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
        with db.connect() as cx:
            token_id = raw[4:].split(".", 1)[0]
            cx.execute("INSERT INTO tokens(id,user_id,digest,expires_at,audience,scopes_json,created_at) VALUES(?,?,?,?,?,?,?)", (token_id, user["id"], digest, token_expiry(settings.token_ttl_seconds), "cloud-api", '["*"]', now))
        _audit(db, user["id"], "auth.login", user["id"], {"role": user["role"]})
        return {"code": 0, "msg": "success", "data": {"token": raw, "jti": token_id, "user_id": user["id"], "role": user["role"], "audience": "cloud-api", "scopes": ["*"], "expires_at": token_expiry(settings.token_ttl_seconds)}}

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
        return {"code": 0, "msg": "success", "data": {"user_id": current["id"], "username": current["username"], "role": current["role"], "audience": current["audience"], "device_id": current["device_id"], "scopes": json.loads(current["scopes_json"]), "expires_at": current["expires_at"]}}

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
            rows = cx.execute("SELECT id,username,role,disabled,created_at FROM users ORDER BY created_at").fetchall()
        return {"code": 0, "msg": "success", "data": [dict(row) for row in rows]}

    @app.get("/v1/admin/audits")
    def list_audits(limit: int = 100, current=Depends(_auth_dependency(db, "admin", "admin"))):
        limit = max(1, min(limit, 500))
        with db.connect() as cx:
            rows = cx.execute("SELECT id,actor_user_id,action,resource_id,metadata_json,created_at FROM audits ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
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

    @app.get("/v1/models")
    def list_models(current=Depends(_auth_dependency(db, required_scope="model.read"))):
        with db.connect() as cx:
            rows = cx.execute("SELECT id,name,provider,model,base_url,enabled,is_default,created_at,updated_at,api_key_ciphertext FROM models WHERE user_id=? ORDER BY created_at", (current["id"],)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**{key: row[key] for key in ("id", "name", "provider", "model", "base_url", "enabled", "is_default", "created_at", "updated_at")}, "has_api_key": bool(row["api_key_ciphertext"])} for row in rows]}

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
            if payload.is_default:
                cx.execute("UPDATE models SET is_default=0 WHERE user_id=?", (current["id"],))
            cx.execute("INSERT INTO models(id,user_id,name,provider,model,base_url,api_key_ciphertext,enabled,is_default,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (model_id, current["id"], payload.name, payload.provider, payload.model, payload.base_url, encrypted_key, int(payload.enabled), int(payload.is_default), now, now))
            cx.execute("COMMIT")
        _audit(db, current["id"], "model.create", model_id, {"provider": payload.provider, "model": payload.model, "has_api_key": bool(payload.api_key)})
        return {"code": 0, "msg": "success", "data": {"id": model_id, "name": payload.name, "provider": payload.provider, "model": payload.model, "enabled": payload.enabled, "is_default": payload.is_default, "has_api_key": bool(payload.api_key)}}

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
            rows = cx.execute("SELECT id,public_key,platform,display_name,connectivity_json,revoked_at,last_seen_at,created_at FROM devices WHERE user_id=? ORDER BY created_at", (current["id"],)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["connectivity"] = json.loads(item.pop("connectivity_json") or "{}")
            item["online"] = bool(item["last_seen_at"] and int(time.time()) - int(item["last_seen_at"]) <= settings.device_online_ttl_seconds and not item["revoked_at"])
            result.append(item)
        return {"code": 0, "msg": "success", "data": result}

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
            cx.execute("COMMIT")
        return {"code": 0, "msg": "success", "data": {"device_id": payload.device_id, "paired": True}}

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
        if payload.model_id:
            with db.connect() as cx:
                model = cx.execute("SELECT id FROM models WHERE id=? AND user_id=? AND enabled=1", (payload.model_id, current["id"])).fetchone()
            if not model:
                raise HTTPException(404, "enabled model not found")
        Workspace(settings.workspaces_dir / current["id"] / payload.workspace_id)
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            cx.execute("INSERT INTO sessions(id,user_id,kind,title,workspace_id,status,model_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (session_id, current["id"], payload.kind, payload.title, payload.workspace_id, "idle", payload.model_id, now, now))
            cx.execute("COMMIT")
        return {"code": 0, "msg": "success", "data": {"id": session_id, "kind": payload.kind, "workspace_id": payload.workspace_id, "model_id": payload.model_id}}

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
                command_rows = cx.execute("SELECT request_id,payload_hash,sequence,input_text,status,created_at FROM commands WHERE session_id=? ORDER BY sequence", (session_id,)).fetchall()
                for row in command_rows:
                    cx.execute("INSERT INTO commands(id,session_id,request_id,payload_hash,sequence,input_text,status,created_at) VALUES(?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), new_id, row["request_id"], row["payload_hash"], row["sequence"], row["input_text"], row["status"], row["created_at"]))
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

    @app.get("/v1/workspaces/{workspace_id}/stats")
    def workspace_stats(workspace_id: str, current=Depends(_auth_dependency(db, required_scope="workspace.read"))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        return {"code": 0, "msg": "success", "data": {"workspace_id": workspace_id, **workspace.stats()}}

    @app.get("/v1/workspaces/{workspace_id}/capacity")
    def workspace_capacity(workspace_id: str, current=Depends(_auth_dependency(db, required_scope="workspace.read"))):
        """Expose quota and volume capacity so clients can render warnings."""
        _validate_workspace_id(workspace_id)
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
        destination = settings.data_dir / "backups" / current["id"] / workspace_id / f"{backup_id}.zip"
        size = workspace.create_backup(destination)
        _audit(db, current["id"], "workspace.backup.create", backup_id, {"workspace_id": workspace_id, "bytes": size})
        return {"code": 0, "msg": "success", "data": {"backup_id": backup_id, "workspace_id": workspace_id, "bytes": size, "created_at": int(time.time())}}

    @app.get("/v1/workspaces/{workspace_id}/backups")
    def list_backups(workspace_id: str, limit: int = 100, current=Depends(_auth_dependency(db, required_scope="workspace.read"))):
        _validate_workspace_id(workspace_id)
        limit = max(1, min(limit, settings.max_backup_list_items))
        directory = settings.data_dir / "backups" / current["id"] / workspace_id
        items = []
        def backup_candidates():
            if not directory.is_dir():
                return
            try:
                entries = directory.iterdir()
            except OSError:
                return
            for path in entries:
                if path.suffix != ".zip":
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                yield (stat.st_mtime, (path, stat))

        paths = heapq.nlargest(limit, backup_candidates(), key=lambda item: item[0])
        for _, (path, stat) in paths[: settings.max_backup_list_items + 1]:
            items.append({"backup_id": path.stem, "bytes": stat.st_size, "created_at": int(stat.st_mtime)})
        return {"code": 0, "msg": "success", "data": items}

    @app.delete("/v1/workspaces/{workspace_id}/backups/{backup_id}")
    def delete_backup(workspace_id: str, backup_id: str, current=Depends(_auth_dependency(db, required_scope="workspace.write"))):
        _validate_workspace_id(workspace_id)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", backup_id):
            raise HTTPException(422, "invalid backup id")
        archive = settings.data_dir / "backups" / current["id"] / workspace_id / f"{backup_id}.zip"
        try:
            archive.unlink()
        except FileNotFoundError as exc:
            raise HTTPException(404, "backup not found") from exc
        _audit(db, current["id"], "workspace.backup.delete", backup_id, {"workspace_id": workspace_id})
        return {"code": 0, "msg": "success", "data": {"backup_id": backup_id, "workspace_id": workspace_id, "deleted": True}}

    @app.post("/v1/workspaces/{workspace_id}/backups/restore")
    def restore_workspace(workspace_id: str, payload: WorkspaceRestore, current=Depends(_auth_dependency(db, required_scope="workspace.write"))):
        _validate_workspace_id(workspace_id)
        archive = settings.data_dir / "backups" / current["id"] / workspace_id / f"{payload.backup_id}.zip"
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        try:
            restored = workspace.restore_backup(archive, settings.max_workspace_bytes, settings.max_workspace_files)
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
            row = cx.execute("SELECT status FROM approvals WHERE id=? AND session_id=? AND user_id=?", (approval_id, session_id, current["id"])).fetchone()
            if not row:
                cx.execute("ROLLBACK")
                raise HTTPException(404, "approval not found")
            if row["status"] != "pending":
                cx.execute("COMMIT")
                return {"code": 0, "msg": "success", "data": {"approval_id": approval_id, "status": row["status"], "idempotent": True}}
            approval = cx.execute("SELECT tool_name,arguments_json FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if approval is None:
                cx.execute("ROLLBACK")
                raise HTTPException(404, "approval not found")
            created_at = cx.execute("SELECT created_at FROM approvals WHERE id=?", (approval_id,)).fetchone()[0]
            if created_at < now - max(1, app.state.settings.approval_ttl_seconds):
                cx.execute("UPDATE approvals SET status='expired',resolved_by=?,resolution_note='approval expired',resolved_at=? WHERE id=? AND status='pending'", (current["id"], now, approval_id))
                cx.execute("COMMIT")
                return {"code": 0, "msg": "success", "data": {"approval_id": approval_id, "status": "expired", "idempotent": True}}
            if payload.status == "approved":
                try:
                    _execute_approved_tool(settings=app.state.settings, session=session, user_id=current["id"], tool_name=approval["tool_name"], arguments=json.loads(approval["arguments_json"]))
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
            rows = cx.execute("SELECT id,session_id,request_id,sequence,status,lease_owner,lease_expires_at,attempt_count,created_at FROM commands WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT ?", (session_id, after, limit)).fetchall()
        return {"code": 0, "msg": "success", "data": [dict(row) for row in rows]}

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
            cx.execute("UPDATE sessions SET next_event_sequence=?,status=? WHERE id=?", (event_sequence + 1, "queued" if payload.mode == "resume" else "idle", session_id))
            cx.execute("COMMIT")
        if payload.mode == "resume":
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
                    if envelope.get("protocol_version") != "notemeld.sync.v1" or envelope.get("session_id") != session_id or envelope.get("sender_device_id") != device_id or not envelope.get("recipient_device_id") or not envelope.get("ciphertext") or not envelope.get("frame_id") or not _valid_nonce(envelope.get("nonce")) or frame_type not in {"command", "receipt", "event"} or not isinstance(sequence, int) or sequence < 1:
                        raise ValueError("invalid relay envelope")
                    with db.connect() as cx:
                        session_row = cx.execute("SELECT authority_epoch,workspace_id FROM sessions WHERE id=?", (session_id,)).fetchone()
                        if session_row is None:
                            raise ValueError("session unavailable")
                        epoch = session_row["authority_epoch"]
                    if envelope.get("authority_epoch") != epoch:
                        raise ValueError("stale authority epoch")
                    required_scope = {"command": "message.send", "event": "event.receive", "receipt": None}[frame_type]
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


def _bootstrap_admin(db: CloudDB, settings: CloudSettings) -> None:
    if not settings.admin_password:
        raise RuntimeError("NOTEMELD_CLOUD_ADMIN_PASSWORD must be set")
    with db.connect() as cx:
        existing = cx.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
        if not existing:
            cx.execute("INSERT INTO users(id,username,password_hash,role,created_at) VALUES(?,?,?,?,?)", (str(uuid.uuid4()), settings.admin_username, hash_password(settings.admin_password), "admin", int(time.time())))


def _user_by_username(db: CloudDB, username: str):
    with db.connect() as cx:
        rows = cx.execute("SELECT * FROM users WHERE username=? ORDER BY created_at", (username,)).fetchall()
    return rows[0] if len(rows) == 1 else None


def _user_by_account_id(db: CloudDB, account_id: str | None):
    if not account_id:
        return None
    with db.connect() as cx:
        return cx.execute("SELECT * FROM users WHERE id=?", (account_id,)).fetchone()


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


def _recover_running_commands(db: CloudDB) -> None:
    """Fail closed only for commands whose execution lease is stale.

    A second API process may start while another process is still executing a
    command.  Recovering every ``running`` row at startup would incorrectly
    interrupt that live execution, so active leases remain untouched.
    """
    now = int(time.time())
    with db.connect() as cx:
        cx.execute("BEGIN IMMEDIATE")
        rows = cx.execute("SELECT c.id,c.session_id,c.sequence,s.next_event_sequence FROM commands c JOIN sessions s ON s.id=c.session_id WHERE c.status='running' AND (c.lease_expires_at IS NULL OR c.lease_expires_at<=?)", (now,)).fetchall()
        for row in rows:
            event_sequence = int(row["next_event_sequence"])
            payload = {"command_id": row["id"], "command_sequence": row["sequence"], "status": "needs_attention", "error": {"code": "process_restarted", "message": "Agent execution requires operator recovery"}}
            cx.execute("UPDATE commands SET status='needs_attention',lease_owner=NULL,lease_expires_at=NULL WHERE id=? AND status='running'", (row["id"],))
            cx.execute("INSERT INTO events(id,session_id,sequence,event_type,payload_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), row["session_id"], event_sequence, "turn.needs_attention", json.dumps(payload, separators=(",", ":")), now))
            cx.execute("UPDATE sessions SET next_event_sequence=?,status='idle',updated_at=? WHERE id=?", (event_sequence + 1, now, row["session_id"]))
        cx.execute("COMMIT")


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


def _start_queued_workers(app: FastAPI, db: CloudDB) -> None:
    with db.connect() as cx:
        rows = cx.execute("SELECT DISTINCT s.id,s.user_id FROM sessions s JOIN commands c ON c.session_id=s.id WHERE c.status='queued'").fetchall()
    for row in rows:
        _ensure_session_worker(app, db, row["id"], row["user_id"])


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
                tools, tool_handler = _cloud_workspace_tools(settings=app.state.settings, session=session, user_id=user_id, db=db, command_id=command_id)
                runner = _runner_for_session(app, db, session)
                result = runner.complete(input_text=command["input_text"], messages=messages + [{"role": "user", "content": command["input_text"]}], tools=tools, tool_handler=tool_handler)
            except Exception:
                _finalize_cloud_command(db, session_id, command_id, "failed", {"command_id": command_id, "command_sequence": command["sequence"], "status": "failed", "error": {"code": "provider_unavailable", "message": "cloud agent provider unavailable"}}, worker_id)
            else:
                _finalize_cloud_command(db, session_id, command_id, "completed", {"command_id": command_id, "command_sequence": command["sequence"], "status": "completed", "output": result.content, "model": result.model}, worker_id)
            finally:
                heartbeat_stop.set()
                heartbeat.join(timeout=1)
                if runner is not app.state.agent_runner:
                    close = getattr(runner, "close", None)
                    if callable(close):
                        close()
                _notify_command_waiter(app, session_id, command_id)
    finally:
        with app.state.command_locks_guard:
            current = app.state.queue_workers.get(session_id)
            if current is threading.current_thread():
                app.state.queue_workers.pop(session_id, None)


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


def _claim_next_cloud_command(db: CloudDB, session_id: str, worker_id: str, lease_seconds: int):
    with db.connect() as cx:
        cx.execute("BEGIN IMMEDIATE")
        row = cx.execute("SELECT id,input_text,sequence FROM commands WHERE session_id=? AND status='queued' ORDER BY sequence LIMIT 1", (session_id,)).fetchone()
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
    digest = hashlib.sha256(payload.input.encode()).hexdigest()
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
        cx.execute("INSERT INTO commands(id,session_id,request_id,payload_hash,sequence,input_text,status,created_at) VALUES(?,?,?,?,?,?,?,?)", (command_id, session_id, payload.request_id, digest, sequence, payload.input, "queued", now))
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


def _execute_approved_tool(*, settings: CloudSettings, session: Any, user_id: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    workspace = Workspace(settings.workspaces_dir / user_id / str(session["workspace_id"]))
    path = arguments.get("path")
    if not isinstance(path, str) or len(path) > 1024:
        raise ValueError("invalid workspace path")
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


def _runner_for_session(app: FastAPI, db: CloudDB, session: Any):
    model_id = session["model_id"] if "model_id" in session.keys() else None
    if not model_id:
        return app.state.agent_runner
    with db.connect() as cx:
        model = cx.execute("SELECT provider,model,base_url,api_key_ciphertext,enabled FROM models WHERE id=? AND user_id=?", (model_id, session["user_id"])).fetchone()
    if not model or not model["enabled"] or model["provider"] not in {"openai", "openai-compatible"} or not model["base_url"]:
        raise RuntimeError("configured session model is unavailable")
    master_key = app.state.settings.secret_key
    if model["api_key_ciphertext"] and not master_key:
        raise RuntimeError("cloud secret key is unavailable")
    api_key = decrypt_secret(model["api_key_ciphertext"], master_key) if model["api_key_ciphertext"] else None
    return OpenAICompatibleAgentRunner(base_url=model["base_url"], model=model["model"], api_key=api_key, timeout_seconds=app.state.settings.agent_timeout_seconds, max_retries=getattr(app.state.settings, "agent_max_retries", 2))


def _validate_model_base_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise HTTPException(422, "model base_url must be an absolute HTTP(S) URL without embedded credentials")
    if any(key.lower() in {"api_key", "apikey", "token", "password", "secret"} for key in (part.split("=", 1)[0] for part in parsed.query.split("&") if part)):
        raise HTTPException(422, "model base_url query must not contain credentials")


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


def _cloud_workspace_tools(*, settings: CloudSettings, session: Any, user_id: str, db: CloudDB | None = None, command_id: str | None = None) -> tuple[list[dict[str, Any]], Any]:
    workspace = Workspace(settings.workspaces_dir / user_id / str(session["workspace_id"]))
    tools = [
        {
            "name": "workspace.list",
            "description": "List files in the current cloud workspace.",
            "parameters": {"type": "object", "properties": {"prefix": {"type": "string"}}, "additionalProperties": False},
        },
        {
            "name": "workspace.read",
            "description": "Read a UTF-8 text file from the current cloud workspace.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
        },
    ]
    if db is not None:
        tools.extend([
            {
                "name": "workspace.write",
                "description": "Write a UTF-8 text file; always requires explicit approval.",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False},
            },
            {
                "name": "workspace.delete",
                "description": "Delete a workspace file; always requires explicit approval.",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
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
        row = cx.execute("SELECT user_id,session_id,role,scopes_json,expires_at,revoked_at FROM share_tokens WHERE token_digest=? AND session_id=?", (hashlib.sha256(raw.encode()).hexdigest(), session_id)).fetchone()
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
