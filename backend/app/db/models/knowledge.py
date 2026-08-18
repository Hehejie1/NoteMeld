from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func

from app.db.engine import Base


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    article_id = Column(String, primary_key=True)
    title = Column(String, nullable=False, default="")
    source_type = Column(String, nullable=False, default="")
    source_url = Column(Text, nullable=True)
    content = Column(Text, nullable=False, default="")
    status = Column(String, nullable=False, default="active")
    metadata_json = Column(Text, nullable=False, default="{}")
    index_version = Column(String, nullable=False, default="knowledge_index.v1")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("ix_knowledge_chunks_article_page", "article_id", "page_number"),
        Index("ix_knowledge_chunks_article_index", "article_id", "chunk_index"),
    )

    chunk_id = Column(String, primary_key=True)
    article_id = Column(String, ForeignKey("knowledge_articles.article_id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    section_path = Column(String, nullable=True)
    start_time = Column(Float, nullable=True)
    end_time = Column(Float, nullable=True)
    chunk_index = Column(Integer, nullable=False, default=0)
    metadata_json = Column(Text, nullable=False, default="{}")
    index_version = Column(String, nullable=False, default="knowledge_index.v1")


class KnowledgeProfile(Base):
    __tablename__ = "knowledge_profiles"
    __table_args__ = (UniqueConstraint("article_id", name="uq_knowledge_profiles_article_id"),)

    profile_id = Column(String, primary_key=True)
    article_id = Column(String, ForeignKey("knowledge_articles.article_id"), nullable=False, index=True)
    title = Column(String, nullable=False, default="")
    summary = Column(Text, nullable=False, default="")
    topics_json = Column(Text, nullable=False, default="[]")
    status = Column(String, nullable=False, default="complete")
    index_version = Column(String, nullable=False, default="knowledge_index.v1")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class KnowledgeTerm(Base):
    __tablename__ = "knowledge_terms"

    term_id = Column(String, primary_key=True)
    term_type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    normalized_name = Column(String, nullable=False, index=True)
    aliases_json = Column(Text, nullable=False, default="[]")
    description = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class KnowledgeTermOccurrence(Base):
    __tablename__ = "knowledge_term_occurrences"
    __table_args__ = (
        Index("ix_knowledge_term_occurrences_article", "article_id"),
        Index("ix_knowledge_term_occurrences_term_article", "term_id", "article_id"),
    )

    occurrence_id = Column(String, primary_key=True)
    term_id = Column(String, ForeignKey("knowledge_terms.term_id"), nullable=False, index=True)
    article_id = Column(String, ForeignKey("knowledge_articles.article_id"), nullable=False, index=True)
    evidence_id = Column(String, nullable=True)
    context = Column(Text, nullable=False, default="")
    index_version = Column(String, nullable=False, default="knowledge_index.v1")


class KnowledgeRelation(Base):
    __tablename__ = "knowledge_relations"
    __table_args__ = (
        Index("ix_knowledge_relations_article", "article_id"),
        Index("ix_knowledge_relations_source_target", "source_term_id", "target_term_id"),
    )

    relation_id = Column(String, primary_key=True)
    source_term_id = Column(String, ForeignKey("knowledge_terms.term_id"), nullable=False, index=True)
    target_term_id = Column(String, ForeignKey("knowledge_terms.term_id"), nullable=False, index=True)
    article_id = Column(String, ForeignKey("knowledge_articles.article_id"), nullable=False, index=True)
    relation_type = Column(String, nullable=False, default="related")
    evidence_id = Column(String, nullable=True)
    weight = Column(Float, nullable=False, default=1.0)
    metadata_json = Column(Text, nullable=False, default="{}")
    index_version = Column(String, nullable=False, default="knowledge_index.v1")


class KnowledgeIndexState(Base):
    __tablename__ = "knowledge_index_states"

    layer = Column(String, primary_key=True)
    generation = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ready")
    error_code = Column(String, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


__all__ = [
    "KnowledgeArticle",
    "KnowledgeChunk",
    "KnowledgeIndexState",
    "KnowledgeProfile",
    "KnowledgeRelation",
    "KnowledgeTerm",
    "KnowledgeTermOccurrence",
]
