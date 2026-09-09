from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.db.engine import Base


class Whiteboard(Base):
    __tablename__ = "whiteboards"
    __table_args__ = (
        Index("ix_whiteboards_conversation_updated_at", "conversation_id", "updated_at"),
        UniqueConstraint("legacy_canvas_id", name="uq_whiteboards_legacy_canvas_id"),
    )

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    schema_version = Column(Integer, nullable=False, default=1)
    revision = Column(Integer, nullable=False, default=1)
    viewport_json = Column(Text, nullable=False, default='{"x":0,"y":0,"zoom":1}')
    legacy_canvas_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)


class WhiteboardCard(Base):
    __tablename__ = "whiteboard_cards"
    __table_args__ = (
        Index("ix_whiteboard_cards_whiteboard_z_index", "whiteboard_id", "z_index"),
    )

    id = Column(String, primary_key=True)
    whiteboard_id = Column(String, ForeignKey("whiteboards.id"), nullable=False, index=True)
    card_type = Column(String, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    content_json = Column(Text, nullable=False)
    source_refs_json = Column(Text, nullable=False, default="[]")
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    z_index = Column(Integer, nullable=False, default=0)
    collapsed = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class WhiteboardRelation(Base):
    __tablename__ = "whiteboard_relations"
    __table_args__ = (
        CheckConstraint(
            "source_card_id != target_card_id",
            name="ck_whiteboard_relations_distinct_cards",
        ),
    )

    id = Column(String, primary_key=True)
    whiteboard_id = Column(String, ForeignKey("whiteboards.id"), nullable=False, index=True)
    source_card_id = Column(String, ForeignKey("whiteboard_cards.id"), nullable=False, index=True)
    target_card_id = Column(String, ForeignKey("whiteboard_cards.id"), nullable=False, index=True)
    relation_type = Column(String, nullable=False, default="related")
    label = Column(String(160), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    line_type = Column(String, nullable=False, default="bezier")
    direction = Column(String, nullable=False, default="forward")
    source_refs_json = Column(Text, nullable=False, default="[]")
    style_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class WhiteboardNoteLink(Base):
    __tablename__ = "whiteboard_note_links"
    __table_args__ = (
        UniqueConstraint("note_task_id", name="uq_whiteboard_note_links_note_task_id"),
    )

    whiteboard_id = Column(
        String,
        ForeignKey("whiteboards.id"),
        primary_key=True,
    )
    note_task_id = Column(String, ForeignKey("note_documents.task_id"), nullable=False)
    published_revision = Column(Integer, nullable=False)
    published_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
