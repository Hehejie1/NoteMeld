from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import agent


class _Entry:
    def get_turn(self, turn_id: str):
        if turn_id != "turn-1":
            return None
        return {"turn_id": turn_id, "status": "completed", "session_id": "session-1"}

    def list_events(self, turn_id: str):
        assert turn_id == "turn-1"
        return [
            {"sequence": 0, "type": "turn.started"},
            {"sequence": 1, "type": "tool.completed"},
            {"sequence": 2, "type": "turn.completed"},
        ]


def test_agent_diagnostics_returns_bounded_timeline_and_last_sequence(monkeypatch):
    app = FastAPI()
    app.include_router(agent.router, prefix="/api")
    monkeypatch.setattr(agent, "_entry", _Entry())

    response = TestClient(app).get("/api/agent/v1/turns/turn-1/diagnostics")

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["turn"]["status"] == "completed"
    assert body["event_count"] == 3
    assert body["last_sequence"] == 2
    assert [event["type"] for event in body["events"]] == [
        "turn.started",
        "tool.completed",
        "turn.completed",
    ]


def test_agent_diagnostics_preserves_not_found_contract(monkeypatch):
    app = FastAPI()
    app.include_router(agent.router, prefix="/api")
    monkeypatch.setattr(agent, "_entry", _Entry())

    response = TestClient(app).get("/api/agent/v1/turns/missing/diagnostics")

    assert response.status_code == 404
