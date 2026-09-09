import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Union

from app.db.usage_dao import list_task_usage_summary
from app.enmus.task_status_enums import TaskStatus
from app.services.note_task_store import is_note_task_canceled
from app.utils.storage_paths import note_output_dir


NOTE_OUTPUT_DIR = note_output_dir()
NOTE_PROGRESS_STEPS = [
    TaskStatus.PENDING.value,
    TaskStatus.PARSING.value,
    TaskStatus.DOWNLOADING.value,
    TaskStatus.TRANSCRIBING.value,
    TaskStatus.SUMMARIZING.value,
    TaskStatus.FORMATTING.value,
    TaskStatus.SAVING.value,
    TaskStatus.SUCCESS.value,
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _task_conversation_path(task_id: str) -> Path:
    return NOTE_OUTPUT_DIR / "task_conversations" / f"{task_id}.json"


def register_task_conversation(
    task_id: Optional[str],
    conversation_id: Optional[str],
    source_url: Optional[str] = None,
    extras: Optional[str] = None,
    attempt_id: Optional[str] = None,
) -> None:
    if not task_id or not conversation_id:
        return

    mapping_dir = NOTE_OUTPUT_DIR / "task_conversations"
    mapping_dir.mkdir(parents=True, exist_ok=True)
    existing = get_registered_task_input(task_id)
    previous_attempt = int(existing.get("attempt", 0) or 0)
    payload = {
        **existing,
        "task_id": task_id,
        "conversation_id": conversation_id,
        "attempt": previous_attempt + 1,
        "attempt_id": attempt_id or f"{task_id}:{previous_attempt + 1}",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if source_url:
        payload["source_url"] = source_url
    if extras is not None:
        payload["extras"] = extras
    temp_file = _task_conversation_path(task_id).with_suffix(".tmp")
    temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(_task_conversation_path(task_id))


def _mapped_conversation_id_for_task(task_id: str) -> Optional[str]:
    payload = get_registered_task_input(task_id)
    conversation_id = payload.get("conversation_id")
    return str(conversation_id) if conversation_id else None


def get_registered_task_input(task_id: Optional[str]) -> dict:
    if not task_id:
        return {}
    mapping_path = _task_conversation_path(task_id)
    if not mapping_path.exists():
        return {}
    try:
        payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _status_value(status: Union[str, TaskStatus]) -> str:
    return status.value if isinstance(status, TaskStatus) else status


def _read_status_payload(status_file: Path) -> dict:
    if not status_file.exists():
        return {}
    try:
        payload = json.loads(status_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _elapsed_ms(started_at: Optional[datetime], finished_at: datetime) -> int:
    if started_at is None:
        return 0
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _with_stage_timing(existing: dict, status_value: str, now: datetime) -> dict:
    if status_value == TaskStatus.PENDING.value:
        inherited_timings = {}
        stage_timings = existing.get("stage_timings")
        if isinstance(stage_timings, dict):
            for stage_name in (
                TaskStatus.PENDING.value,
                TaskStatus.PARSING.value,
                TaskStatus.DOWNLOADING.value,
                TaskStatus.TRANSCRIBING.value,
            ):
                stage_timing = stage_timings.get(stage_name)
                if (
                    isinstance(stage_timing, dict)
                    and stage_timing.get("status") == "done"
                    and isinstance(stage_timing.get("duration_ms"), int)
                ):
                    inherited_timings[stage_name] = {
                        "status": "done",
                        "duration_ms": stage_timing["duration_ms"],
                    }
        return {
            "stage_started_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "stage_timings": inherited_timings,
        }

    stage_timings = existing.get("stage_timings")
    if not isinstance(stage_timings, dict):
        stage_timings = {}

    previous_stage = str(existing.get("status") or "")
    previous_started_at = _parse_iso_datetime(str(existing.get("stage_started_at") or ""))
    current_stage_started_at = previous_started_at if previous_stage == status_value else now

    if previous_stage in NOTE_PROGRESS_STEPS and previous_stage != status_value:
        previous_timing = dict(stage_timings.get(previous_stage) or {})
        previous_timing.update({
            "status": "done",
            "duration_ms": _elapsed_ms(previous_started_at, now),
        })
        previous_timing.pop("elapsed_ms", None)
        stage_timings[previous_stage] = previous_timing

    if status_value in NOTE_PROGRESS_STEPS:
        current_timing = dict(stage_timings.get(status_value) or {})
        if status_value == TaskStatus.SUCCESS.value:
            current_timing.update({"status": "done", "duration_ms": current_timing.get("duration_ms", 0)})
            current_timing.pop("elapsed_ms", None)
        else:
            current_timing.update({
                "status": "running",
                "elapsed_ms": _elapsed_ms(current_stage_started_at, now),
            })
        stage_timings[status_value] = current_timing

    return {
        "stage_started_at": current_stage_started_at.isoformat(),
        "updated_at": now.isoformat(),
        "stage_timings": stage_timings,
    }


def _default_message(status_value: str) -> str:
    try:
        return TaskStatus.description(TaskStatus(status_value))
    except Exception:
        return status_value


def _conversation_id_for_task(task_id: str) -> Optional[str]:
    mapped_conversation_id = _mapped_conversation_id_for_task(task_id)
    if mapped_conversation_id:
        return mapped_conversation_id

    try:
        from app.services.conversation_store import list_conversations
    except Exception:
        return None

    try:
        for conversation in list_conversations():
            linked_task_id = conversation.get("linkedNoteTaskId") or conversation.get("linked_note_task_id")
            if linked_task_id == task_id:
                return conversation.get("id")
    except Exception:
        return None
    return None


def _upsert_note_progress_message(
    task_id: str,
    status: Union[str, TaskStatus],
    message: Optional[str],
    progress_status: str,
    status_payload: Optional[dict] = None,
) -> None:
    conversation_id = _conversation_id_for_task(task_id)
    if not conversation_id:
        return

    try:
        from app.services.conversation_store import upsert_progress_message
    except Exception:
        return

    status_value = _status_value(status)
    detail = message or _default_message(status_value)
    task_input = get_registered_task_input(task_id)
    timing_payload = status_payload if isinstance(status_payload, dict) else {}
    upsert_progress_message(
        conversation_id,
        task_id,
        {
            "message_id": f"note-progress-{task_id}-{uuid.uuid5(uuid.NAMESPACE_DNS, task_id)}",
            "status": progress_status,
            "content": detail,
            "current_step": status_value,
            "steps": NOTE_PROGRESS_STEPS,
            "detail": detail,
            "attempt_id": task_input.get("attempt_id", ""),
            "attempt": task_input.get("attempt", 0),
            "source_url": task_input.get("source_url", ""),
            "extras": task_input.get("extras", ""),
            "stage_timings": timing_payload.get("stage_timings", {}),
            "stage_started_at": timing_payload.get("stage_started_at", ""),
            "updated_at": timing_payload.get("updated_at", ""),
        },
    )


def _persist_conversation_status(
    task_id: str,
    status: Union[str, TaskStatus],
    message: Optional[str] = None,
    result_payload: Optional[dict] = None,
) -> None:
    conversation_id = _conversation_id_for_task(task_id)
    if not conversation_id:
        return

    try:
        from app.services.conversation_store import upsert_conversation
    except Exception:
        return

    status_value = _status_value(status)
    if status_value == TaskStatus.FAILED.value and _conversation_has_documents(conversation_id):
        return

    payload = {
        "id": conversation_id,
        "mode": "note",
        "status": status_value,
        "message": message or _default_message(status_value),
        "linkedNoteTaskId": task_id,
        "noteState": "ready" if status_value == TaskStatus.SUCCESS.value else "failed",
    }
    if result_payload:
        payload.update(
            {
                "markdown": result_payload.get("markdown", ""),
                "transcript": result_payload.get("transcript", {}),
                "audioMeta": result_payload.get("audio_meta", {}),
            }
        )

    upsert_conversation(payload)


def _conversation_has_documents(conversation_id: str) -> bool:
    try:
        from app.services.note_document_store import get_note_document_task_ids
    except Exception:
        return False

    try:
        return bool(get_note_document_task_ids(conversation_id))
    except Exception:
        return False


def _read_task_result(task_id: str) -> dict:
    result_path = NOTE_OUTPUT_DIR / f"{task_id}.json"
    if not result_path.exists():
        return {}
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_task_status(task_id: str) -> dict:
    status_path = NOTE_OUTPUT_DIR / f"{task_id}.status.json"
    if not status_path.exists():
        return {}
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _total_duration_ms(stage_timings: dict) -> int:
    total = 0
    for timing in stage_timings.values():
        if not isinstance(timing, dict):
            continue
        duration = timing.get("duration_ms")
        if isinstance(duration, (int, float)) and duration > 0:
            total += int(duration)
    return total


def _task_total_tokens(task_id: str) -> Optional[int]:
    try:
        summaries = list_task_usage_summary(task_id=task_id)
    except Exception:
        return None
    if not summaries:
        return None
    total_tokens = summaries[0].get("total_tokens")
    if isinstance(total_tokens, (int, float)) and total_tokens >= 0:
        return int(total_tokens)
    return None


def _persist_note_document(task_id: str, conversation_id: str, payload: dict, result_payload: dict) -> None:
    if not result_payload.get("markdown"):
        return

    try:
        from app.services.note_document_store import upsert_note_document
    except Exception:
        return

    form_data = {}
    try:
        from app.services.conversation_store import get_conversation

        conversation = get_conversation(conversation_id) or {}
        form_data = conversation.get("formData") or {}
    except Exception:
        form_data = {}

    try:
        upsert_note_document(
            {
                "task_id": task_id,
                "conversation_id": conversation_id,
                "title": payload.get("title") or payload.get("content") or "",
                "content": result_payload.get("markdown", ""),
                "source_url": payload.get("source_url", ""),
                "platform": payload.get("platform") or result_payload.get("audio_meta", {}).get("platform", ""),
                "model_name": form_data.get("model_name", ""),
                "style": form_data.get("style", ""),
                "status": TaskStatus.SUCCESS.value,
                "wiki_status": payload.get("wiki_status", "pending"),
            }
        )
    except Exception:
        return


def _task_status_meta(task_id: str) -> dict:
    task_input = get_registered_task_input(task_id)
    return {
        "attempt_id": task_input.get("attempt_id", ""),
        "attempt": task_input.get("attempt", 0),
        "source_url": task_input.get("source_url", ""),
        "extras": task_input.get("extras", ""),
    }


def write_task_status(task_id: Optional[str], status: Union[str, TaskStatus], message: Optional[str] = None) -> dict:
    if not task_id:
        return {}

    NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    status_file = NOTE_OUTPUT_DIR / f"{task_id}.status.json"
    temp_file = status_file.with_suffix(".tmp")
    status_value = _status_value(status)
    existing = _read_status_payload(status_file)
    if existing.get("status") == TaskStatus.CANCELED.value and status_value != TaskStatus.CANCELED.value:
        return existing
    payload = {"status": _status_value(status), **_task_status_meta(task_id)}
    payload.update(_with_stage_timing(existing, status_value, _now()))
    # 保留已有的 collector_timings，避免被覆盖
    if isinstance(existing.get("collector_timings"), dict):
        payload["collector_timings"] = existing["collector_timings"]
    if message:
        payload["message"] = message

    with temp_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    temp_file.replace(status_file)
    return payload


def emit_note_progress(task_id: Optional[str], status: Union[str, TaskStatus], message: Optional[str] = None) -> None:
    if not task_id:
        return

    status_value = _status_value(status)
    detail = message or _default_message(status_value)
    progress_status = "running"
    if status_value == TaskStatus.SUCCESS.value:
        progress_status = "success"
    elif status_value == TaskStatus.FAILED.value:
        progress_status = "failed"
    elif status_value == TaskStatus.CANCELED.value:
        progress_status = "failed"
    elif status_value == TaskStatus.PENDING.value:
        progress_status = "pending"

    if status_value != TaskStatus.CANCELED.value and is_note_task_canceled(task_id):
        return

    status_payload = write_task_status(task_id, status_value, detail)
    _upsert_note_progress_message(task_id, status_value, detail, progress_status, status_payload)


def emit_note_failed(task_id: Optional[str], message: Optional[str] = None) -> None:
    emit_note_progress(task_id, TaskStatus.FAILED, message)
    if task_id:
        _persist_conversation_status(task_id, TaskStatus.FAILED, message)


def emit_note_success(task_id: Optional[str], message: Optional[str] = None) -> None:
    emit_note_progress(task_id, TaskStatus.SUCCESS, message)


def emit_note_result(task_id: Optional[str], payload: dict) -> None:
    if not task_id:
        return
    if is_note_task_canceled(task_id):
        return

    conversation_id = _conversation_id_for_task(task_id)
    if not conversation_id:
        return

    try:
        from app.services.conversation_store import append_note_result_message
    except Exception:
        return

    status_payload = _read_task_status(task_id)
    stage_timings = status_payload.get("stage_timings") if isinstance(status_payload.get("stage_timings"), dict) else {}
    if stage_timings:
        payload = {
            **payload,
            "stage_timings": stage_timings,
            "total_duration_ms": _total_duration_ms(stage_timings),
        }
    total_tokens = _task_total_tokens(task_id)
    if total_tokens is not None:
        payload = {
            **payload,
            "total_tokens": total_tokens,
        }

    append_note_result_message(task_id=task_id, conversation_id=conversation_id, payload=payload)
    result_payload = _read_task_result(task_id)
    _persist_note_document(task_id, conversation_id, payload, result_payload)
    _persist_conversation_status(task_id, TaskStatus.SUCCESS, payload.get("content"), result_payload)
