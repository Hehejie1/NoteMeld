from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


def _default_vector_store_factory():
    from app.services.vector_store import VectorStoreManager

    return VectorStoreManager()


class IngestionMaterializationService:
    def __init__(self, vector_store_factory: Callable | None = None):
        self.vector_store_factory = vector_store_factory or _default_vector_store_factory

    def materialize(self, result) -> dict:
        payload = {
            "schema_version": "ingestion_materialization.v1",
            "job_id": result.request.job_id,
            "chunk_count": len(result.knowledge_chunks),
            "vector_indexed": False,
            "vector_error": "",
        }
        if not any(getattr(chunk, "content", "").strip() for chunk in result.knowledge_chunks):
            payload["vector_error"] = "no_indexable_chunks"
            self._write_payload(result.materialization_path, payload)
            return payload

        try:
            self.vector_store_factory().index_chunks(result.request.job_id, result.knowledge_chunks)
            payload["vector_indexed"] = True
        except Exception as exc:
            payload["vector_error"] = str(exc)

        self._write_payload(result.materialization_path, payload)
        return payload

    def _write_payload(self, path: str, payload: dict) -> None:
        materialization_path = Path(path)
        materialization_path.parent.mkdir(parents=True, exist_ok=True)
        materialization_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
