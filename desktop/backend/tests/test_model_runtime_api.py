from __future__ import annotations

from collections.abc import Generator
from unittest.mock import ANY

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import model_capability_dao, model_dao
from app.db.engine import Base
from app.db.models.conversation import NoteDocument
from app.db.models.model_usage_records import ModelUsageRecord
from app.db.models.models import ModelCapability
from app.db.models.providers import Provider
from app.routers import model as model_router
from app.services import model as model_service


def _session_dependency(session_factory) -> Generator:
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def runtime_api(monkeypatch, tmp_path):
    """Route tests use a real isolated SQLite database behind the model DAOs."""
    engine = create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def get_test_db():
        yield from _session_dependency(session_factory)

    monkeypatch.setattr(model_dao, "get_db", get_test_db)
    monkeypatch.setattr(model_capability_dao, "get_db", get_test_db)
    monkeypatch.setattr(model_service, "get_model_by_provider_and_name", model_dao.get_model_by_provider_and_name)
    monkeypatch.setattr(model_service, "insert_model", model_dao.insert_model)
    monkeypatch.setattr(model_service, "delete_model_with_capability", model_dao.delete_model_with_capability)

    def get_provider(provider_id: str):
        with session_factory() as db:
            provider = db.query(Provider).filter_by(id=provider_id).first()
            if provider is None:
                return None
            return {
                "id": provider.id,
                "name": provider.name,
                "logo": provider.logo,
                "api_key": provider.api_key,
                "base_url": provider.base_url,
                "enabled": provider.enabled,
                "created_at": provider.created_at,
            }

    monkeypatch.setattr(model_service.ProviderService, "get_provider_by_id", staticmethod(get_provider))
    with session_factory.begin() as db:
        db.add(Provider(
            id="provider-1",
            name="Test Provider",
            logo="custom",
            api_key="",
            base_url="http://localhost",
            enabled=1,
        ))

    app = FastAPI()
    app.include_router(model_router.router, prefix="/api")
    return TestClient(app), session_factory


def _create_payload(**overrides) -> dict:
    payload = {
        "provider_id": "provider-1",
        "model_name": "runtime-model",
        "context_window_tokens": 131072,
        "supports_vision": True,
        "supports_stream": False,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("context_window_tokens", [511, 4_000_001])
def test_create_model_rejects_context_window_outside_persisted_runtime_range(runtime_api, context_window_tokens):
    client, _ = runtime_api

    response = client.post("/api/models", json=_create_payload(context_window_tokens=context_window_tokens))

    assert response.status_code == 422


@pytest.mark.parametrize("missing_field", ["supports_vision", "supports_stream"])
def test_create_model_requires_each_boolean_runtime_field(runtime_api, missing_field):
    client, _ = runtime_api
    payload = _create_payload()
    payload.pop(missing_field)

    response = client.post("/api/models", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize("field, value", [("supports_vision", 1), ("supports_stream", "false")])
def test_create_model_rejects_non_boolean_runtime_flags(runtime_api, field, value):
    client, _ = runtime_api

    response = client.post("/api/models", json=_create_payload(**{field: value}))

    assert response.status_code == 422


def test_create_model_returns_wrapper_code_404_when_provider_does_not_exist(runtime_api):
    client, _ = runtime_api

    response = client.post("/api/models", json=_create_payload(provider_id="missing-provider"))

    assert response.status_code == 200
    assert response.json()["code"] == 404


def test_create_model_returns_full_persisted_runtime_row(runtime_api):
    client, _ = runtime_api

    response = client.post("/api/models", json=_create_payload())

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"] == {
        "id": 1,
        "provider_id": "provider-1",
        "model_name": "runtime-model",
        "context_window_tokens": 131072,
        "supports_vision": True,
        "supports_stream": False,
        "created_at": ANY,
    }


def test_create_model_returns_wrapper_code_409_for_duplicate_provider_model(runtime_api):
    client, _ = runtime_api
    assert client.post("/api/models", json=_create_payload()).json()["code"] == 0

    response = client.post("/api/models", json=_create_payload())

    assert response.status_code == 200
    assert response.json()["code"] == 409


def test_create_model_returns_409_when_database_unique_constraint_catches_racing_duplicate(runtime_api, monkeypatch):
    client, _ = runtime_api
    # Simulate two requests both completing the service-level existence check
    # before either INSERT is committed. The database remains the final guard.
    monkeypatch.setattr(model_service, "get_model_by_provider_and_name", lambda *_args: None)

    assert client.post("/api/models", json=_create_payload()).json()["code"] == 0
    response = client.post("/api/models", json=_create_payload())

    assert response.status_code == 200
    assert response.json()["code"] == 409


def test_model_list_returns_each_saved_runtime_field(runtime_api):
    client, _ = runtime_api
    assert client.post("/api/models", json=_create_payload()).json()["code"] == 0

    response = client.get("/api/model_list")

    assert response.status_code == 200
    saved = response.json()["data"]
    assert len(saved) == 1
    assert saved[0] == {
        "id": 1,
        "provider_id": "provider-1",
        "model_name": "runtime-model",
        "context_window_tokens": 131072,
        "supports_vision": True,
        "supports_stream": False,
        "created_at": ANY,
        "capabilities": {},
    }


def test_enabled_provider_model_list_returns_each_saved_runtime_field(runtime_api):
    client, _ = runtime_api
    assert client.post("/api/models", json=_create_payload()).json()["code"] == 0

    response = client.get("/api/model_enable/provider-1")

    assert response.status_code == 200
    saved = response.json()["data"]
    assert len(saved) == 1
    assert saved[0]["context_window_tokens"] == 131072
    assert saved[0]["supports_vision"] is True
    assert saved[0]["supports_stream"] is False


def test_delete_model_removes_only_its_capability_cache(runtime_api):
    client, session_factory = runtime_api
    created = client.post("/api/models", json=_create_payload()).json()["data"]
    model_capability_dao.upsert_model_capability("provider-1", "runtime-model", supports_json_mode=True)
    with session_factory.begin() as db:
        db.add(NoteDocument(
            task_id="note-1",
            conversation_id="conversation-1",
            title="Existing note",
            content="must remain",
        ))
        db.add(ModelUsageRecord(
            task_id="task-1",
            provider_id="provider-1",
            provider_name="Test Provider",
            model_name="runtime-model",
            phase="summary",
            platform="web",
            status="success",
        ))

    response = client.get(f"/api/models/delete/{created['id']}")

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert model_dao.get_model_by_provider_and_name("provider-1", "runtime-model") is None
    assert model_capability_dao.get_model_capability("provider-1", "runtime-model") is None
    with session_factory() as db:
        assert db.query(Provider).filter_by(id="provider-1").count() == 1
        assert db.query(NoteDocument).filter_by(task_id="note-1").count() == 1
        assert db.query(ModelUsageRecord).filter_by(task_id="task-1").count() == 1


def test_delete_model_rolls_back_when_capability_cache_delete_fails(runtime_api):
    client, session_factory = runtime_api
    created = client.post("/api/models", json=_create_payload()).json()["data"]
    model_capability_dao.upsert_model_capability("provider-1", "runtime-model", supports_json_mode=True)
    with session_factory.begin() as db:
        db.connection().exec_driver_sql("""
            CREATE TRIGGER fail_model_capability_delete
            BEFORE DELETE ON model_capabilities
            BEGIN
                SELECT RAISE(ABORT, 'forced capability delete failure');
            END
        """)

    response = client.get(f"/api/models/delete/{created['id']}")

    assert response.status_code == 200
    assert response.json()["code"] == 500
    assert model_dao.get_model_by_provider_and_name("provider-1", "runtime-model") is not None
    assert model_capability_dao.get_model_capability("provider-1", "runtime-model") is not None
