from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.enmus.task_status_enums import TaskStatus
from app.utils.storage_paths import note_output_dir


NOTE_OUTPUT_DIR = note_output_dir()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_path(task_id: str) -> Path:
    return NOTE_OUTPUT_DIR / f"{task_id}.status.json"


def _read_status(task_id: str) -> dict:
    path = _status_path(task_id)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def cancel_note_task(task_id: str, message: str = "任务已取消") -> dict:
    if not task_id:
        return {}

    NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = _read_status(task_id)
    payload = {
        **existing,
        "status": TaskStatus.CANCELED.value,
        "message": message,
        "updated_at": _now_iso(),
    }
    status_file = _status_path(task_id)
    temp_file = status_file.with_suffix(".tmp")
    temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(status_file)
    return payload


def is_note_task_canceled(task_id: str) -> bool:
    if not task_id:
        return False
    return _read_status(task_id).get("status") == TaskStatus.CANCELED.value
