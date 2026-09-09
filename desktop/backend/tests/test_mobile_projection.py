import pathlib
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

from app.db.engine import Base  # noqa: E402
from app.db.models.mobile_projection import MobileSyncCursor, WorkspaceMemory, WorkspaceProjection  # noqa: E402,F401
from app.routers import mobile_projection  # noqa: E402


def test_mobile_projection_workspace_and_memory_lifecycle(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'projection.db'}")
    Base.metadata.create_all(engine, tables=[WorkspaceProjection.__table__, WorkspaceMemory.__table__, MobileSyncCursor.__table__])
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(mobile_projection, "SessionLocal", factory)

    app = FastAPI()
    app.include_router(mobile_projection.router, prefix="/api")
    with TestClient(app) as client:
        initial = client.get("/api/mobile/projection").json()["data"]
        assert initial["workspace"]["id"] == "default"
        assert initial["workspace"]["revision"] == 1
        memory = client.post("/api/mobile/memories", json={"content": "始终使用真实 API", "source": "test"}).json()["data"]
        assert memory["content"] == "始终使用真实 API"
        updated = client.put(
            "/api/mobile/workspace?workspace_id=default",
            json={"display_name": "研究工作区", "folders": ["notes"], "policies": {"network": True}, "revision": 1},
        ).json()["data"]
        assert updated["revision"] == 2
        projection = client.get("/api/mobile/projection").json()["data"]
        assert projection["workspace"]["display_name"] == "研究工作区"
        assert projection["memories"][0]["id"] == memory["id"]
        conflict = client.put(
            "/api/mobile/workspace?workspace_id=default",
            json={"display_name": "过期写入", "folders": [], "policies": {}, "revision": 1},
        )
        assert conflict.status_code == 200
        assert conflict.json()["code"] == 409
        assert client.delete(f"/api/mobile/memories/{memory['id']}").json()["data"]["deleted"] is True


def test_mobile_sync_cursor_is_durable_and_revision_checked(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'cursor.db'}")
    Base.metadata.create_all(engine, tables=[MobileSyncCursor.__table__])
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(mobile_projection, "SessionLocal", factory)

    app = FastAPI()
    app.include_router(mobile_projection.router, prefix="/api")
    with TestClient(app) as client:
        initial = client.get("/api/mobile/sync-cursor?device_id=android-test&workspace_id=default&session_id=session-1")
        assert initial.json()["data"]["event_sequence"] == 0
        saved = client.put(
            "/api/mobile/sync-cursor",
            json={"device_id": "android-test", "workspace_id": "default", "session_id": "session-1", "snapshot_revision": 3, "event_sequence": 12, "expected_revision": 0},
        )
        assert saved.json()["data"]["event_sequence"] == 12
        conflict = client.put(
            "/api/mobile/sync-cursor",
            json={"device_id": "android-test", "workspace_id": "default", "session_id": "session-1", "snapshot_revision": 4, "event_sequence": 13, "expected_revision": 1},
        )
        assert conflict.status_code == 200
        assert conflict.json()["code"] == 409
        current = client.get("/api/mobile/sync-cursor?device_id=android-test&workspace_id=default&session_id=session-1")
        assert current.json()["data"]["snapshot_revision"] == 3
        assert current.json()["data"]["event_sequence"] == 12
