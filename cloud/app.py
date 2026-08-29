from __future__ import annotations

import hashlib
import base64
import json
import os
import secrets
import time
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import CloudSettings, load_settings
from .db import CloudDB
from .security import hash_password, issue_token, parse_token, token_digest, token_expiry, verify_password
from .workspace import Workspace


class LoginRequest(BaseModel):
    username: str | None = None
    account_id: str | None = None
    password: str


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
    scopes: list[str] = Field(default_factory=list, max_length=32)
    workspace_refs: list[str] = Field(default_factory=list, max_length=32)
    expires_at: int | None = None


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


class DeviceKeyRotate(BaseModel):
    public_key: str


class AuthorityLease(BaseModel):
    owner: str = Field(min_length=1, max_length=128)
    ttl_seconds: int = Field(default=30, ge=5, le=300)


class SessionCreate(BaseModel):
    kind: str = Field(pattern="^(cloud_native|device_remote)$")
    title: str = Field(default="New session", max_length=200)
    workspace_id: str = Field(default="default", min_length=1, max_length=128, pattern="^[A-Za-z0-9_-]+$")


class CommandCreate(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    input: str = Field(min_length=1, max_length=100_000)


class WorkspaceWrite(BaseModel):
    content: str = Field(max_length=10_000_000)


class WorkspaceRestore(BaseModel):
    backup_id: str = Field(min_length=1, max_length=128, pattern="^[A-Za-z0-9_-]+$")


class ShareTokenCreate(BaseModel):
    session_id: str
    role: str = Field(default="viewer", pattern="^(viewer|standard|super_admin)$")
    scopes: list[str] = Field(default_factory=list, max_length=32)
    expires_at: int | None = None


def create_app(settings: CloudSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    db = CloudDB(settings.database_path)
    db.init()
    settings.workspaces_dir.mkdir(parents=True, exist_ok=True)
    _bootstrap_admin(db, settings)
    app = FastAPI(title="NoteMeld Cloud", version="0.1.0")
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Share-Token"])
    app.state.db = db
    app.state.settings = settings
    app.state.relays: dict[str, dict[str, WebSocket]] = {}
    app.state.relay_sequences: dict[tuple[str, str], int] = {}
    app.state.login_failures: dict[str, list[int]] = {}

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "notemeld-cloud"}

    @app.get("/ready")
    def readiness() -> dict:
        checks: dict[str, str] = {}
        try:
            with db.connect() as cx:
                cx.execute("SELECT 1").fetchone()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
        checks["workspace_root"] = "ok" if settings.workspaces_dir.is_dir() and os.access(settings.workspaces_dir, os.W_OK) else "error"
        if any(value != "ok" for value in checks.values()):
            raise HTTPException(503, detail={"service": "notemeld-cloud", "ready": False, "checks": checks})
        return {"service": "notemeld-cloud", "ready": True, "checks": checks}

    @app.post("/v1/auth/login")
    def login(payload: LoginRequest, request: Request):
        key = f"{request.client.host if request.client else 'unknown'}:{payload.account_id or payload.username or ''}"
        now = int(time.time())
        recent = [stamp for stamp in app.state.login_failures.get(key, []) if stamp > now - 60]
        if len(recent) >= 5:
            raise HTTPException(429, "too many login attempts")
        if not payload.username and not payload.account_id:
            raise HTTPException(400, "username or account_id is required")
        user = _user_by_account_id(db, payload.account_id) if payload.account_id else _user_by_username(db, payload.username or "")
        if not user or user["disabled"] or not verify_password(payload.password, user["password_hash"]):
            recent.append(now)
            app.state.login_failures[key] = recent
            raise HTTPException(401, "invalid credentials")
        app.state.login_failures.pop(key, None)
        raw, digest = issue_token()
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("INSERT INTO tokens(id,user_id,digest,expires_at,created_at) VALUES(?,?,?,?,?)", (raw[4:].split(".", 1)[0], user["id"], digest, token_expiry(settings.token_ttl_seconds), now))
        _audit(db, user["id"], "auth.login", user["id"], {"role": user["role"]})
        return {"code": 0, "msg": "success", "data": {"token": raw, "user_id": user["id"], "role": user["role"]}}

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
            cx.execute("INSERT INTO tokens(id,user_id,digest,expires_at,created_at) VALUES(?,?,?,?,?)", (new_id, current["id"], digest, token_expiry(settings.token_ttl_seconds), now))
            cx.execute("COMMIT")
        return {"code": 0, "msg": "success", "data": {"token": raw, "user_id": current["id"], "role": current["role"]}}

    @app.get("/v1/admin/users")
    def list_users(current=Depends(_auth_dependency(db, "admin"))):
        with db.connect() as cx:
            rows = cx.execute("SELECT id,username,role,disabled,created_at FROM users ORDER BY created_at").fetchall()
        return {"code": 0, "msg": "success", "data": [dict(row) for row in rows]}

    @app.get("/v1/admin/audits")
    def list_audits(limit: int = 100, current=Depends(_auth_dependency(db, "admin"))):
        limit = max(1, min(limit, 500))
        with db.connect() as cx:
            rows = cx.execute("SELECT id,actor_user_id,action,resource_id,metadata_json,created_at FROM audits ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]}

    @app.post("/v1/admin/users")
    def create_user(payload: UserCreate, current=Depends(_auth_dependency(db, "admin"))):
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
    def update_user(user_id: str, payload: UserUpdate, current=Depends(_auth_dependency(db, "admin"))):
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
    def delete_user(user_id: str, current=Depends(_auth_dependency(db, "admin"))):
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            cx.execute("DELETE FROM share_tokens WHERE user_id=?", (user_id,))
            cx.execute("DELETE FROM grants WHERE user_id=?", (user_id,))
            cx.execute("DELETE FROM pairings WHERE user_id=?", (user_id,))
            cx.execute("DELETE FROM events WHERE session_id IN (SELECT id FROM sessions WHERE user_id=?)", (user_id,))
            cx.execute("DELETE FROM commands WHERE session_id IN (SELECT id FROM sessions WHERE user_id=?)", (user_id,))
            cx.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            cx.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))
            cx.execute("DELETE FROM devices WHERE user_id=?", (user_id,))
            result = cx.execute("DELETE FROM users WHERE id=? AND role='user'", (user_id,))
            cx.execute("COMMIT")
        if result.rowcount != 1:
            raise HTTPException(404, "user not found")
        _audit(db, current["id"], "admin.user.delete", user_id, {})
        return {"code": 0, "msg": "success", "data": {"deleted": True}}

    @app.post("/v1/devices")
    def register_device(payload: DeviceCreate, current=Depends(_auth_dependency(db))):
        if payload.public_key is not None and not _valid_public_key(payload.public_key):
            raise HTTPException(422, "public_key must be URL-safe base64 Ed25519 key")
        now = int(time.time())
        with db.connect() as cx:
            try:
                cx.execute("INSERT INTO devices(id,user_id,public_key,platform,display_name,created_at) VALUES(?,?,?,?,?,?)", (payload.device_id, current["id"], payload.public_key, payload.platform, payload.display_name, now))
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise HTTPException(409, "device already registered") from exc
                raise
        return {"code": 0, "msg": "success", "data": {"device_id": payload.device_id}}

    @app.get("/v1/devices")
    def list_devices(current=Depends(_auth_dependency(db))):
        with db.connect() as cx:
            rows = cx.execute("SELECT id,public_key,platform,display_name,revoked_at,last_seen_at,created_at FROM devices WHERE user_id=? ORDER BY created_at", (current["id"],)).fetchall()
        return {"code": 0, "msg": "success", "data": [dict(row) for row in rows]}

    @app.post("/v1/devices/{device_id}/revoke")
    def revoke_device(device_id: str, current=Depends(_auth_dependency(db))):
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            result = cx.execute("UPDATE devices SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (int(time.time()), device_id, current["id"]))
            if result.rowcount == 1:
                cx.execute("UPDATE grants SET revoked_at=? WHERE user_id=? AND (controller_device_id=? OR host_device_id=?) AND revoked_at IS NULL", (int(time.time()), current["id"], device_id, device_id))
            cx.execute("COMMIT")
        if result.rowcount != 1:
            raise HTTPException(404, "active device not found")
        _audit(db, current["id"], "device.revoke", device_id, {"grants_revoked": True})
        return {"code": 0, "msg": "success", "data": {"device_id": device_id, "revoked": True}}

    @app.post("/v1/devices/{device_id}/rotate-key")
    def rotate_device_key(device_id: str, payload: DeviceKeyRotate, current=Depends(_auth_dependency(db))):
        if not _valid_public_key(payload.public_key):
            raise HTTPException(422, "public_key must be URL-safe base64 Ed25519 key")
        with db.connect() as cx:
            result = cx.execute("UPDATE devices SET public_key=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (payload.public_key, device_id, current["id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "active device not found")
        _audit(db, current["id"], "device.key.rotate", device_id, {})
        return {"code": 0, "msg": "success", "data": {"device_id": device_id, "rotated": True}}

    @app.post("/v1/devices/{device_id}/heartbeat")
    def device_heartbeat(device_id: str, current=Depends(_auth_dependency(db))):
        now = int(time.time())
        with db.connect() as cx:
            result = cx.execute("UPDATE devices SET last_seen_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (now, device_id, current["id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "active device not found")
        return {"code": 0, "msg": "success", "data": {"device_id": device_id, "last_seen_at": now}}

    @app.post("/v1/pairings/start")
    def start_pairing(current=Depends(_auth_dependency(db))):
        raw_code = f"{secrets.token_urlsafe(9)}"
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("INSERT INTO pairings(id,user_id,code_hash,expires_at,status,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), current["id"], hashlib.sha256(raw_code.encode()).hexdigest(), now + 300, "pending", now))
        return {"code": 0, "msg": "success", "data": {"code": raw_code, "expires_at": now + 300}}

    @app.post("/v1/pairings/confirm")
    def confirm_pairing(payload: PairingConfirm, current=Depends(_auth_dependency(db))):
        if payload.public_key is not None and not _valid_public_key(payload.public_key):
            raise HTTPException(422, "public_key must be URL-safe base64 Ed25519 key")
        digest = hashlib.sha256(payload.code.encode()).hexdigest()
        now = int(time.time())
        with db.connect() as cx:
            pairing = cx.execute("SELECT * FROM pairings WHERE code_hash=? AND status='pending' AND expires_at>? AND user_id=?", (digest, now, current["id"])).fetchone()
            if not pairing:
                raise HTTPException(400, "pairing code expired or invalid")
            cx.execute("INSERT OR REPLACE INTO devices(id,user_id,public_key,platform,display_name,created_at) VALUES(?,?,?,?,?,?)", (payload.device_id, current["id"], payload.public_key, payload.platform, payload.display_name, now))
            cx.execute("UPDATE pairings SET status='confirmed',device_id=? WHERE id=?", (payload.device_id, pairing["id"]))
        return {"code": 0, "msg": "success", "data": {"device_id": payload.device_id, "paired": True}}

    @app.post("/v1/grants")
    def create_grant(payload: GrantCreate, current=Depends(_auth_dependency(db))):
        if payload.role == "super_admin" and current["role"] != "admin":
            raise HTTPException(403, "permission denied")
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
    def list_grants(current=Depends(_auth_dependency(db))):
        with db.connect() as cx:
            rows = cx.execute("SELECT id,controller_device_id,host_device_id,role,scopes_json,workspace_refs_json,expires_at,revoked_at,created_at FROM grants WHERE user_id=? ORDER BY created_at DESC", (current["id"],)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "scopes": json.loads(row["scopes_json"]), "workspace_refs": json.loads(row["workspace_refs_json"])} for row in rows]}

    @app.post("/v1/grants/{grant_id}/revoke")
    def revoke_grant(grant_id: str, current=Depends(_auth_dependency(db))):
        with db.connect() as cx:
            result = cx.execute("UPDATE grants SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (int(time.time()), grant_id, current["id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "active grant not found")
        _audit(db, current["id"], "grant.revoke", grant_id, {})
        return {"code": 0, "msg": "success", "data": {"grant_id": grant_id, "revoked": True}}

    @app.post("/v1/share-tokens")
    def create_share_token(payload: ShareTokenCreate, current=Depends(_auth_dependency(db))):
        _owned_session(db, payload.session_id, current["id"])
        if payload.role == "super_admin" and current["role"] != "admin":
            raise HTTPException(403, "permission denied")
        raw = "nms_" + secrets.token_urlsafe(32)
        token_id = str(uuid.uuid4())
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("INSERT INTO share_tokens(id,user_id,session_id,token_digest,role,scopes_json,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?)", (token_id, current["id"], payload.session_id, hashlib.sha256(raw.encode()).hexdigest(), payload.role, json.dumps(payload.scopes), payload.expires_at, now))
        _audit(db, current["id"], "share_token.create", token_id, {"session_id": payload.session_id, "role": payload.role, "scopes": payload.scopes, "permanent": payload.expires_at is None})
        return {"code": 0, "msg": "success", "data": {"id": token_id, "token": raw, "session_id": payload.session_id, "role": payload.role, "scopes": payload.scopes, "expires_at": payload.expires_at}}

    @app.get("/v1/share-tokens")
    def list_share_tokens(current=Depends(_auth_dependency(db))):
        with db.connect() as cx:
            rows = cx.execute("SELECT id,session_id,role,scopes_json,expires_at,revoked_at,created_at FROM share_tokens WHERE user_id=? ORDER BY created_at DESC", (current["id"],)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "scopes": json.loads(row["scopes_json"])} for row in rows]}

    @app.post("/v1/share-tokens/{token_id}/revoke")
    def revoke_share_token(token_id: str, current=Depends(_auth_dependency(db))):
        with db.connect() as cx:
            result = cx.execute("UPDATE share_tokens SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (int(time.time()), token_id, current["id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "active share token not found")
        _audit(db, current["id"], "share_token.revoke", token_id, {})
        return {"code": 0, "msg": "success", "data": {"id": token_id, "revoked": True}}

    @app.post("/v1/sessions")
    def create_session(payload: SessionCreate, current=Depends(_auth_dependency(db))):
        session_id = str(uuid.uuid4())
        now = int(time.time())
        Workspace(settings.workspaces_dir / current["id"] / payload.workspace_id)
        with db.connect() as cx:
            cx.execute("INSERT INTO sessions(id,user_id,kind,title,workspace_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (session_id, current["id"], payload.kind, payload.title, payload.workspace_id, "idle", now, now))
        return {"code": 0, "msg": "success", "data": {"id": session_id, "kind": payload.kind, "workspace_id": payload.workspace_id}}

    @app.post("/v1/sessions/{session_id}/copy")
    def copy_session(session_id: str, current=Depends(_auth_dependency(db))):
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
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            cx.execute("INSERT INTO sessions(id,user_id,kind,title,workspace_id,status,copied_from,created_at,updated_at,next_sequence,next_event_sequence,authority_epoch) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (new_id, current["id"], source["kind"], f"Copy of {source['title']}", workspace_id, "idle", session_id, now, now, source["next_sequence"], source["next_event_sequence"], 1))
            cx.execute("INSERT INTO commands SELECT ?,?,request_id,payload_hash,sequence,input_text,status,created_at FROM commands WHERE session_id=?", (str(uuid.uuid4()), new_id, session_id))
            rows = cx.execute("SELECT sequence,event_type,payload_json,created_at FROM events WHERE session_id=? ORDER BY sequence", (session_id,)).fetchall()
            for row in rows:
                cx.execute("INSERT INTO events(id,session_id,sequence,event_type,payload_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), new_id, row["sequence"], row["event_type"], row["payload_json"], row["created_at"]))
            cx.execute("COMMIT")
        return {"code": 0, "msg": "success", "data": {"id": new_id, "copied_from": session_id, "workspace_id": workspace_id, **copied_files}}

    @app.post("/v1/sessions/{session_id}/authority/rotate")
    def rotate_authority(session_id: str, current=Depends(_auth_dependency(db))):
        _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            cx.execute("UPDATE sessions SET authority_epoch=authority_epoch+1,updated_at=? WHERE id=?", (int(time.time()), session_id))
            epoch = cx.execute("SELECT authority_epoch FROM sessions WHERE id=?", (session_id,)).fetchone()[0]
        _audit(db, current["id"], "session.authority.rotate", session_id, {"authority_epoch": epoch})
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "authority_epoch": epoch}}

    @app.post("/v1/sessions/{session_id}/authority/lease")
    def acquire_authority_lease(session_id: str, payload: AuthorityLease, current=Depends(_auth_dependency(db))):
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
    def release_authority_lease(session_id: str, owner: str, current=Depends(_auth_dependency(db))):
        _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            result = cx.execute("UPDATE sessions SET lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=? AND lease_owner=?", (int(time.time()), session_id, owner))
        if result.rowcount != 1:
            raise HTTPException(409, "lease owner mismatch or lease is not held")
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "released": True}}

    @app.get("/v1/workspaces/{workspace_id}/stats")
    def workspace_stats(workspace_id: str, current=Depends(_auth_dependency(db))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        return {"code": 0, "msg": "success", "data": {"workspace_id": workspace_id, **workspace.stats()}}

    @app.get("/v1/workspaces/{workspace_id}/files/{logical_path:path}")
    def read_workspace_file(workspace_id: str, logical_path: str, current=Depends(_auth_dependency(db))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        try:
            content = workspace.read_text(logical_path)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"code": 0, "msg": "success", "data": {"workspace_id": workspace_id, "path": logical_path, "content": content}}

    @app.get("/v1/workspaces/{workspace_id}/files")
    def list_workspace_files(workspace_id: str, prefix: str = "", current=Depends(_auth_dependency(db))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        try:
            files = workspace.list_files(prefix)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"code": 0, "msg": "success", "data": {"workspace_id": workspace_id, "files": files}}

    @app.put("/v1/workspaces/{workspace_id}/files/{logical_path:path}")
    def write_workspace_file(workspace_id: str, logical_path: str, payload: WorkspaceWrite, current=Depends(_auth_dependency(db))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        try:
            existing_size = workspace.path(logical_path).stat().st_size if workspace.path(logical_path).is_file() else 0
            projected = workspace.stats()["bytes_used"] - existing_size + len(payload.content.encode("utf-8"))
            if projected > settings.max_workspace_bytes:
                raise HTTPException(413, "workspace quota exceeded")
            workspace.write_text(logical_path, payload.content)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"code": 0, "msg": "success", "data": {"workspace_id": workspace_id, "path": logical_path, "bytes_written": len(payload.content.encode("utf-8"))}}

    @app.delete("/v1/workspaces/{workspace_id}/files/{logical_path:path}")
    def delete_workspace_file(workspace_id: str, logical_path: str, current=Depends(_auth_dependency(db))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        try:
            workspace.delete_file(logical_path)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"code": 0, "msg": "success", "data": {"workspace_id": workspace_id, "path": logical_path, "deleted": True}}

    @app.post("/v1/workspaces/{workspace_id}/backups")
    def backup_workspace(workspace_id: str, current=Depends(_auth_dependency(db))):
        _validate_workspace_id(workspace_id)
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        backup_id = f"{int(time.time())}-{secrets.token_urlsafe(8)}"
        destination = settings.data_dir / "backups" / current["id"] / workspace_id / f"{backup_id}.zip"
        size = workspace.create_backup(destination)
        return {"code": 0, "msg": "success", "data": {"backup_id": backup_id, "workspace_id": workspace_id, "bytes": size, "created_at": int(time.time())}}

    @app.get("/v1/workspaces/{workspace_id}/backups")
    def list_backups(workspace_id: str, current=Depends(_auth_dependency(db))):
        _validate_workspace_id(workspace_id)
        directory = settings.data_dir / "backups" / current["id"] / workspace_id
        items = []
        for path in sorted(directory.glob("*.zip")) if directory.is_dir() else []:
            items.append({"backup_id": path.stem, "bytes": path.stat().st_size, "created_at": int(path.stat().st_mtime)})
        return {"code": 0, "msg": "success", "data": items}

    @app.post("/v1/workspaces/{workspace_id}/backups/restore")
    def restore_workspace(workspace_id: str, payload: WorkspaceRestore, current=Depends(_auth_dependency(db))):
        _validate_workspace_id(workspace_id)
        archive = settings.data_dir / "backups" / current["id"] / workspace_id / f"{payload.backup_id}.zip"
        workspace = Workspace(settings.workspaces_dir / current["id"] / workspace_id)
        try:
            restored = workspace.restore_backup(archive, settings.max_workspace_bytes)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"code": 0, "msg": "success", "data": {"backup_id": payload.backup_id, "workspace_id": workspace_id, **restored}}

    @app.get("/v1/sessions")
    def list_sessions(current=Depends(_auth_dependency(db))):
        with db.connect() as cx:
            rows = cx.execute("SELECT s.*, a.archived_at FROM sessions s LEFT JOIN session_archives a ON a.session_id=s.id AND a.user_id=? WHERE s.user_id=? ORDER BY s.updated_at DESC", (current["id"], current["id"])).fetchall()
        return {"code": 0, "msg": "success", "data": [dict(row) for row in rows]}

    @app.post("/v1/sessions/{session_id}/archive")
    def archive_session(session_id: str, current=Depends(_auth_dependency(db))):
        _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            cx.execute("INSERT OR REPLACE INTO session_archives(user_id,session_id,archived_at) VALUES(?,?,?)", (current["id"], session_id, int(time.time())))
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "archived": True}}

    @app.post("/v1/sessions/{session_id}/restore")
    def restore_session(session_id: str, current=Depends(_auth_dependency(db))):
        _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            result = cx.execute("DELETE FROM session_archives WHERE session_id=? AND user_id=?", (session_id, current["id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "archived session not found")
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "archived": False}}

    @app.delete("/v1/sessions/{session_id}")
    def delete_session(session_id: str, current=Depends(_auth_dependency(db))):
        _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            cx.execute("DELETE FROM events WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM commands WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM share_tokens WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM session_archives WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM sessions WHERE id=? AND user_id=?", (session_id, current["id"]))
            cx.execute("COMMIT")
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "deleted": True}}

    @app.post("/v1/sessions/{session_id}/commands")
    def submit_command(session_id: str, payload: CommandCreate, current=Depends(_auth_dependency(db))):
        session = _owned_session(db, session_id, current["id"])
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
            sequence, event_sequence = cx.execute("SELECT next_sequence,next_event_sequence FROM sessions WHERE id=?", (session_id,)).fetchone()
            command_id = str(uuid.uuid4())
            cx.execute("UPDATE sessions SET next_sequence=?,next_event_sequence=?,status='running',updated_at=? WHERE id=?", (sequence + 1, event_sequence + 2, now, session_id))
            cx.execute("INSERT INTO commands(id,session_id,request_id,payload_hash,sequence,input_text,status,created_at) VALUES(?,?,?,?,?,?,?,?)", (command_id, session_id, payload.request_id, digest, sequence, payload.input, "completed", now))
            queued_event = {"command_id": command_id, "command_sequence": sequence, "status": "queued"}
            cx.execute("INSERT INTO events(id,session_id,sequence,event_type,payload_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), session_id, event_sequence, "command.queued", json.dumps(queued_event), now))
            completed_event = {"command_id": command_id, "command_sequence": sequence, "status": "completed", "output": f"Cloud Agent received: {payload.input}"}
            cx.execute("INSERT INTO events(id,session_id,sequence,event_type,payload_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), session_id, event_sequence + 1, "turn.completed", json.dumps(completed_event), now))
            cx.execute("UPDATE sessions SET status='idle',updated_at=? WHERE id=?", (now, session_id))
            cx.execute("COMMIT")
        return {"code": 0, "msg": "success", "data": {"command_id": command_id, "sequence": sequence, "status": "completed"}}

    @app.get("/v1/sessions/{session_id}/commands/{command_id}")
    def command_status(session_id: str, command_id: str, current=Depends(_auth_dependency(db))):
        _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            row = cx.execute("SELECT id,session_id,request_id,sequence,status,created_at FROM commands WHERE id=? AND session_id=?", (command_id, session_id)).fetchone()
        if not row:
            raise HTTPException(404, "command not found")
        return {"code": 0, "msg": "success", "data": dict(row)}

    @app.get("/v1/sessions/{session_id}/commands")
    def list_commands(session_id: str, after: int = 0, limit: int = 100, current=Depends(_auth_dependency(db))):
        _owned_session(db, session_id, current["id"])
        limit = max(1, min(limit, 500))
        with db.connect() as cx:
            rows = cx.execute("SELECT id,session_id,request_id,sequence,status,created_at FROM commands WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT ?", (session_id, after, limit)).fetchall()
        return {"code": 0, "msg": "success", "data": [dict(row) for row in rows]}

    @app.get("/v1/sessions/{session_id}/snapshot")
    def snapshot(session_id: str, current=Depends(_auth_dependency(db))):
        session = _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            events = cx.execute("SELECT sequence,event_type,payload_json,created_at FROM events WHERE session_id=? ORDER BY sequence", (session_id,)).fetchall()
        return {"code": 0, "msg": "success", "data": {"session": dict(session), "snapshot_seq": events[-1]["sequence"] if events else 0, "events": [{**dict(row), "payload": json.loads(row["payload_json"])} for row in events]}}

    @app.get("/v1/shared/{session_id}/snapshot")
    def shared_snapshot(session_id: str, share_token: Annotated[str | None, Header(alias="X-Share-Token")] = None):
        access = _authenticate_share_token(db, share_token, session_id)
        if not access:
            raise HTTPException(401, "invalid share token")
        return snapshot(session_id, current={"id": access["user_id"]})

    @app.get("/v1/shared/{session_id}/events")
    def shared_events(session_id: str, after: int = 0, share_token: Annotated[str | None, Header(alias="X-Share-Token")] = None):
        access = _authenticate_share_token(db, share_token, session_id)
        if not access:
            raise HTTPException(401, "invalid share token")
        _owned_session(db, session_id, access["user_id"])
        with db.connect() as cx:
            rows = cx.execute("SELECT sequence,event_type,payload_json,created_at FROM events WHERE session_id=? AND sequence>? ORDER BY sequence", (session_id, after)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]}

    @app.post("/v1/shared/{session_id}/commands")
    def shared_command(session_id: str, payload: CommandCreate, share_token: Annotated[str | None, Header(alias="X-Share-Token")] = None):
        access = _authenticate_share_token(db, share_token, session_id)
        if not access:
            raise HTTPException(401, "invalid share token")
        scopes = json.loads(access["scopes_json"])
        if access["role"] == "viewer" or "message.send" not in scopes:
            raise HTTPException(403, "share token cannot send messages")
        return submit_command(session_id, payload, current={"id": access["user_id"]})

    @app.get("/v1/sessions/{session_id}/events")
    def events(session_id: str, after: int = 0, current=Depends(_auth_dependency(db))):
        _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            rows = cx.execute("SELECT sequence,event_type,payload_json,created_at FROM events WHERE session_id=? AND sequence>? ORDER BY sequence", (session_id, after)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]}

    @app.websocket("/v1/relay/connect/{session_id}")
    async def relay(websocket: WebSocket, session_id: str):
        current = _authenticate_token(db, websocket.headers.get("authorization"))
        device_id = websocket.query_params.get("device_id")
        if not current or not device_id or not _session_owned_by(db, session_id, current["id"]) or not _active_device_owned(db, device_id, current["id"]):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        with db.connect() as cx:
            cx.execute("UPDATE devices SET last_seen_at=? WHERE id=?", (int(time.time()), device_id))
        peers = app.state.relays.setdefault(session_id, {})
        previous = peers.get(device_id)
        if previous is not None and previous is not websocket:
            await previous.close(code=4009, reason="replaced by a newer connection")
        peers[device_id] = websocket
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
                if len(message.encode()) > 256 * 1024:
                    await websocket.send_json({"type": "rejected", "error": "frame_too_large"})
                    continue
                try:
                    envelope = json.loads(message)
                    sequence = envelope.get("sequence")
                    frame_type = envelope.get("frame_type", "command")
                    if envelope.get("protocol_version") != "notemeld.sync.v1" or envelope.get("session_id") != session_id or envelope.get("sender_device_id") != device_id or not envelope.get("recipient_device_id") or not envelope.get("ciphertext") or not envelope.get("frame_id") or not _valid_nonce(envelope.get("nonce")) or frame_type not in {"command", "receipt", "event"} or not isinstance(sequence, int) or sequence < 1:
                        raise ValueError("invalid relay envelope")
                    with db.connect() as cx:
                        epoch = cx.execute("SELECT authority_epoch FROM sessions WHERE id=?", (session_id,)).fetchone()[0]
                    if envelope.get("authority_epoch") != epoch:
                        raise ValueError("stale authority epoch")
                    required_scope = "message.send" if frame_type == "command" else None
                    if not _grant_allows(db, session_id, current["id"], device_id, envelope["recipient_device_id"], required_scope):
                        raise ValueError("relay grant missing")
                    replay_key = (session_id, device_id)
                    if sequence <= app.state.relay_sequences.get(replay_key, 0):
                        raise ValueError("replayed relay envelope")
                    app.state.relay_sequences[replay_key] = sequence
                except (ValueError, json.JSONDecodeError, TypeError):
                    await websocket.send_json({"type": "rejected", "error": "invalid_envelope"})
                    continue
                peer = peers.get(envelope["recipient_device_id"])
                if peer is None or peer is websocket:
                    await websocket.send_json({"type": "failed", "error": "host_offline", "frame_id": envelope["frame_id"]})
                    continue
                await peer.send_text(message)
                await websocket.send_json({"type": "relay_accepted", "frame_id": envelope["frame_id"]})
        except WebSocketDisconnect:
            if peers.get(device_id) is websocket:
                peers.pop(device_id, None)
            if not peers:
                app.state.relays.pop(session_id, None)

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


def _auth_dependency(db: CloudDB, required_role: str | None = None):
    def dependency(authorization: Annotated[str | None, Header()] = None):
        row = _authenticate_token(db, authorization)
        if not row:
            raise HTTPException(401, "invalid token")
        if required_role and row["role"] != required_role:
            raise HTTPException(403, "permission denied")
        return row
    return dependency


def _authenticate_token(db: CloudDB, authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    parsed = parse_token(authorization[7:].strip())
    if not parsed:
        return None
    token_id, secret = parsed
    with db.connect() as cx:
        row = cx.execute("SELECT u.*,t.expires_at,t.revoked_at FROM tokens t JOIN users u ON u.id=t.user_id WHERE t.id=? AND t.digest=?", (token_id, token_digest(token_id, secret))).fetchone()
    if not row or row["revoked_at"] or row["disabled"] or (row["expires_at"] and row["expires_at"] < int(time.time())):
        return None
    return row


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


def _validate_workspace_id(workspace_id: str) -> None:
    if not workspace_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in workspace_id):
        raise HTTPException(400, "invalid workspace id")


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
    except (ValueError, TypeError):
        return False
    return len(decoded) == 32


def _valid_nonce(value: str | None) -> bool:
    if not value:
        return False
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError):
        return False
    return len(decoded) == 12


def _audit(db: CloudDB, actor_user_id: str | None, action: str, resource_id: str | None, metadata: dict) -> None:
    with db.connect() as cx:
        cx.execute("INSERT INTO audits(id,actor_user_id,action,resource_id,metadata_json,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), actor_user_id, action, resource_id, json.dumps(metadata, separators=(",", ":")), int(time.time())))


def _grant_allows(db: CloudDB, session_id: str, user_id: str, controller: str, host: str, required_scope: str | None = None) -> bool:
    with db.connect() as cx:
        row = cx.execute("SELECT g.expires_at,g.revoked_at,g.scopes_json,s.kind FROM grants g JOIN sessions s ON s.user_id=g.user_id WHERE g.user_id=? AND s.id=? AND g.controller_device_id=? AND g.host_device_id=? ORDER BY g.created_at DESC LIMIT 1", (user_id, session_id, controller, host)).fetchone()
        if not row and required_scope is None:
            row = cx.execute("SELECT g.expires_at,g.revoked_at,g.scopes_json,s.kind FROM grants g JOIN sessions s ON s.user_id=g.user_id WHERE g.user_id=? AND s.id=? AND g.controller_device_id=? AND g.host_device_id=? ORDER BY g.created_at DESC LIMIT 1", (user_id, session_id, host, controller)).fetchone()
    scopes = json.loads(row["scopes_json"]) if row else []
    return bool(row and row["kind"] == "device_remote" and not row["revoked_at"] and (row["expires_at"] is None or row["expires_at"] > int(time.time())) and (required_scope is None or required_scope in scopes))
