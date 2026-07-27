from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.db.engine import Base


class TemplateExtractionTask(Base):
    __tablename__ = "template_extraction_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, nullable=False, default="pending", index=True)
    stage = Column(String, nullable=False, default="created")
    messages_json = Column(Text, nullable=False, default="[]")
    chunks_json = Column(Text, nullable=False, default="[]")
    provider_id = Column(String, nullable=False, default="")
    model_name = Column(String, nullable=False, default="")
    file_name = Column(String, nullable=False, default="")
    progress = Column(Integer, nullable=False, default=0)
    request_type = Column(String, nullable=False, default="")
    request_payload_json = Column(Text, nullable=False, default="{}")
    user_message_json = Column(Text, nullable=False, default="{}")
    result_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
