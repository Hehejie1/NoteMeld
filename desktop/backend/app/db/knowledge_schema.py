from __future__ import annotations

from sqlalchemy import text

from app.db.engine import get_engine


def ensure_knowledge_schema(engine=None) -> None:
    engine = engine or get_engine()
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunk_fts "
            "USING fts5(chunk_id UNINDEXED, article_id UNINDEXED, content, title, section_path)"
        ))
        connection.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_profile_fts "
            "USING fts5(profile_id UNINDEXED, article_id UNINDEXED, title, summary, topics)"
        ))
        connection.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_term_fts "
            "USING fts5(term_id UNINDEXED, article_id UNINDEXED, term_type, name, aliases, description, context)"
        ))
