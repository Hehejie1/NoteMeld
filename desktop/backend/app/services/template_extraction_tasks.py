from __future__ import annotations

import time
import uuid
from copy import deepcopy
from typing import Any

from app.db.template_extraction_task_dao import (
    cleanup_task_records,
    create_task_record,
    get_latest_task_record,
    get_task_record,
    list_task_records,
    update_task_record,
)

_TASKS: dict[str, dict[str, Any]] = {}
DEFAULT_TASK_HISTORY_KEEP_LATEST = 20
DEFAULT_TASK_HISTORY_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def create_task() -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    task = {
        "task_id": task_id,
        "status": "pending",
        "stage": "created",
        "messages": [],
        "chunks": [],
        "provider_id": "",
        "model_name": "",
        "file_name": "",
        "progress": 0,
        "request_type": "",
        "request_payload": {},
        "analysis_summary": None,
        "user_message": {},
        "result": None,
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    _TASKS[task_id] = task
    persisted = create_task_record(task)
    _TASKS[task_id] = persisted
    return deepcopy(persisted)


def reset_task(task_id: str, **updates: Any) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise KeyError(task_id)
    task.update(
        {
            "status": "pending",
            "stage": "created",
            "messages": [],
            "chunks": [],
            "progress": 0,
            "result": None,
            "error": None,
            **updates,
        }
    )
    task["updated_at"] = time.time()
    persisted = update_task_record(task_id, task)
    if persisted is None:
        raise KeyError(task_id)
    _TASKS[task_id] = persisted
    return deepcopy(persisted)


def update_task(task_id: str, **updates: Any) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise KeyError(task_id)
    task.update(updates)
    task["updated_at"] = time.time()
    persisted = update_task_record(task_id, task)
    if persisted is None:
        raise KeyError(task_id)
    _TASKS[task_id] = persisted
    return deepcopy(persisted)


def get_task(task_id: str) -> dict[str, Any] | None:
    task = _TASKS.get(task_id)
    if task:
        return deepcopy(task)
    task = get_task_record(task_id)
    if task:
        _TASKS[task_id] = task
    return deepcopy(task) if task else None


def list_tasks(
    *,
    limit: int = DEFAULT_TASK_HISTORY_KEEP_LATEST,
    offset: int = 0,
    status: str | None = None,
) -> dict[str, Any]:
    page = list_task_records(limit=limit, offset=offset, status=status)
    tasks = page["items"]
    for task in tasks:
        _TASKS[task["task_id"]] = task
    return {
        "items": deepcopy(tasks),
        "has_more": bool(page["has_more"]),
        "next_offset": page["next_offset"],
    }


def get_latest_task() -> dict[str, Any] | None:
    task = get_latest_task_record()
    if task:
        _TASKS[task["task_id"]] = task
    return deepcopy(task) if task else None


def cancel_task(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if not task:
        raise KeyError(task_id)
    if task.get("status") in {"succeeded", "failed", "canceled"}:
        return task
    task.update(
        {
            "status": "canceled",
            "stage": "canceled",
            "error": "用户已取消模板提取任务",
            "messages": [*(task.get("messages") or []), "任务已取消"],
            "updated_at": time.time(),
        }
    )
    persisted = update_task_record(task_id, task)
    if persisted is None:
        raise KeyError(task_id)
    _TASKS[task_id] = persisted
    return deepcopy(persisted)


def is_task_canceled(task_id: str) -> bool:
    task = get_task(task_id)
    return bool(task and task.get("status") == "canceled")


def cleanup_tasks(
    *,
    keep_latest: int = DEFAULT_TASK_HISTORY_KEEP_LATEST,
    max_age_seconds: int = DEFAULT_TASK_HISTORY_MAX_AGE_SECONDS,
) -> int:
    deleted = cleanup_task_records(keep_latest=keep_latest, max_age_seconds=max_age_seconds)
    if deleted > 0:
        persisted_page = list_task_records(limit=max(len(_TASKS), keep_latest, DEFAULT_TASK_HISTORY_KEEP_LATEST))
        persisted_ids = {task["task_id"] for task in persisted_page["items"]}
        stale_ids = [task_id for task_id in _TASKS if task_id not in persisted_ids]
        for task_id in stale_ids:
            _TASKS.pop(task_id, None)
    return deleted


def run_startup_template_task_cleanup() -> int:
    return cleanup_tasks(
        keep_latest=DEFAULT_TASK_HISTORY_KEEP_LATEST,
        max_age_seconds=DEFAULT_TASK_HISTORY_MAX_AGE_SECONDS,
    )
