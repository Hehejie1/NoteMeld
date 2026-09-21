from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.utils.storage_paths import note_output_dir


class IngestionJobStore:
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir or note_output_dir())

    def job_path(self, job_id: str) -> Path:
        return self.output_dir / f"{job_id}_ingestion_job.json"

    def write_event(self, job_id: str, stage: str, progress: int, message: str) -> dict:
        payload = self._read_or_default(job_id)
        payload["status"] = "running"
        payload["events"].append({
            "stage": stage,
            "progress": progress,
            "message": message,
            "created_at": self._now(),
        })
        self._write(job_id, payload)
        return payload

    def mark_completed(self, job_id: str) -> dict:
        payload = self._read_or_default(job_id)
        payload["status"] = "completed"
        payload["completed_at"] = self._now()
        self._write(job_id, payload)
        return payload

    def mark_failed(self, job_id: str, error: str) -> dict:
        payload = self._read_or_default(job_id)
        payload["status"] = "failed"
        payload["error"] = error
        payload["completed_at"] = self._now()
        self._write(job_id, payload)
        return payload

    def read(self, job_id: str) -> dict:
        return self._read_or_default(job_id)

    def list(self, limit: int = 50) -> list[dict]:
        rows: list[dict] = []
        for path in self.output_dir.glob("*_ingestion_job.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("job_id"):
                rows.append(payload)
        rows.sort(key=lambda item: str(item.get("completed_at") or item.get("updated_at") or ""), reverse=True)
        return rows[: max(1, min(limit, 200))]

    def _read_or_default(self, job_id: str) -> dict:
        path = self.job_path(job_id)
        if not path.exists():
            return {
                "schema_version": "ingestion_job.v1",
                "job_id": job_id,
                "status": "pending",
                "events": [],
                "error": "",
                "completed_at": "",
            }
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, job_id: str, payload: dict) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.job_path(job_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
