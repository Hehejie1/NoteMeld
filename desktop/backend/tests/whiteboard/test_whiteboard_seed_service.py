from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.db.models.conversation import Conversation, NoteDocument
from app.db.models.whiteboard import Whiteboard
from app.models.learning_canvas import (
    LearningCanvas,
    LearningEdge,
    LearningNode,
    LearningSource,
)
from app.services import conversation_store, note_document_store
from app.services.learning_canvas_store import LearningCanvasStore
from app.services.whiteboard_repository import WhiteboardRepository
from app.services.whiteboard_seed_service import WhiteboardSeedService


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _legacy_canvas() -> LearningCanvas:
    return LearningCanvas(
        version=2,
        canvas_id="lc_legacy",
        conversation_id="conv_legacy",
        goal="Agent architecture",
        document_task_id="note_legacy",
        nodes=[
            LearningNode(
                id="node_plan",
                label="Planning",
                summary="Break the goal into steps.",
                source_ids=["wiki:planning", "missing:source"],
            ),
            LearningNode(
                id="node_tools",
                label="Tools",
                user_label="Tool execution",
                summary="Call external capabilities.",
                user_summary="Use validated tools and inspect their output.",
                source_ids=["github:agent-kit"],
            ),
            LearningNode(
                id="node_review",
                label="Review",
                summary="Revise after observation.",
            ),
        ],
        edges=[
            LearningEdge(source="node_plan", target="node_tools", type="prerequisite"),
            LearningEdge(source="node_tools", target="node_missing", type="supports"),
        ],
        sources=[
            LearningSource(
                id="wiki:planning",
                source_type="local_wiki",
                provider="notemeld_wiki",
                title="Planning note",
                local_task_id="task_planning",
            ),
            LearningSource(
                id="github:agent-kit",
                source_type="github",
                provider="github",
                title="Agent kit",
                url="https://github.com/example/agent-kit",
            ),
        ],
    )


def _seed_fixture(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'whiteboard-seed.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(Conversation(id="conv_legacy"))
        session.add(
            NoteDocument(
                task_id="note_legacy",
                conversation_id="conv_legacy",
                title="Agent architecture",
                content="# Agent architecture",
            )
        )
    store = LearningCanvasStore(root=tmp_path / "workspaces")
    store.save(_legacy_canvas())
    repository = WhiteboardRepository(factory)
    service = WhiteboardSeedService(repository=repository, store=store)
    return engine, factory, store, service


def test_seed_converts_grid_sources_relations_and_note_without_touching_json(tmp_path) -> None:
    engine, _factory, store, service = _seed_fixture(tmp_path)
    path = store.path_for("conv_legacy", "lc_legacy")
    checksum_before = _sha256(path)
    try:
        board = service.ensure_from_learning_canvas("conv_legacy", "lc_legacy")

        assert board.legacy_canvas_id == "lc_legacy"
        assert [card.title for card in board.cards] == [
            "Planning",
            "Tool execution",
            "Review",
        ]
        assert [card.position.model_dump() for card in board.cards] == [
            {"x": 0.0, "y": 0.0},
            {"x": 340.0, "y": 0.0},
            {"x": 0.0, "y": 220.0},
        ]
        assert [card.size.model_dump() for card in board.cards] == [
            {"width": 300.0, "height": 170.0},
            {"width": 300.0, "height": 170.0},
            {"width": 300.0, "height": 170.0},
        ]
        assert board.cards[0].source_refs[0].model_dump(mode="json") == {
            "source_id": "wiki:planning",
            "source_type": "local_wiki",
            "title": "Planning note",
            "url": None,
            "task_id": "task_planning",
        }
        assert [item.source_id for item in board.cards[0].source_refs] == [
            "wiki:planning"
        ]
        assert board.cards[1].source_refs[0].url == "https://github.com/example/agent-kit"
        assert len(board.relations) == 1
        assert board.relations[0].relation_type == "depends_on"
        assert board.relations[0].label == "prerequisite"
        assert board.note_link is not None
        assert board.note_link.note_task_id == "note_legacy"
        assert board.note_link.published_revision == 1
        assert _sha256(path) == checksum_before
    finally:
        engine.dispose()


def test_repeated_seed_returns_the_same_board_and_one_legacy_row(tmp_path) -> None:
    engine, factory, _store, service = _seed_fixture(tmp_path)
    try:
        first = service.ensure_from_learning_canvas("conv_legacy", "lc_legacy")
        second = service.ensure_from_learning_canvas("conv_legacy", "lc_legacy")

        assert second.id == first.id
        with factory() as session:
            assert session.scalar(
                select(func.count()).select_from(Whiteboard).where(
                    Whiteboard.legacy_canvas_id == "lc_legacy"
                )
            ) == 1
    finally:
        engine.dispose()


def test_repeated_seed_returns_existing_board_before_revalidating_legacy_payload(
    tmp_path,
) -> None:
    engine, _factory, store, service = _seed_fixture(tmp_path)
    try:
        first = service.ensure_from_learning_canvas("conv_legacy", "lc_legacy")
        path = store.path_for("conv_legacy", "lc_legacy")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["goal"] = "x" * 201
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        repeated = service.ensure_from_learning_canvas("conv_legacy", "lc_legacy")

        assert repeated.id == first.id
    finally:
        engine.dispose()


def test_soft_deleted_legacy_seed_is_not_resurfaced(tmp_path) -> None:
    engine, factory, _store, service = _seed_fixture(tmp_path)
    try:
        board = service.ensure_from_learning_canvas("conv_legacy", "lc_legacy")
        service.repository.soft_delete("conv_legacy", board.id)

        with pytest.raises(LookupError):
            service.ensure_from_learning_canvas("conv_legacy", "lc_legacy")
        with factory() as session:
            assert session.scalar(
                select(func.count()).select_from(Whiteboard).where(
                    Whiteboard.legacy_canvas_id == "lc_legacy"
                )
            ) == 1
    finally:
        engine.dispose()


def test_seed_rejects_deleted_conversation_before_creating_board(tmp_path) -> None:
    engine, factory, _store, service = _seed_fixture(tmp_path)
    try:
        with factory.begin() as session:
            session.get(Conversation, "conv_legacy").deleted_at = conversation_store._now_dt()

        with pytest.raises(LookupError):
            service.ensure_from_learning_canvas("conv_legacy", "lc_legacy")

        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Whiteboard)) == 0
    finally:
        engine.dispose()


def test_foreign_and_absent_learning_canvas_paths_are_indistinguishable(tmp_path) -> None:
    engine, _factory, _store, service = _seed_fixture(tmp_path)
    try:
        for canvas_id in ("lc_legacy", "lc_absent"):
            with pytest.raises(FileNotFoundError):
                service.ensure_from_learning_canvas("conv_other", canvas_id)
    finally:
        engine.dispose()


def test_concurrent_seed_calls_create_one_legacy_canvas_row(tmp_path) -> None:
    engine, factory, _store, service = _seed_fixture(tmp_path)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            boards = list(
                pool.map(
                    lambda _index: service.ensure_from_learning_canvas(
                        "conv_legacy", "lc_legacy"
                    ),
                    range(16),
                )
            )

        assert len({board.id for board in boards}) == 1
        with factory() as session:
            assert session.scalar(
                select(func.count()).select_from(Whiteboard).where(
                    Whiteboard.legacy_canvas_id == "lc_legacy"
                )
            ) == 1
    finally:
        engine.dispose()


def test_conversation_delete_serializes_against_learning_canvas_seed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory, _store, service = _seed_fixture(tmp_path)

    def open_session():
        return factory()

    monkeypatch.setattr(conversation_store, "_db", open_session)
    monkeypatch.setattr(note_document_store, "_db", open_session)
    delete_entered = threading.Event()
    allow_delete = threading.Event()
    original_soft_delete = conversation_store.soft_delete_whiteboards_by_conversation
    outcomes: dict[str, object] = {}

    def paused_soft_delete(conversation_id: str, *, db=None) -> int:
        delete_entered.set()
        assert allow_delete.wait(timeout=5)
        return original_soft_delete(conversation_id, db=db)

    monkeypatch.setattr(
        conversation_store,
        "soft_delete_whiteboards_by_conversation",
        paused_soft_delete,
    )

    def delete_conversation() -> None:
        try:
            outcomes["delete"] = conversation_store.soft_delete_conversation(
                "conv_legacy"
            )
        except Exception as exc:  # pragma: no cover - asserted through outcomes
            outcomes["delete_error"] = exc

    def seed_canvas() -> None:
        try:
            outcomes["seed"] = service.ensure_from_learning_canvas(
                "conv_legacy",
                "lc_legacy",
            )
        except Exception as exc:  # pragma: no cover - asserted through outcomes
            outcomes["seed_error"] = exc

    try:
        delete_thread = threading.Thread(target=delete_conversation)
        delete_thread.start()
        assert delete_entered.wait(timeout=5)
        seed_thread = threading.Thread(target=seed_canvas)
        seed_thread.start()
        time.sleep(0.1)
        allow_delete.set()
        delete_thread.join(timeout=5)
        seed_thread.join(timeout=5)

        assert outcomes.get("delete") is True
        assert isinstance(outcomes.get("seed_error"), LookupError)
        assert "seed" not in outcomes
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Whiteboard)) == 0
    finally:
        engine.dispose()


def test_foreign_conversation_note_is_not_linked(tmp_path) -> None:
    engine, factory, store, service = _seed_fixture(tmp_path)
    with factory.begin() as session:
        session.add(Conversation(id="conv_other"))
        session.add(
            NoteDocument(
                task_id="note_foreign",
                conversation_id="conv_other",
                title="Foreign note",
                content="# Foreign note",
            )
        )
    canvas = _legacy_canvas()
    canvas.canvas_id = "lc_without_owned_note"
    canvas.document_task_id = "note_foreign"
    store.save(canvas)
    try:
        board = service.ensure_from_learning_canvas(
            "conv_legacy", "lc_without_owned_note"
        )
        assert board.note_link is None
    finally:
        engine.dispose()
