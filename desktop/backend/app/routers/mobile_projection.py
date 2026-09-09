from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.db.engine import SessionLocal
from app.db.models.mobile_projection import MobileSyncCursor, WorkspaceMemory, WorkspaceProjection
from app.utils.response import ResponseWrapper as R


router = APIRouter(prefix="/mobile")


class _StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceUpdate(_StrictPayload):
    display_name: str = Field(min_length=1, max_length=200)
    folders: list[str] = Field(default_factory=list, max_length=100)
    policies: dict[str, bool] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)


class MemoryCreate(_StrictPayload):
    workspace_id: str = Field(default="default", min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20_000)
    source: str = Field(default="user", min_length=1, max_length=100)


class SyncCursorUpdate(_StrictPayload):
    device_id: str = Field(min_length=1, max_length=200)
    workspace_id: str = Field(default="default", min_length=1, max_length=200)
    session_id: str = Field(default="", max_length=200)
    snapshot_revision: int = Field(default=0, ge=0)
    event_sequence: int = Field(default=0, ge=0)
    expected_revision: int | None = Field(default=None, ge=0)


def _decode_json(value: str, fallback):
    try:
        decoded = json.loads(value)
        return decoded
    except (TypeError, ValueError):
        return fallback


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _projection_dict(db: SessionLocal, workspace_id: str) -> dict:
    projection = db.get(WorkspaceProjection, workspace_id)
    if projection is None:
        projection = WorkspaceProjection(workspace_id=workspace_id)
        db.add(projection)
        db.commit()
        db.refresh(projection)
    memories = (
        db.query(WorkspaceMemory)
        .filter(WorkspaceMemory.workspace_id == workspace_id)
        .order_by(WorkspaceMemory.updated_at.desc(), WorkspaceMemory.memory_id.asc())
        .all()
    )
    return {
        "workspace": {
            "id": projection.workspace_id,
            "display_name": projection.display_name,
            "folders": _decode_json(projection.folders_json, []),
            "policies": _decode_json(projection.policies_json, {}),
            "revision": projection.revision,
            "updated_at": _iso(projection.updated_at),
        },
        "memories": [
            {
                "id": item.memory_id,
                "workspace_id": item.workspace_id,
                "content": item.content,
                "source": item.source,
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
            }
            for item in memories
        ],
    }


@router.get("/projection")
def get_projection(workspace_id: str = "default"):
    db = SessionLocal()
    try:
        return R.success(_projection_dict(db, workspace_id))
    finally:
        db.close()


@router.get("/sync-cursor")
def get_sync_cursor(device_id: str, workspace_id: str = "default", session_id: str = ""):
    db = SessionLocal()
    try:
        item = db.get(MobileSyncCursor, (device_id, workspace_id, session_id))
        if item is None:
            return R.success({
                "device_id": device_id,
                "workspace_id": workspace_id,
                "session_id": session_id,
                "snapshot_revision": 0,
                "event_sequence": 0,
                "updated_at": None,
            })
        return R.success({
            "device_id": item.device_id,
            "workspace_id": item.workspace_id,
            "session_id": item.session_id,
            "snapshot_revision": item.snapshot_revision,
            "event_sequence": item.event_sequence,
            "updated_at": _iso(item.updated_at),
        })
    finally:
        db.close()


@router.put("/sync-cursor")
def put_sync_cursor(data: SyncCursorUpdate):
    db = SessionLocal()
    try:
        item = db.get(MobileSyncCursor, (data.device_id, data.workspace_id, data.session_id))
        if item is None:
            if data.expected_revision not in (None, 0):
                return R.error("同步游标版本冲突", code=409, data={"snapshot_revision": 0, "event_sequence": 0})
            item = MobileSyncCursor(
                device_id=data.device_id,
                workspace_id=data.workspace_id,
                session_id=data.session_id,
            )
            db.add(item)
        elif data.expected_revision is not None and item.snapshot_revision != data.expected_revision:
            return R.error("同步游标版本冲突", code=409, data={"snapshot_revision": item.snapshot_revision, "event_sequence": item.event_sequence})
        item.snapshot_revision = data.snapshot_revision
        item.event_sequence = data.event_sequence
        db.commit()
        db.refresh(item)
        return R.success({
            "device_id": item.device_id,
            "workspace_id": item.workspace_id,
            "session_id": item.session_id,
            "snapshot_revision": item.snapshot_revision,
            "event_sequence": item.event_sequence,
            "updated_at": _iso(item.updated_at),
        })
    finally:
        db.close()


@router.put("/workspace")
def update_workspace(data: WorkspaceUpdate, workspace_id: str = "default"):
    db = SessionLocal()
    try:
        projection = db.get(WorkspaceProjection, workspace_id)
        if projection is None:
            projection = WorkspaceProjection(workspace_id=workspace_id)
            db.add(projection)
        if projection.revision != data.revision:
            return R.error("工作区已在其他设备更新", code=409, data={"revision": projection.revision})
        projection.display_name = data.display_name.strip()
        projection.folders_json = json.dumps(data.folders, ensure_ascii=False)
        projection.policies_json = json.dumps(data.policies, ensure_ascii=False)
        projection.revision += 1
        db.commit()
        return R.success(_projection_dict(db, workspace_id)["workspace"])
    finally:
        db.close()


@router.post("/memories")
def create_memory(data: MemoryCreate):
    db = SessionLocal()
    try:
        item = WorkspaceMemory(
            memory_id=f"memory_{uuid4().hex}",
            workspace_id=data.workspace_id,
            content=data.content.strip(),
            source=data.source.strip(),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return R.success({
            "id": item.memory_id,
            "workspace_id": item.workspace_id,
            "content": item.content,
            "source": item.source,
            "created_at": _iso(item.created_at),
            "updated_at": _iso(item.updated_at),
        })
    finally:
        db.close()


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str):
    db = SessionLocal()
    try:
        item = db.get(WorkspaceMemory, memory_id)
        if item is None:
            return R.error("记忆不存在", code=404)
        db.delete(item)
        db.commit()
        return R.success({"deleted": True, "id": memory_id})
    finally:
        db.close()
