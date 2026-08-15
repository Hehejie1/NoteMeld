from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.routers import whiteboard
from app.services.whiteboard_repository import WhiteboardRepository


class _SeedService:
    def __init__(self, repository: WhiteboardRepository):
        self.repository = repository

    def ensure_from_learning_canvas(self, conversation_id: str, canvas_id: str):
        return self.repository.create(conversation_id, f"Seeded {canvas_id}")


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'whiteboard-api.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repository = WhiteboardRepository(factory)
    monkeypatch.setattr(whiteboard, "repository", repository)
    monkeypatch.setattr(whiteboard, "seed_service", _SeedService(repository))
    app = FastAPI()
    app.include_router(whiteboard.router, prefix="/api")
    try:
        yield TestClient(app), repository
    finally:
        engine.dispose()


@pytest.fixture
def seeded_board(api):
    _client, repository = api
    board = repository.create("conv_1", "Agent research", "Evidence map")
    repository.apply_mutations(
        "conv_1",
        board.id,
        board.revision,
        [
            {
                "op": "card.create",
                "card": {
                    "id": "card_seed",
                    "type": "markdown",
                    "title": "Agent loop",
                    "description": "Plan and revise",
                    "content": {"markdown": "## Agent loop"},
                    "source_refs": [],
                    "position": {"x": 0, "y": 0},
                    "size": {"width": 300, "height": 170},
                },
            }
        ],
    )
    return repository.get("conv_1", board.id)


def test_whiteboard_crud_uses_response_wrapper(api) -> None:
    client, _repository = api

    created = client.post(
        "/api/conversations/conv_1/whiteboards",
        json={"title": "Research board", "description": "Draft evidence"},
    ).json()
    board_id = created["data"]["id"]

    assert created["code"] == 0
    assert created["data"]["revision"] == 1
    listed = client.get("/api/conversations/conv_1/whiteboards").json()
    assert listed["code"] == 0
    assert listed["msg"] == "success"
    assert len(listed["data"]) == 1
    assert listed["data"][0]["id"] == board_id
    assert listed["data"][0]["title"] == "Research board"
    assert listed["data"][0]["status"] == "active"
    loaded = client.get(
        f"/api/conversations/conv_1/whiteboards/{board_id}"
    ).json()
    assert loaded == created

    deleted = client.delete(
        f"/api/conversations/conv_1/whiteboards/{board_id}"
    ).json()
    assert deleted == {"code": 0, "msg": "success", "data": {"deleted": True}}
    assert client.get("/api/conversations/conv_1/whiteboards").json()["data"] == []


def test_mutation_conflict_uses_wrapper(api, seeded_board) -> None:
    client, _repository = api

    response = client.post(
        f"/api/conversations/conv_1/whiteboards/{seeded_board.id}/mutations",
        json={"base_revision": 0, "operations": []},
    ).json()

    assert response == {
        "code": 409,
        "msg": "白板已在其他窗口更新",
        "data": {"current_revision": seeded_board.revision},
    }


def test_mutation_success_returns_wrapped_delta(api, seeded_board) -> None:
    client, _repository = api

    response = client.post(
        f"/api/conversations/conv_1/whiteboards/{seeded_board.id}/mutations",
        json={
            "base_revision": seeded_board.revision,
            "operations": [
                {
                    "op": "viewport.update",
                    "x": 10,
                    "y": -20,
                    "zoom": 1.25,
                }
            ],
        },
    ).json()

    assert response["code"] == 0
    assert response["data"]["revision"] == seeded_board.revision + 1
    assert response["data"]["viewport"] == {"x": 10.0, "y": -20.0, "zoom": 1.25}


def test_malformed_operation_keeps_fastapi_422(api, seeded_board) -> None:
    client, _repository = api

    response = client.post(
        f"/api/conversations/conv_1/whiteboards/{seeded_board.id}/mutations",
        json={"base_revision": seeded_board.revision, "operations": [{"op": "unknown"}]},
    )

    assert response.status_code == 422


def test_domain_mutation_error_uses_safe_400_wrapper(api, seeded_board) -> None:
    client, _repository = api

    response = client.post(
        f"/api/conversations/conv_1/whiteboards/{seeded_board.id}/mutations",
        json={
            "base_revision": seeded_board.revision,
            "operations": [{"op": "card.delete", "card_id": "card_absent"}],
        },
    ).json()

    assert response == {"code": 400, "msg": "白板操作无效", "data": None}


def test_context_endpoint_returns_one_authoritative_wrapped_selection(api, seeded_board) -> None:
    client, _repository = api

    response = client.post(
        f"/api/conversations/conv_1/whiteboards/{seeded_board.id}/context",
        json={
            "revision": seeded_board.revision,
            "card_ids": ["card_seed"],
            "relation_ids": [],
            "label": "Agent evidence",
        },
    ).json()

    assert response["code"] == 0
    assert response["data"]["type"] == "whiteboard_selection"
    assert response["data"]["whiteboard_id"] == seeded_board.id
    assert response["data"]["revision"] == seeded_board.revision
    assert response["data"]["card_ids"] == ["card_seed"]
    assert response["data"]["relation_ids"] == []
    assert response["data"]["label"] == "Agent evidence"
    assert "[卡片] Agent loop" in response["data"]["snapshot"]
    assert "## Agent loop" in response["data"]["snapshot"]
    assert response["data"]["source_ids"] == []


def test_context_endpoint_rejects_client_snapshot_and_source_ids(api, seeded_board) -> None:
    client, _repository = api

    response = client.post(
        f"/api/conversations/conv_1/whiteboards/{seeded_board.id}/context",
        json={
            "revision": seeded_board.revision,
            "card_ids": ["card_seed"],
            "relation_ids": [],
            "label": "Agent evidence",
            "snapshot": "FORGED",
            "source_ids": ["forged"],
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("revision_delta", "card_ids", "label"),
    [
        (-1, ["card_seed"], "Stale"),
        (0, [], "Empty"),
        (0, ["missing"], "Missing"),
    ],
)
def test_context_endpoint_rejects_stale_or_invalid_selection_with_safe_400(
    api,
    seeded_board,
    revision_delta,
    card_ids,
    label,
) -> None:
    client, _repository = api

    response = client.post(
        f"/api/conversations/conv_1/whiteboards/{seeded_board.id}/context",
        json={
            "revision": seeded_board.revision + revision_delta,
            "card_ids": card_ids,
            "relation_ids": [],
            "label": label,
        },
    ).json()

    assert response == {"code": 400, "msg": "白板操作无效", "data": None}


def test_context_endpoint_foreign_and_absent_boards_are_indistinguishable(api, seeded_board) -> None:
    client, _repository = api
    payload = {
        "revision": seeded_board.revision,
        "card_ids": ["card_seed"],
        "relation_ids": [],
        "label": "Agent evidence",
    }

    foreign = client.post(
        f"/api/conversations/conv_2/whiteboards/{seeded_board.id}/context",
        json=payload,
    ).json()
    absent = client.post(
        "/api/conversations/conv_2/whiteboards/wb_absent/context",
        json=payload,
    ).json()

    assert foreign == absent == {"code": 404, "msg": "白板不存在", "data": None}


def test_context_endpoint_enforces_selection_bounds(api, seeded_board) -> None:
    client, _repository = api

    response = client.post(
        f"/api/conversations/conv_1/whiteboards/{seeded_board.id}/context",
        json={
            "revision": seeded_board.revision,
            "card_ids": [f"card_{index}" for index in range(21)],
            "relation_ids": [],
            "label": "Too many",
        },
    )

    assert response.status_code == 422


def test_foreign_and_absent_whiteboards_are_indistinguishable(api, seeded_board) -> None:
    client, _repository = api

    foreign = client.get(
        f"/api/conversations/conv_2/whiteboards/{seeded_board.id}"
    ).json()
    absent = client.get(
        "/api/conversations/conv_2/whiteboards/wb_absent"
    ).json()

    assert foreign == absent == {"code": 404, "msg": "白板不存在", "data": None}

    foreign_delete = client.delete(
        f"/api/conversations/conv_2/whiteboards/{seeded_board.id}"
    ).json()
    absent_delete = client.delete(
        "/api/conversations/conv_2/whiteboards/wb_absent"
    ).json()
    assert foreign_delete == absent_delete == foreign

    mutation_payload = {"base_revision": seeded_board.revision, "operations": []}
    foreign_mutation = client.post(
        f"/api/conversations/conv_2/whiteboards/{seeded_board.id}/mutations",
        json=mutation_payload,
    ).json()
    absent_mutation = client.post(
        "/api/conversations/conv_2/whiteboards/wb_absent/mutations",
        json=mutation_payload,
    ).json()
    assert foreign_mutation == absent_mutation == foreign


def test_unexpected_repository_error_is_sanitized(api, monkeypatch) -> None:
    client, repository = api

    def fail(*_args, **_kwargs):
        raise RuntimeError("SELECT secret FROM /sensitive/notemeld.db")

    monkeypatch.setattr(repository, "list_for_conversation", fail)
    response = client.get("/api/conversations/conv_1/whiteboards").json()

    assert response == {"code": 500, "msg": "白板服务暂时不可用", "data": None}
    assert "sensitive" not in str(response)


def test_from_learning_canvas_uses_wrapper(api) -> None:
    client, _repository = api

    response = client.post(
        "/api/conversations/conv_1/whiteboards/from-learning-canvas/lc_1"
    ).json()

    assert response["code"] == 0
    assert response["data"]["conversation_id"] == "conv_1"
