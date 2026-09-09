from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.db.engine import Base


class ModelUsageRecord(Base):
    __tablename__ = "model_usage_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, index=True, nullable=True)
    provider_id = Column(String, index=True, nullable=False)
    provider_name = Column(String, nullable=False)
    model_name = Column(String, index=True, nullable=False)
    phase = Column(String, index=True, nullable=False)
    platform = Column(String, index=True, nullable=True)
    video_id = Column(String, index=True, nullable=True)
    video_title = Column(String, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    status = Column(String, index=True, nullable=False)
    error_message = Column(Text, nullable=True)
    request_started_at = Column(DateTime, nullable=True)
    request_finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=False, default=0)
    request_meta_json = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
