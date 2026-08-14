from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func

from app.db.engine import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    mode = Column(String, nullable=False, default="chat")
    title = Column(String, nullable=True)
    status = Column(String, nullable=False, default="SUCCESS")
    message = Column(Text, nullable=True)
    platform = Column(String, nullable=True)
    linked_note_task_id = Column(String, nullable=True)
    note_state = Column(String, nullable=False, default="none")
    form_data_json = Column(Text, nullable=False, default="{}")
    transcript_json = Column(Text, nullable=False, default="{}")
    audio_meta_json = Column(Text, nullable=False, default="{}")
    markdown_json = Column(Text, nullable=False, default='""')
    # P3 阶段二：会话绑定的研究空间 id（cid→rs_id 映射），nullable 兼容历史行
    research_space_id = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    message_type = Column(String, nullable=False, default="assistant_text")
    content = Column(Text, nullable=False)
    status = Column(String, nullable=True)
    meta_json = Column(Text, nullable=False, default="{}")
    sources_json = Column(Text, nullable=False, default="[]")
    error = Column(Integer, nullable=False, default=0)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class NoteDocument(Base):
    __tablename__ = "note_documents"

    task_id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    title = Column(String, nullable=False, default="")
    content = Column(Text, nullable=False, default="")
    source_url = Column(Text, nullable=True)
    platform = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    style = Column(String, nullable=True)
    status = Column(String, nullable=False, default="SUCCESS")
    wiki_status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)
