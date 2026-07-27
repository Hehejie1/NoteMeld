from __future__ import annotations

from datetime import datetime

from sqlalchemy import func

from app.db.engine import SessionLocal
from app.db.models.model_usage_records import ModelUsageRecord


def _apply_usage_filters(query, start_at=None, end_at=None, task_id=None, provider_id=None, model_name=None, status=None):
    if start_at:
        query = query.filter(ModelUsageRecord.created_at >= start_at)
    if end_at:
        query = query.filter(ModelUsageRecord.created_at <= end_at)
    if task_id:
        query = query.filter(ModelUsageRecord.task_id == task_id)
    if provider_id:
        query = query.filter(ModelUsageRecord.provider_id == provider_id)
    if model_name:
        query = query.filter(ModelUsageRecord.model_name == model_name)
    if status:
        query = query.filter(ModelUsageRecord.status == status)
    return query


def insert_usage_record(payload: dict):
    db = SessionLocal()
    try:
        record = ModelUsageRecord(**payload)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
    finally:
        db.close()


def list_usage_records(start_at=None, end_at=None, task_id=None, provider_id=None, model_name=None, status=None):
    db = SessionLocal()
    try:
        query = db.query(ModelUsageRecord)
        query = _apply_usage_filters(
            query,
            start_at=start_at,
            end_at=end_at,
            task_id=task_id,
            provider_id=provider_id,
            model_name=model_name,
            status=status,
        )
        query = query.order_by(ModelUsageRecord.created_at.desc(), ModelUsageRecord.id.desc())
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "provider_id": row.provider_id,
                "provider_name": row.provider_name,
                "model_name": row.model_name,
                "phase": row.phase,
                "platform": row.platform,
                "video_id": row.video_id,
                "video_title": row.video_title,
                "prompt_tokens": row.prompt_tokens or 0,
                "completion_tokens": row.completion_tokens or 0,
                "total_tokens": row.total_tokens or 0,
                "status": row.status,
                "error_message": row.error_message,
                "request_started_at": row.request_started_at.isoformat() if row.request_started_at else None,
                "request_finished_at": row.request_finished_at.isoformat() if row.request_finished_at else None,
                "duration_ms": row.duration_ms,
                "request_meta_json": row.request_meta_json,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in query.all()
        ]
    finally:
        db.close()


def list_task_usage_summary(start_at=None, end_at=None, task_id=None, provider_id=None, model_name=None):
    db = SessionLocal()
    try:
        query = db.query(
            ModelUsageRecord.task_id.label("task_id"),
            func.max(ModelUsageRecord.platform).label("platform"),
            func.max(ModelUsageRecord.video_id).label("video_id"),
            func.max(ModelUsageRecord.video_title).label("video_title"),
            func.count(ModelUsageRecord.id).label("call_count"),
            func.coalesce(func.sum(ModelUsageRecord.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(ModelUsageRecord.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(ModelUsageRecord.total_tokens), 0).label("total_tokens"),
            func.max(ModelUsageRecord.created_at).label("latest_call_at"),
        )
        query = _apply_usage_filters(
            query,
            start_at=start_at,
            end_at=end_at,
            task_id=task_id,
            provider_id=provider_id,
            model_name=model_name,
            status=None,
        )
        query = query.group_by(ModelUsageRecord.task_id).order_by(func.max(ModelUsageRecord.created_at).desc())
        return [
            {
                "task_id": row.task_id,
                "platform": row.platform,
                "video_id": row.video_id,
                "video_title": row.video_title,
                "call_count": row.call_count,
                "prompt_tokens": int(row.prompt_tokens or 0),
                "completion_tokens": int(row.completion_tokens or 0),
                "total_tokens": int(row.total_tokens or 0),
                "latest_call_at": row.latest_call_at.isoformat() if row.latest_call_at else None,
            }
            for row in query.all()
            if row.task_id
        ]
    finally:
        db.close()


def list_task_usage_calls(task_id: str):
    return list_usage_records(task_id=task_id)


def get_usage_overview(start_at=None, end_at=None, task_id=None, provider_id=None, model_name=None, status=None):
    db = SessionLocal()
    try:
        query = db.query(
            func.coalesce(func.sum(ModelUsageRecord.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(ModelUsageRecord.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(ModelUsageRecord.total_tokens), 0).label("total_tokens"),
            func.count(ModelUsageRecord.id).label("call_count"),
            func.count(func.distinct(ModelUsageRecord.task_id)).label("task_count"),
        )
        query = _apply_usage_filters(
            query,
            start_at=start_at,
            end_at=end_at,
            task_id=task_id,
            provider_id=provider_id,
            model_name=model_name,
            status=status,
        )
        row = query.one()
        return {
            "prompt_tokens": int(row.prompt_tokens or 0),
            "completion_tokens": int(row.completion_tokens or 0),
            "total_tokens": int(row.total_tokens or 0),
            "call_count": int(row.call_count or 0),
            "task_count": int(row.task_count or 0),
        }
    finally:
        db.close()
