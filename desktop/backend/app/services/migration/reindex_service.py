from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services.wiki_store import WikiStore
from app.utils.storage_paths import database_path, note_output_dir


class MigrationReindexService:
    def __init__(
        self,
        current_db_path: str | Path | None = None,
        note_output_root: str | Path | None = None,
        vector_store_manager=None,
    ):
        self.current_db_path = Path(current_db_path or database_path())
        self.note_output_root = Path(note_output_root or note_output_dir())
        self.vector_store_manager = vector_store_manager

    def rebuild(self, task_ids: list[str] | None = None) -> dict:
        tasks = self._normalize_task_ids(task_ids or self._task_ids_from_db())
        WikiStore(base_dir=self.note_output_root / "wiki").rebuild_from_contributions()
        knowledge_result = {"indexed": 0}
        if self.vector_store_manager is None:
            from app.services.knowledge_reindex_service import KnowledgeReindexService

            knowledge_result = KnowledgeReindexService(
                note_output_root=self.note_output_root,
                current_db_path=self.current_db_path,
            ).rebuild(tasks)

        vector_store = self.vector_store_manager or self._build_vector_store_manager()
        rebuilt = 0
        for task_id in tasks:
            if not (self.note_output_root / f"{task_id}.json").exists():
                continue
            vector_store.index_task(task_id)
            rebuilt += 1

        return {
            "wiki_rebuilt": True,
            "vector_rebuilt": rebuilt,
            "knowledge_rebuilt": knowledge_result["indexed"],
            "task_ids": tasks,
        }

    def _build_vector_store_manager(self):
        from app.services.vector_store import VectorStoreManager

        return VectorStoreManager()

    def _task_ids_from_db(self) -> list[str]:
        if not self.current_db_path.exists():
            return []
        conn = sqlite3.connect(self.current_db_path)
        try:
            rows = conn.execute(
                """
                SELECT task_id
                FROM note_documents
                WHERE deleted_at IS NULL
                ORDER BY created_at ASC, updated_at ASC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()
        return [row[0] for row in rows if row and row[0]]

    def _normalize_task_ids(self, task_ids: list[str]) -> list[str]:
        normalized: list[str] = []
        for task_id in task_ids:
            value = str(task_id or "").strip()
            if value and value not in normalized:
                normalized.append(value)
        return normalized
