from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, UniqueConstraint, func

from app.db.engine import Base


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_name", name="uq_model_provider_model"),
        Index("uq_models_provider_model_id", "provider_id", "model_id", unique=True),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    # notemeld.model-add.v1：协议模型标识，新库 NOT NULL；旧库经 additive 迁移回填后建部分唯一索引
    model_id = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    context_window_tokens = Column(Integer, nullable=False, server_default="4096")
    max_input_tokens = Column(Integer, nullable=False, server_default="3072")
    max_output_tokens = Column(Integer, nullable=False, server_default="1024")
    supports_vision = Column(Boolean, nullable=False, server_default="0")
    supports_stream = Column(Boolean, nullable=False, server_default="1")
    enabled = Column(Integer, nullable=False, server_default="1")
    is_default = Column(Integer, nullable=False, server_default="0")
    test_status = Column(String, nullable=False, server_default="unknown")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


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
