from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.db.models.conversation import Conversation, NoteDocument
from app.db.models.whiteboard import (
    Whiteboard,
    WhiteboardCard,
    WhiteboardNoteLink,
    WhiteboardRelation,
)
from app.services.migration.merge_service import MigrationMergeService


def _database(path: Path):
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _conversation(session, conversation_id: str, note_ids: tuple[str, ...]) -> None:
    session.add(Conversation(id=conversation_id))
    for note_id in note_ids:
        session.add(
            NoteDocument(
                task_id=note_id,
                conversation_id=conversation_id,
                title=note_id,
                content=f"# {note_id}",
            )
        )


def _board(session, board_id: str, conversation_id: str, title: str) -> Whiteboard:
    row = Whiteboard(
        id=board_id,
        conversation_id=conversation_id,
        title=title,
        description="",
        schema_version=1,
        revision=1,
        viewport_json='{"x":0,"y":0,"zoom":1}',
        status="active",
    )
    session.add(row)
    return row


def _card(session, card_id: str, board_id: str, title: str) -> WhiteboardCard:
    row = WhiteboardCard(
        id=card_id,
        whiteboard_id=board_id,
        card_type="markdown",
        title=title,
        description="",
        content_json='{"markdown":"body"}',
        source_refs_json="[]",
        x=0,
        y=0,
        width=320,
        height=220,
        z_index=0,
        collapsed=True,
    )
    session.add(row)
    return row


def _relation(
    session,
    relation_id: str,
    board_id: str,
    source_card_id: str,
    target_card_id: str,
    label: str,
) -> WhiteboardRelation:
    row = WhiteboardRelation(
        id=relation_id,
        whiteboard_id=board_id,
        source_card_id=source_card_id,
        target_card_id=target_card_id,
        relation_type="related",
        label=label,
        description="",
        line_type="bezier",
        direction="forward",
        source_refs_json="[]",
        style_json="{}",
    )
    session.add(row)
    return row


def test_merge_remaps_cross_owner_graph_collisions_and_skips_unique_note_link(
    tmp_path: Path,
) -> None:
    current_path = tmp_path / "current.db"
    source_path = tmp_path / "source.db"
    current_engine, current_factory = _database(current_path)
    source_engine, source_factory = _database(source_path)

    with current_factory.begin() as session:
        _conversation(session, "conv-local", ("note-local",))
        _conversation(session, "conv-owner", ("note-shared",))
        _board(session, "wb-shared", "conv-local", "Local collision board")
        _card(session, "card-shared", "wb-shared", "Local collision card")
        _card(session, "card-local-target", "wb-shared", "Local target")
        _relation(
            session,
            "rel-shared",
            "wb-shared",
            "card-shared",
            "card-local-target",
            "Local relation",
        )
        _board(session, "wb-same", "conv-owner", "Old same-owner title")
        _card(session, "card-same", "wb-same", "Old same-owner card")
        _board(session, "wb-note-local", "conv-owner", "Local note owner")
        session.add(
            WhiteboardNoteLink(
                whiteboard_id="wb-note-local",
                note_task_id="note-shared",
                published_revision=1,
            )
        )

    with source_factory.begin() as session:
        _conversation(session, "conv-import", ("note-import",))
        _conversation(session, "conv-owner", ("note-shared",))
        _board(session, "wb-shared", "conv-import", "Imported collision board")
        _card(session, "card-shared", "wb-shared", "Imported collision card")
        _card(session, "card-import-target", "wb-shared", "Imported target")
        _relation(
            session,
            "rel-shared",
            "wb-shared",
            "card-shared",
            "card-import-target",
            "Imported relation",
        )
        session.add(
            WhiteboardNoteLink(
                whiteboard_id="wb-shared",
                note_task_id="note-import",
                published_revision=1,
            )
        )
        _board(session, "wb-same", "conv-owner", "New same-owner title")
        _card(session, "card-same", "wb-same", "New same-owner card")
        _board(session, "wb-note-import", "conv-owner", "Imported duplicate note owner")
        session.add(
            WhiteboardNoteLink(
                whiteboard_id="wb-note-import",
                note_task_id="note-shared",
                published_revision=1,
            )
        )

    summary = MigrationMergeService(current_db_path=current_path).merge_database(
        source_path
    )

    with current_factory() as session:
        local_board = session.get(Whiteboard, "wb-shared")
        assert local_board.conversation_id == "conv-local"
        assert local_board.title == "Local collision board"
        imported_board = session.scalar(
            select(Whiteboard).where(Whiteboard.title == "Imported collision board")
        )
        assert imported_board is not None
        assert imported_board.id != "wb-shared"
        assert imported_board.conversation_id == "conv-import"

        local_card = session.get(WhiteboardCard, "card-shared")
        assert local_card.whiteboard_id == "wb-shared"
        assert local_card.title == "Local collision card"
        imported_card = session.scalar(
            select(WhiteboardCard).where(
                WhiteboardCard.title == "Imported collision card"
            )
        )
        imported_target = session.scalar(
            select(WhiteboardCard).where(WhiteboardCard.title == "Imported target")
        )
        assert imported_card is not None
        assert imported_card.id != "card-shared"
        assert imported_card.whiteboard_id == imported_board.id
        assert imported_target.whiteboard_id == imported_board.id

        local_relation = session.get(WhiteboardRelation, "rel-shared")
        assert local_relation.whiteboard_id == "wb-shared"
        assert local_relation.label == "Local relation"
        imported_relation = session.scalar(
            select(WhiteboardRelation).where(
                WhiteboardRelation.label == "Imported relation"
            )
        )
        assert imported_relation is not None
        assert imported_relation.id != "rel-shared"
        assert imported_relation.whiteboard_id == imported_board.id
        assert imported_relation.source_card_id == imported_card.id
        assert imported_relation.target_card_id == imported_target.id

        assert session.get(Whiteboard, "wb-same").title == "New same-owner title"
        assert session.get(WhiteboardCard, "card-same").title == "New same-owner card"
        assert session.get(WhiteboardNoteLink, imported_board.id).note_task_id == "note-import"
        shared_links = session.scalars(
            select(WhiteboardNoteLink).where(
                WhiteboardNoteLink.note_task_id == "note-shared"
            )
        ).all()
        assert [link.whiteboard_id for link in shared_links] == ["wb-note-local"]

    assert summary["whiteboards"]["inserted"] == 2
    assert summary["whiteboards"]["overwritten"] == 1
    assert summary["whiteboard_note_links"]["skipped"] == 1
    current_engine.dispose()
    source_engine.dispose()
