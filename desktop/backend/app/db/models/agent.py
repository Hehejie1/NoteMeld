from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text

from app.db.engine import Base


class AgentTurn(Base):
    __tablename__ = "agent_turns"
    __table_args__ = (
        Index(
            "uq_agent_turns_session_idempotency_key",
            "session_id",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    turn_id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    idempotency_key = Column(String, nullable=True)
    status = Column(String, nullable=False, default="created")
    model_name = Column(String, nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AgentEvent(Base):
    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint("turn_id", "sequence", name="uq_agent_events_turn_sequence"),
    )

    event_id = Column(String, primary_key=True)
    turn_id = Column(String, ForeignKey("agent_turns.turn_id"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String, nullable=True)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, server_default=func.now())


class AgentPreference(Base):
    __tablename__ = "agent_preferences"

    session_id = Column(String, ForeignKey("conversations.id"), primary_key=True)
    default_model_id = Column(String, nullable=True)
    fallback_models_json = Column(Text, nullable=False, default="[]")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


__all__ = ["AgentEvent", "AgentPreference", "AgentTurn"]
