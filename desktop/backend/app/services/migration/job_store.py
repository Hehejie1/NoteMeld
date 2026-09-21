from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.migration.validation import ensure_child_path, validate_path_component
from app.utils.storage_paths import migration_jobs_dir


class MigrationJobStore:
    SCHEMA_VERSION = "migration_job.v1"

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = Path(output_dir or migration_jobs_dir())

    def job_path(self, job_id: str) -> Path:
        safe_job_id = validate_path_component(job_id, "job_id")
        return ensure_child_path(self.output_dir, self.output_dir / f"{safe_job_id}_migration_job.json", "job_id")

    def read(self, job_id: str) -> dict[str, Any]:
        path = self.job_path(job_id)
        if not path.exists():
            return self._default_payload(job_id)
        return self._load_json(path)

    def write_progress(self, job_id: str, stage: str, progress: int, message: str) -> dict[str, Any]:
        payload = self.read(job_id)
        payload["status"] = "running"
        payload["stage"] = stage
        payload["progress"] = self._clamp_progress(progress)
        payload["updated_at"] = self._now()
        payload["events"].append(
            {
                "stage": stage,
                "progress": payload["progress"],
                "message": message,
                "created_at": payload["updated_at"],
            }
        )
        self._write(job_id, payload)
        return payload

    def mark_completed(
        self,
        job_id: str,
        summary: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = self.read(job_id)
        payload["status"] = "completed"
        payload["progress"] = 100
        payload["summary"] = dict(summary or {})
        payload["warnings"] = [str(item) for item in (warnings or [])]
        payload["error"] = ""
        payload["recoverable"] = False
        payload["completed_at"] = self._now()
        payload["updated_at"] = payload["completed_at"]
        self._write(job_id, payload)
        return payload

    def mark_failed(self, job_id: str, error: str, recoverable: bool = False) -> dict[str, Any]:
        payload = self.read(job_id)
        payload["status"] = "failed"
        payload["error"] = error
        payload["recoverable"] = recoverable
        payload["completed_at"] = self._now()
        payload["updated_at"] = payload["completed_at"]
        self._write(job_id, payload)
        return payload

    def _default_payload(self, job_id: str) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "job_id": job_id,
            "status": "pending",
            "stage": "",
            "progress": 0,
            "events": [],
            "summary": {},
            "warnings": [],
            "error": "",
            "recoverable": False,
            "completed_at": "",
            "updated_at": "",
        }

    def _write(self, job_id: str, payload: dict[str, Any]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.job_path(job_id)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)

    def _load_json(self, path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}

    def _clamp_progress(self, progress: int) -> int:
        return max(0, min(100, int(progress)))

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
