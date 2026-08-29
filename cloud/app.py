from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from .config import CloudSettings, load_settings
from .db import CloudDB
from .security import hash_password, issue_token, parse_token, token_digest, token_expiry, verify_password
from .workspace import Workspace


class LoginRequest(BaseModel):
    username: str
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


class SessionCreate(BaseModel):
    kind: str = Field(pattern="^(cloud_native|device_remote)$")
    title: str = Field(default="New session", max_length=200)
    workspace_id: str = Field(default="default", min_length=1, max_length=128)


class CommandCreate(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    input: str = Field(min_length=1, max_length=100_000)


def create_app(settings: CloudSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    db = CloudDB(settings.database_path)
    db.init()
    settings.workspaces_dir.mkdir(parents=True, exist_ok=True)
    _bootstrap_admin(db, settings)
    app = FastAPI(title="NoteMeld Cloud", version="0.1.0")
    app.state.db = db
    app.state.settings = settings
    app.state.relays: dict[str, set[WebSocket]] = {}

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "service": "notemeld-cloud"}

    @app.post("/v1/auth/login")
    def login(payload: LoginRequest):
        user = _user_by_username(db, payload.username)
        if not user or user["disabled"] or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(401, "invalid credentials")
        raw, digest = issue_token()
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("INSERT INTO tokens(id,user_id,digest,expires_at,created_at) VALUES(?,?,?,?,?)", (raw[4:].split(".", 1)[0], user["id"], digest, token_expiry(settings.token_ttl_seconds), now))
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
                result = cx.execute(f"UPDATE users SET {assignments} WHERE id=? AND role='user'", (*changes.values(), user_id))
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(409, "username already exists") from exc
            raise
        if result.rowcount != 1:
            raise HTTPException(404, "user not found")
        return {"code": 0, "msg": "success", "data": {"id": user_id, **changes, "password_hash": None}}

    @app.delete("/v1/admin/users/{user_id}")
    def delete_user(user_id: str, current=Depends(_auth_dependency(db, "admin"))):
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            cx.execute("DELETE FROM events WHERE session_id IN (SELECT id FROM sessions WHERE user_id=?)", (user_id,))
            cx.execute("DELETE FROM commands WHERE session_id IN (SELECT id FROM sessions WHERE user_id=?)", (user_id,))
            cx.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            cx.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))
            cx.execute("DELETE FROM devices WHERE user_id=?", (user_id,))
            result = cx.execute("DELETE FROM users WHERE id=? AND role='user'", (user_id,))
            cx.execute("COMMIT")
        if result.rowcount != 1:
            raise HTTPException(404, "user not found")
        return {"code": 0, "msg": "success", "data": {"deleted": True}}

    @app.post("/v1/devices")
    def register_device(payload: DeviceCreate, current=Depends(_auth_dependency(db))):
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
            rows = cx.execute("SELECT id,public_key,platform,display_name,revoked_at,created_at FROM devices WHERE user_id=? ORDER BY created_at", (current["id"],)).fetchall()
        return {"code": 0, "msg": "success", "data": [dict(row) for row in rows]}

    @app.post("/v1/devices/{device_id}/revoke")
    def revoke_device(device_id: str, current=Depends(_auth_dependency(db))):
        with db.connect() as cx:
            result = cx.execute("UPDATE devices SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (int(time.time()), device_id, current["id"]))
        if result.rowcount != 1:
            raise HTTPException(404, "active device not found")
        return {"code": 0, "msg": "success", "data": {"device_id": device_id, "revoked": True}}

    @app.post("/v1/pairings/start")
    def start_pairing(current=Depends(_auth_dependency(db))):
        raw_code = f"{secrets.token_urlsafe(9)}"
        now = int(time.time())
        with db.connect() as cx:
            cx.execute("INSERT INTO pairings(id,user_id,code_hash,expires_at,status,created_at) VALUES(?,?,?,?,?,?)", (str(uuid.uuid4()), current["id"], hashlib.sha256(raw_code.encode()).hexdigest(), now + 300, "pending", now))
        return {"code": 0, "msg": "success", "data": {"code": raw_code, "expires_at": now + 300}}

    @app.post("/v1/pairings/confirm")
    def confirm_pairing(payload: PairingConfirm, current=Depends(_auth_dependency(db))):
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
            devices = cx.execute("SELECT id FROM devices WHERE user_id=? AND id IN (?,?) AND revoked_at IS NULL", (current["id"], payload.controller_device_id, payload.host_device_id)).fetchall()
        if len(devices) != 2:
            raise HTTPException(404, "active devices not found")
        grant_id = str(uuid.uuid4())
        with db.connect() as cx:
            cx.execute("INSERT INTO grants(id,user_id,controller_device_id,host_device_id,role,scopes_json,workspace_refs_json,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (grant_id, current["id"], payload.controller_device_id, payload.host_device_id, payload.role, json.dumps(payload.scopes), json.dumps(payload.workspace_refs), payload.expires_at, int(time.time())))
        return {"code": 0, "msg": "success", "data": {"grant_id": grant_id, "role": payload.role, "expires_at": payload.expires_at}}

    @app.post("/v1/sessions")
    def create_session(payload: SessionCreate, current=Depends(_auth_dependency(db))):
        session_id = str(uuid.uuid4())
        now = int(time.time())
        Workspace(settings.workspaces_dir / current["id"] / payload.workspace_id)
        with db.connect() as cx:
            cx.execute("INSERT INTO sessions(id,user_id,kind,title,workspace_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (session_id, current["id"], payload.kind, payload.title, payload.workspace_id, "idle", now, now))
        return {"code": 0, "msg": "success", "data": {"id": session_id, "kind": payload.kind, "workspace_id": payload.workspace_id}}

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

    @app.delete("/v1/sessions/{session_id}")
    def delete_session(session_id: str, current=Depends(_auth_dependency(db))):
        _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            cx.execute("DELETE FROM events WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM commands WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM session_archives WHERE session_id=?", (session_id,))
            cx.execute("DELETE FROM sessions WHERE id=? AND user_id=?", (session_id, current["id"]))
            cx.execute("COMMIT")
        return {"code": 0, "msg": "success", "data": {"session_id": session_id, "deleted": True}}

    @app.post("/v1/sessions/{session_id}/commands")
    def submit_command(session_id: str, payload: CommandCreate, current=Depends(_auth_dependency(db))):
        session = _owned_session(db, session_id, current["id"])
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
        return {"code": 0, "msg": "success", "data": {"command_id": command_id, "sequence": sequence, "status": "queued"}}

    @app.get("/v1/sessions/{session_id}/snapshot")
    def snapshot(session_id: str, current=Depends(_auth_dependency(db))):
        session = _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            events = cx.execute("SELECT sequence,event_type,payload_json,created_at FROM events WHERE session_id=? ORDER BY sequence", (session_id,)).fetchall()
        return {"code": 0, "msg": "success", "data": {"session": dict(session), "snapshot_seq": events[-1]["sequence"] if events else 0, "events": [{**dict(row), "payload": json.loads(row["payload_json"])} for row in events]}}

    @app.get("/v1/sessions/{session_id}/events")
    def events(session_id: str, after: int = 0, current=Depends(_auth_dependency(db))):
        _owned_session(db, session_id, current["id"])
        with db.connect() as cx:
            rows = cx.execute("SELECT sequence,event_type,payload_json,created_at FROM events WHERE session_id=? AND sequence>? ORDER BY sequence", (session_id, after)).fetchall()
        return {"code": 0, "msg": "success", "data": [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]}

    @app.websocket("/v1/relay/connect/{session_id}")
    async def relay(websocket: WebSocket, session_id: str):
        current = _authenticate_token(db, websocket.headers.get("authorization"))
        if not current or not _session_owned_by(db, session_id, current["id"]):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        peers = app.state.relays.setdefault(session_id, set())
        peers.add(websocket)
        try:
            while True:
                message = await websocket.receive_text()
                if len(message.encode()) > 256 * 1024:
                    await websocket.send_json({"type": "rejected", "error": "frame_too_large"})
                    continue
                for peer in tuple(peers):
                    if peer is not websocket:
                        await peer.send_text(message)
                await websocket.send_json({"type": "accepted"})
        except WebSocketDisconnect:
            peers.discard(websocket)
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
        return cx.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


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
