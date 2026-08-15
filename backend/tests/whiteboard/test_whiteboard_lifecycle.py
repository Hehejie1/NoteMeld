from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.db.models.conversation import Conversation, NoteDocument
from app.db.models.whiteboard import (
    Whiteboard as WhiteboardRow,
    WhiteboardCard as WhiteboardCardRow,
    WhiteboardNoteLink as WhiteboardNoteLinkRow,
    WhiteboardRelation as WhiteboardRelationRow,
)
from app.services import conversation_store, note_document_store
from app.services.whiteboard_repository import WhiteboardRepository


@pytest.fixture()
def lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def open_session():
        return factory()

    monkeypatch.setattr(conversation_store, "_db", open_session)
    monkeypatch.setattr(note_document_store, "_db", open_session)
    monkeypatch.setattr(note_document_store, "delete_note_task_artifacts", lambda _task_id: {})
    monkeypatch.setattr("app.services.note_task_store.cancel_note_task", lambda *_args: {})

    conversation_store.upsert_conversation(
        {
            "id": "conv-lifecycle",
            "mode": "note",
            "linkedNoteTaskId": "note-lifecycle",
            "noteState": "ready",
        }
    )
    note_document_store.upsert_note_document(
        {
            "task_id": "note-lifecycle",
            "conversation_id": "conv-lifecycle",
            "title": "Published note",
            "content": "# Published note",
        }
    )
    return factory, WhiteboardRepository(factory)


def _create_linked_board(factory, repository: WhiteboardRepository):
    board = repository.create("conv-lifecycle", "Lifecycle board")
    with factory.begin() as session:
        session.add(
            WhiteboardNoteLinkRow(
                whiteboard_id=board.id,
                note_task_id="note-lifecycle",
                published_revision=board.revision,
            )
        )
    return board


def test_conversation_soft_delete_hides_boards_without_deleting_graph(lifecycle) -> None:
    factory, repository = lifecycle
    board = repository.create("conv-lifecycle", "Recoverable board")
    repository.apply_mutations(
        "conv-lifecycle",
        board.id,
        board.revision,
        [
            {
                "op": "card.create",
                "card": {
                    "id": "card-recoverable",
                    "type": "markdown",
                    "title": "Preserved",
                    "description": "",
                    "content": {"markdown": "Preserved body"},
                    "source_refs": [],
                    "position": {"x": 0, "y": 0},
                    "size": {"width": 320, "height": 220},
                    "z_index": 0,
                    "collapsed": True,
                },
            }
        ],
    )

    assert conversation_store.soft_delete_conversation("conv-lifecycle") is True
    assert repository.list_for_conversation("conv-lifecycle") == []
    with pytest.raises(LookupError):
        repository.get("conv-lifecycle", board.id)

    with factory() as session:
        stored_board = session.get(WhiteboardRow, board.id)
        assert stored_board is not None
        assert stored_board.status == "archived"
        assert stored_board.deleted_at is not None
        assert session.get(WhiteboardCardRow, "card-recoverable") is not None


def test_card_delete_removes_its_relations_in_the_same_mutation(lifecycle) -> None:
    factory, repository = lifecycle
    board = repository.create("conv-lifecycle", "Transactional graph")
    created = repository.apply_mutations(
        "conv-lifecycle",
        board.id,
        board.revision,
        [
            {
                "op": "card.create",
                "card": {
                    "id": card_id,
                    "type": "markdown",
                    "title": card_id,
                    "description": "",
                    "content": {"markdown": card_id},
                    "source_refs": [],
                    "position": {"x": index * 360, "y": 0},
                    "size": {"width": 320, "height": 220},
                    "z_index": index,
                    "collapsed": True,
                },
            }
            for index, card_id in enumerate(("card-a", "card-b"))
        ]
        + [
            {
                "op": "relation.create",
                "relation": {
                    "id": "relation-a-b",
                    "source_card_id": "card-a",
                    "target_card_id": "card-b",
                    "relation_type": "related",
                    "label": "supports",
                    "description": "",
                    "line_type": "bezier",
                    "direction": "forward",
                    "source_refs": [],
                    "style": {},
                },
            }
        ],
    )

    deleted = repository.apply_mutations(
        "conv-lifecycle",
        board.id,
        created.revision,
        [{"op": "card.delete", "card_id": "card-a"}],
    )

    assert deleted.deleted_card_ids == ["card-a"]
    assert deleted.deleted_relation_ids == ["relation-a-b"]
    with factory() as session:
        assert session.get(WhiteboardCardRow, "card-a") is None
        assert session.get(WhiteboardRelationRow, "relation-a-b") is None


def test_deleting_linked_note_clears_link_but_preserves_board(lifecycle) -> None:
    factory, repository = lifecycle
    board = _create_linked_board(factory, repository)

    result = conversation_store.delete_conversation_note_document(
        "conv-lifecycle",
        "note-lifecycle",
    )

    assert result is not None
    reloaded = repository.get("conv-lifecycle", board.id)
    assert reloaded.note_link is None
    assert reloaded.id == board.id
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(WhiteboardRow)) == 1
        assert session.get(NoteDocument, "note-lifecycle").deleted_at is not None
        assert session.get(Conversation, "conv-lifecycle").deleted_at is None


def test_conversation_delete_serializes_against_board_mutation(
    lifecycle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _factory, repository = lifecycle
    board = repository.create("conv-lifecycle", "Concurrent board")
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
                "conv-lifecycle"
            )
        except Exception as exc:  # pragma: no cover - asserted through outcomes
            outcomes["delete_error"] = exc

    def mutate_board() -> None:
        try:
            repository.apply_mutations(
                "conv-lifecycle",
                board.id,
                board.revision,
                [{"op": "viewport.update", "x": 10, "y": 20, "zoom": 1}],
            )
            outcomes["mutation"] = "committed"
        except Exception as exc:  # pragma: no cover - asserted through outcomes
            outcomes["mutation_error"] = exc

    delete_thread = threading.Thread(target=delete_conversation)
    delete_thread.start()
    assert delete_entered.wait(timeout=5)
    mutation_thread = threading.Thread(target=mutate_board)
    mutation_thread.start()
    time.sleep(0.1)
    allow_delete.set()
    delete_thread.join(timeout=5)
    mutation_thread.join(timeout=5)

    assert outcomes.get("delete") is True
    assert "delete_error" not in outcomes
    assert isinstance(outcomes.get("mutation_error"), LookupError)
    assert "mutation" not in outcomes
    assert repository.list_for_conversation("conv-lifecycle") == []
