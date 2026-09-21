from __future__ import annotations

import json
import time
from typing import Any, Optional

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.db.engine import engine, get_db
from app.db.models.template_extraction_task import TemplateExtractionTask


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _extract_analysis_summary(request_payload: dict[str, Any]) -> dict[str, Any] | None:
    summary = request_payload.get("analysis_summary")
    return summary if isinstance(summary, dict) else None


def _to_dict(row: TemplateExtractionTask) -> dict[str, Any]:
    request_payload = _loads(row.request_payload_json, {})
    return {
        "task_id": row.task_id,
        "status": row.status,
        "stage": row.stage,
        "messages": _loads(row.messages_json, []),
        "chunks": _loads(row.chunks_json, []),
        "provider_id": row.provider_id or "",
        "model_name": row.model_name or "",
        "file_name": row.file_name or "",
        "progress": row.progress or 0,
        "request_type": row.request_type or "",
        "request_payload": request_payload,
        "analysis_summary": _extract_analysis_summary(request_payload),
        "user_message": _loads(row.user_message_json, {}),
        "result": _loads(row.result_json, None),
        "error": row.error,
        "created_at": row.created_at.timestamp() if row.created_at else None,
        "updated_at": row.updated_at.timestamp() if row.updated_at else None,
    }


def ensure_template_extraction_task_table() -> None:
    TemplateExtractionTask.__table__.create(bind=engine, checkfirst=True)


def create_task_record(task: dict[str, Any]) -> dict[str, Any]:
    ensure_template_extraction_task_table()
    db: Session = next(get_db())
    try:
        row = TemplateExtractionTask(
            task_id=task["task_id"],
            status=task.get("status") or "pending",
            stage=task.get("stage") or "created",
            messages_json=_dumps(task.get("messages") or []),
            chunks_json=_dumps(task.get("chunks") or []),
            provider_id=task.get("provider_id") or "",
            model_name=task.get("model_name") or "",
            file_name=task.get("file_name") or "",
            progress=int(task.get("progress") or 0),
            request_type=task.get("request_type") or "",
            request_payload_json=_dumps(task.get("request_payload") or {}),
            user_message_json=_dumps(task.get("user_message") or {}),
            result_json=_dumps(task["result"]) if task.get("result") is not None else None,
            error=task.get("error"),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _to_dict(row)
    finally:
        db.close()


def update_task_record(task_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
    ensure_template_extraction_task_table()
    db: Session = next(get_db())
    try:
        row = db.query(TemplateExtractionTask).filter_by(task_id=task_id).first()
        if not row:
            return None
        if "status" in updates:
            row.status = updates["status"]
        if "stage" in updates:
            row.stage = updates["stage"]
        if "messages" in updates:
            row.messages_json = _dumps(updates.get("messages") or [])
        if "chunks" in updates:
            row.chunks_json = _dumps(updates.get("chunks") or [])
        if "provider_id" in updates:
            row.provider_id = updates.get("provider_id") or ""
        if "model_name" in updates:
            row.model_name = updates.get("model_name") or ""
        if "file_name" in updates:
            row.file_name = updates.get("file_name") or ""
        if "progress" in updates:
            row.progress = int(updates.get("progress") or 0)
        if "request_type" in updates:
            row.request_type = updates.get("request_type") or ""
        if "request_payload" in updates:
            row.request_payload_json = _dumps(updates.get("request_payload") or {})
        if "user_message" in updates:
            row.user_message_json = _dumps(updates.get("user_message") or {})
        if "result" in updates:
            row.result_json = _dumps(updates["result"]) if updates.get("result") is not None else None
        if "error" in updates:
            row.error = updates.get("error")
        db.commit()
        db.refresh(row)
        return _to_dict(row)
    finally:
        db.close()


def get_task_record(task_id: str) -> Optional[dict[str, Any]]:
    ensure_template_extraction_task_table()
    db: Session = next(get_db())
    try:
        row = db.query(TemplateExtractionTask).filter_by(task_id=task_id).first()
        return _to_dict(row) if row else None
    finally:
        db.close()


def list_task_records(
    *,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
) -> dict[str, Any]:
    ensure_template_extraction_task_table()
    db: Session = next(get_db())
    try:
        query = db.query(TemplateExtractionTask)
        if status:
            query = query.filter(TemplateExtractionTask.status == status)
        rows = (
            query
            .order_by(TemplateExtractionTask.id.desc())
            .offset(max(offset, 0))
            .limit(max(limit, 1) + 1)
            .all()
        )
        items = [_to_dict(row) for row in rows[: max(limit, 1)]]
        has_more = len(rows) > max(limit, 1)
        next_offset = max(offset, 0) + len(items) if has_more else None
        return {
            "items": items,
            "has_more": has_more,
            "next_offset": next_offset,
        }
    finally:
        db.close()


def get_latest_task_record() -> Optional[dict[str, Any]]:
    ensure_template_extraction_task_table()
    db: Session = next(get_db())
    try:
        row = (
            db.query(TemplateExtractionTask)
            .order_by(
                case(
                    (
                        TemplateExtractionTask.status.in_(["pending", "running", "retrying"]),
                        0,
                    ),
                    else_=1,
                ),
                TemplateExtractionTask.created_at.desc(),
            )
            .first()
        )
        return _to_dict(row) if row else None
    finally:
        db.close()


def cleanup_task_records(
    *,
    keep_latest: int = 20,
    max_age_seconds: int = 7 * 24 * 60 * 60,
    statuses: tuple[str, ...] = ("succeeded", "failed", "canceled"),
) -> int:
    ensure_template_extraction_task_table()
    db: Session = next(get_db())
    try:
        keep_ids = [
            row.task_id
            for row in (
                db.query(TemplateExtractionTask.task_id)
                .order_by(TemplateExtractionTask.created_at.desc())
                .limit(max(keep_latest, 0))
                .all()
            )
        ]
        threshold = time.time() - max_age_seconds
        rows = (
            db.query(TemplateExtractionTask)
            .filter(TemplateExtractionTask.status.in_(statuses))
            .all()
        )
        deleted = 0
        for row in rows:
            if row.task_id in keep_ids:
                continue
            updated_at = row.updated_at.timestamp() if row.updated_at else 0
            created_at = row.created_at.timestamp() if row.created_at else 0
            if max(updated_at, created_at) >= threshold:
                continue
            db.delete(row)
            deleted += 1
        db.commit()
        return deleted
    finally:
        db.close()
