from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from app.services.knowledge_article_service import KnowledgeArticleService
from app.utils.storage_paths import database_path, note_output_dir


class KnowledgeReindexService:
    def __init__(self, *, note_output_root: str | Path | None = None, article_service: KnowledgeArticleService | None = None, current_db_path: str | Path | None = None):
        self.note_output_root = Path(note_output_root or note_output_dir())
        self.article_service = article_service or KnowledgeArticleService()
        self.current_db_path = Path(current_db_path or database_path())

    def rebuild(self, article_ids: list[str] | None = None, cancel_check: Callable[[], bool] | None = None) -> dict:
        ids = self._normalize(article_ids or self._article_ids_from_db())
        rebuilt = []
        cancelled = False
        for article_id in ids:
            if cancel_check and cancel_check():
                cancelled = True
                break
            try:
                self.article_service.index_from_note_file(article_id)
            except FileNotFoundError:
                continue
            rebuilt.append(article_id)
        return {"status": "cancelled" if cancelled else "success", "indexed": len(rebuilt), "article_ids": rebuilt}

    def _article_ids_from_db(self) -> list[str]:
        if not self.current_db_path.exists():
            return []
        with sqlite3.connect(self.current_db_path) as connection:
            try:
                rows = connection.execute("SELECT task_id FROM note_documents WHERE deleted_at IS NULL ORDER BY created_at ASC").fetchall()
            except sqlite3.OperationalError:
                return []
        return [str(row[0]) for row in rows if row and row[0]]

    def _normalize(self, values: list[str]) -> list[str]:
        return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))
