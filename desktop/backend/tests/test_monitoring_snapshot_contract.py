import pathlib
import sys
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

from app.routers import usage  # noqa: E402
from app.services.monitoring_snapshot import MonitoringSnapshotService  # noqa: E402


def test_monitoring_snapshot_uses_one_bounded_window_and_returns_component_health():
    app = FastAPI()
    app.include_router(usage.router, prefix="/api")
    app.include_router(usage.monitoring_router, prefix="/api")
    client = TestClient(app)

    with (
        patch.object(
            usage.MonitoringSnapshotService,
            "get_snapshot",
            new=AsyncMock(
                return_value={
                    "window": {"days": 1, "start_at": "2026-09-08T00:00:00+00:00", "end_at": "2026-09-08T12:00:00+00:00"},
                    "health": {"status": "degraded", "components": {"backend": "healthy", "plugins": "degraded"}},
                    "usage": {"total_tokens": 42, "record_count": 2},
                    "tasks": {"running": 1, "completed": 1, "failed": 0},
                    "runtime": {"backend": {"status": "running"}},
                    "plugins": {"ready": False, "failed_plugins": ["official.browser"]},
                }
            ),
        ) as snapshot,
    ):
        response = client.get("/api/monitoring/snapshot?days=1")

    assert response.status_code == 200
    assert response.json()["data"]["health"]["status"] == "degraded"
    assert response.json()["data"]["window"]["days"] == 1
    snapshot.assert_awaited_once_with(days=1, provider_id=None)


def test_monitoring_snapshot_rejects_an_unbounded_window():
    app = FastAPI()
    app.include_router(usage.router, prefix="/api")
    app.include_router(usage.monitoring_router, prefix="/api")
    response = TestClient(app).get("/api/monitoring/snapshot?days=0")
    assert response.status_code == 422


def test_monitoring_task_counts_preserve_aggregated_statuses():
    counts = MonitoringSnapshotService._task_counts([
        {"task_id": "failed-task", "call_count": 2, "status": "failed"},
        {"task_id": "running-task", "call_count": 1, "status": "running"},
        {"task_id": "done-task", "call_count": 3, "status": "completed"},
    ])

    assert counts == {"task_count": 3, "call_count": 6, "running": 1, "completed": 1, "failed": 1, "other": 0}


def test_monitoring_provider_counts_are_sorted_and_keep_failures():
    providers = MonitoringSnapshotService._provider_counts([
        {"provider_id": "b", "provider_name": "Provider B", "total_tokens": 10, "status": "completed"},
        {"provider_id": "a", "provider_name": "Provider A", "total_tokens": 20, "status": "failed"},
        {"provider_id": "a", "provider_name": "Provider A", "total_tokens": 5, "status": "completed"},
    ])

    assert providers == [
        {"provider_id": "a", "provider_name": "Provider A", "call_count": 2, "total_tokens": 25, "failed": 1},
        {"provider_id": "b", "provider_name": "Provider B", "call_count": 1, "total_tokens": 10, "failed": 0},
    ]
