from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint, func

from app.db.engine import Base


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_name", name="uq_model_provider_model"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    context_window_tokens = Column(Integer, nullable=False, server_default="4096")
    supports_vision = Column(Boolean, nullable=False, server_default="0")
    supports_stream = Column(Boolean, nullable=False, server_default="1")
    created_at = Column(DateTime, server_default=func.now())


class ModelCapability(Base):
    __tablename__ = "model_capabilities"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_name", name="uq_model_capability_provider_model"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    supports_json_mode = Column(Boolean, nullable=True)
    supports_vision = Column(Boolean, nullable=True)
    json_mode_checked_at = Column(DateTime, nullable=True)
    vision_checked_at = Column(DateTime, nullable=True)
    last_probe_error = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())
