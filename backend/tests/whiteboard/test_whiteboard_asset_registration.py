from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.routers import whiteboard
from app.services.conversation_asset_store import ConversationAssetStore
from app.services.whiteboard_asset_service import WhiteboardAssetRegistrationService
from app.services.whiteboard_repository import WhiteboardRepository


@pytest.fixture
def asset_environment(tmp_path, monkeypatch):
    output_root = tmp_path / "note-results"
    uploads_root = tmp_path / "uploads"
    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(output_root))
    monkeypatch.setenv("UPLOAD_DIR", str(uploads_root))
    engine = create_engine(f"sqlite:///{tmp_path / 'whiteboard-assets.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    store = ConversationAssetStore()
    repository = WhiteboardRepository(factory)
    service = WhiteboardAssetRegistrationService(
        repository=repository,
        asset_store=store,
        uploads_root=uploads_root,
    )
    try:
        yield repository, service, store, uploads_root
    finally:
        engine.dispose()


def _file_card(upload_id: str) -> dict:
    return {
        "op": "card.create",
        "card": {
            "id": "card_file",
            "type": "file",
            "title": "Paper",
            "description": "Evidence",
            "content": {"upload_id": upload_id},
            "source_refs": [],
            "position": {"x": 0, "y": 0},
            "size": {"width": 300, "height": 170},
        },
    }


def test_register_real_upload_then_repository_accepts_file_card(asset_environment) -> None:
    repository, service, store, uploads_root = asset_environment
    board = repository.create("conv_owner", "Research")
    upload_id = "upload_owned"
    uploads_root.mkdir(parents=True)
    (uploads_root / f"{upload_id}.pdf").write_bytes(b"%PDF-test")

    registered = service.register(
        "conv_owner",
        board.id,
        upload_id=upload_id,
        file_name="paper.pdf",
        content_type="application/pdf",
        file_kind="document",
    )
    result = repository.apply_mutations(
        "conv_owner", board.id, board.revision, [_file_card(upload_id)]
    )

    assert registered["upload_id"] == upload_id
    assert registered["source_url"] == f"/api/uploads/{upload_id}"
    assert registered["file_name"] == "paper.pdf"
    assert result.cards[0].content == {"upload_id": upload_id}
    assets = store.list_assets("conv_owner")
    assert len(assets) == 1
    assert assets[0]["source_url"] == f"/api/uploads/{upload_id}"


def test_foreign_conversation_cannot_register_upload_for_board(asset_environment) -> None:
    repository, service, store, uploads_root = asset_environment
    board = repository.create("conv_owner", "Research")
    uploads_root.mkdir(parents=True)
    (uploads_root / "upload_foreign.pdf").write_bytes(b"%PDF-test")

    with pytest.raises(LookupError):
        service.register(
            "conv_foreign",
            board.id,
            upload_id="upload_foreign",
            file_name="paper.pdf",
            content_type="application/pdf",
            file_kind="document",
        )

    assert store.list_assets("conv_foreign") == []


def test_missing_or_unsafe_upload_is_not_registered(asset_environment) -> None:
    repository, service, store, _uploads_root = asset_environment
    board = repository.create("conv_owner", "Research")

    with pytest.raises(FileNotFoundError):
        service.register(
            "conv_owner",
            board.id,
            upload_id="upload_missing",
            file_name="paper.pdf",
            content_type="application/pdf",
            file_kind="document",
        )
    with pytest.raises(ValueError):
        service.register(
            "conv_owner",
            board.id,
            upload_id="../escape",
            file_name="paper.pdf",
            content_type="application/pdf",
            file_kind="document",
        )

    assert store.list_assets("conv_owner") == []


def test_asset_registration_endpoint_uses_scoped_service(asset_environment, monkeypatch) -> None:
    repository, service, store, uploads_root = asset_environment
    board = repository.create("conv_owner", "Research")
    uploads_root.mkdir(parents=True)
    (uploads_root / "upload_api.pdf").write_bytes(b"%PDF-test")
    monkeypatch.setattr(whiteboard, "asset_service", service)
    app = FastAPI()
    app.include_router(whiteboard.router, prefix="/api")

    response = TestClient(app).post(
        f"/api/conversations/conv_owner/whiteboards/{board.id}/assets",
        json={
            "upload_id": "upload_api",
            "file_name": "paper.pdf",
            "content_type": "application/pdf",
            "file_kind": "document",
        },
    ).json()

    assert response["code"] == 0
    assert response["data"]["source_url"] == "/api/uploads/upload_api"
    assert len(store.list_assets("conv_owner")) == 1
