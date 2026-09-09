from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.plugins.manager import PluginManager
from app.services.usage import UsageService


class MonitoringSnapshotService:
    """Build one bounded, read-only runtime snapshot for the monitoring app."""

    @staticmethod
    async def get_snapshot(*, days: int = 1, provider_id: str | None = None) -> dict[str, Any]:
        if not 1 <= days <= 31:
            raise ValueError("days must be between 1 and 31")

        end_at = datetime.now(timezone.utc)
        start_at = end_at - timedelta(days=days)
        filters = {
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "provider_id": provider_id,
        }
        usage = UsageService.get_overview(**filters)
        task_summary = UsageService.get_task_summary(**filters)
        records = UsageService.get_records(**filters)
        runtime = await MonitoringSnapshotService._runtime_status()
        plugins = MonitoringSnapshotService._plugin_status()

        components = {
            "backend": "healthy" if runtime.get("backend", {}).get("status") == "running" else "degraded",
            "cuda": "healthy" if runtime.get("cuda", {}).get("available") else "unavailable",
            "ffmpeg": "healthy" if runtime.get("ffmpeg", {}).get("available") else "degraded",
            "mcp": "healthy" if runtime.get("mcp", {}).get("status") == "running" else "degraded",
            "plugins": "healthy" if plugins["ready"] else "degraded",
        }
        overall = "healthy" if all(value in {"healthy", "unavailable"} for value in components.values()) else "degraded"

        return {
            "window": {"days": days, "start_at": start_at.isoformat(), "end_at": end_at.isoformat(), "provider_id": provider_id},
            "health": {"status": overall, "components": components},
            "usage": {
                "total_tokens": int((usage or {}).get("total_tokens") or 0),
                "record_count": int((usage or {}).get("call_count") or 0),
                "overview": usage or {},
            },
            "tasks": MonitoringSnapshotService._task_counts(task_summary),
            "task_rows": task_summary or [],
            "providers": MonitoringSnapshotService._provider_counts(records),
            "runtime": runtime,
            "plugins": plugins,
        }

    @staticmethod
    def _task_counts(rows: list[dict[str, Any]] | None) -> dict[str, int]:
        counts = {"task_count": 0, "call_count": 0, "running": 0, "completed": 0, "failed": 0, "other": 0}
        for row in rows or []:
            counts["task_count"] += 1
            counts["call_count"] += int(row.get("call_count") or 0)
            status = str(row.get("status") or "").lower()
            if status in counts:
                counts[status] += 1
            else:
                counts["other"] += 1
        return counts

    @staticmethod
    def _provider_counts(records: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for record in records or []:
            provider_id = str(record.get("provider_id") or "unknown")
            item = grouped.setdefault(provider_id, {"provider_id": provider_id, "provider_name": record.get("provider_name") or provider_id, "call_count": 0, "total_tokens": 0, "failed": 0})
            item["call_count"] += 1
            item["total_tokens"] += int(record.get("total_tokens") or 0)
            if str(record.get("status") or "").lower() == "failed":
                item["failed"] += 1
        return sorted(grouped.values(), key=lambda item: (-item["total_tokens"], item["provider_id"]))

    @staticmethod
    async def _runtime_status() -> dict[str, Any]:
        # Import lazily to avoid making the config router a module import dependency
        # for usage/monitoring tests and to reuse the existing deploy status contract.
        from app.routers.config import deploy_status

        response = await deploy_status()
        body = json.loads(response.body.decode("utf-8"))
        return body.get("data") or {}

    @staticmethod
    def _plugin_status() -> dict[str, Any]:
        try:
            rows = PluginManager().list()
        except Exception:
            return {"ready": False, "failed_plugins": [], "status": "unavailable"}
        failed = [
            row.get("plugin_id")
            for row in rows
            if row.get("enabled") and row.get("runtime_status") != "running"
        ]
        return {"ready": not failed, "failed_plugins": failed, "status": "ready" if not failed else "degraded"}
