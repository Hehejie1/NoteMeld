from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.storage_paths import note_output_dir


COLLECTOR_STAGE_KEYS = ("PARSING", "DOWNLOADING", "TRANSCRIBING")
NOTE_OUTPUT_DIR = note_output_dir()
_STATUS_WRITE_LOCK = threading.RLock()


def _clean_timing_map(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}

    cleaned: dict[str, dict[str, Any]] = {}
    for key, timing in value.items():
        if isinstance(key, str) and isinstance(timing, dict):
            cleaned[key] = dict(timing)
    return cleaned


def build_collector_timings(status_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(status_payload, dict):
        return {}

    explicit_timings = _clean_timing_map(status_payload.get("collector_timings"))
    if explicit_timings:
        return explicit_timings

    stage_timings = _clean_timing_map(status_payload.get("stage_timings"))
    return {
        stage: stage_timings[stage]
        for stage in COLLECTOR_STAGE_KEYS
        if stage in stage_timings
    }


def _status_path(task_id: str) -> Path:
    return NOTE_OUTPUT_DIR / f"{task_id}.status.json"


def _read_status_payload(task_id: str) -> dict[str, Any]:
    path = _status_path(task_id)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_status_payload(task_id: str, payload: dict[str, Any]) -> None:
    NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _status_path(task_id)
    temp_path = path.with_name(
        f"{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _update_collector(task_id: str, collector: str, fields: dict[str, Any]) -> None:
    with _STATUS_WRITE_LOCK:
        payload = _read_status_payload(task_id)
        timings = payload.get("collector_timings")
        if not isinstance(timings, dict):
            timings = {}
        current = timings.get(collector)
        if not isinstance(current, dict):
            current = {}
        current.update(fields)
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        timings[collector] = current
        payload["collector_timings"] = timings
        _write_status_payload(task_id, payload)


def mark_collector_running(task_id: str, collector: str, message: str = "") -> None:
    _update_collector(
        task_id,
        collector,
        {
            "status": "running",
            "message": message,
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def mark_collector_done(task_id: str, collector: str, duration_ms: int) -> None:
    _update_collector(task_id, collector, {"status": "done", "duration_ms": max(0, int(duration_ms))})


def mark_collector_failed(task_id: str, collector: str, error: str) -> None:
    _update_collector(task_id, collector, {"status": "failed", "error": error})


def mark_collector_skipped(task_id: str, collector: str, reason: str) -> None:
    _update_collector(task_id, collector, {"status": "skipped", "message": reason})


def read_collector_timings(task_id: str) -> dict[str, dict[str, Any]]:
    return _clean_timing_map(_read_status_payload(task_id).get("collector_timings"))
