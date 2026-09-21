from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.db.models.conversation import Conversation, NoteDocument  # noqa: F401
from app.db.models.whiteboard import Whiteboard


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'whiteboard-session.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_whiteboard_tables_are_created_on_empty_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'whiteboard.db'}")
    try:
        Base.metadata.create_all(engine)
        names = set(inspect(engine).get_table_names())
        assert {
            "whiteboards",
            "whiteboard_cards",
            "whiteboard_relations",
            "whiteboard_note_links",
        } <= names
    finally:
        engine.dispose()


def test_whiteboard_legacy_canvas_id_is_unique(db_session):
    db_session.add_all([
        Whiteboard(id="wb_1", conversation_id="c1", title="A", legacy_canvas_id="lc_1"),
        Whiteboard(id="wb_2", conversation_id="c1", title="B", legacy_canvas_id="lc_1"),
    ])
    with pytest.raises(IntegrityError):
        db_session.commit()
