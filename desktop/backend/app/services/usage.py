from __future__ import annotations

from datetime import datetime

from app.db.usage_dao import (
    get_usage_overview,
    list_task_usage_calls,
    list_task_usage_summary,
    list_usage_records,
)


class UsageService:
    @staticmethod
    def _parse_dt(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def get_overview(**filters):
        return get_usage_overview(
            start_at=UsageService._parse_dt(filters.get("start_at")),
            end_at=UsageService._parse_dt(filters.get("end_at")),
            task_id=filters.get("task_id"),
            provider_id=filters.get("provider_id"),
            model_name=filters.get("model_name"),
            status=filters.get("status"),
        )

    @staticmethod
    def get_records(**filters):
        return list_usage_records(
            start_at=UsageService._parse_dt(filters.get("start_at")),
            end_at=UsageService._parse_dt(filters.get("end_at")),
            task_id=filters.get("task_id"),
            provider_id=filters.get("provider_id"),
            model_name=filters.get("model_name"),
            status=filters.get("status"),
        )

    @staticmethod
    def get_task_summary(**filters):
        return list_task_usage_summary(
            start_at=UsageService._parse_dt(filters.get("start_at")),
            end_at=UsageService._parse_dt(filters.get("end_at")),
            task_id=filters.get("task_id"),
            provider_id=filters.get("provider_id"),
            model_name=filters.get("model_name"),
        )

    @staticmethod
    def get_task_calls(task_id: str):
        return list_task_usage_calls(task_id)
