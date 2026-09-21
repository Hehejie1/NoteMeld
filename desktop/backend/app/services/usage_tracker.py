from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from app.db.usage_dao import insert_usage_record
from app.utils.logger import get_logger

logger = get_logger(__name__)


def record_usage(
    *,
    provider_id: str,
    provider_name: str,
    model_name: str,
    phase: str = "chat",
    task_id: Optional[str] = None,
    platform: Optional[str] = None,
    video_id: Optional[str] = None,
    video_title: Optional[str] = None,
    response: Optional[object] = None,
    response_usage: Optional[object] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
    duration_ms: Optional[int] = None,
    request_meta: Optional[dict] = None,
) -> None:
    """通用 LLM 用量记录工具。

    所有直接调用 LLM API 的路径都应通过此函数记录用量，
    确保 Token 消耗统计的完整性。

    response: 完整的 API 响应对象（非流式场景），会自动提取 usage
    response_usage: 直接传入 usage 对象（流式场景），优先级高于 response
    """
    now = datetime.now(timezone.utc)
    if started_at is None:
        started_at = now
    if finished_at is None:
        finished_at = now
    if duration_ms is None:
        duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))

    if response_usage is not None:
        usage = response_usage
    elif response is not None:
        usage = getattr(response, "usage", None)
    else:
        usage = None

    prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
    completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
    total_tokens = getattr(usage, "total_tokens", None) if usage else None

    payload = {
        "task_id": task_id,
        "provider_id": provider_id or "unknown",
        "provider_name": provider_name or "unknown",
        "model_name": model_name,
        "phase": phase,
        "platform": platform,
        "video_id": video_id,
        "video_title": video_title,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "status": status,
        "error_message": error_message,
        "request_started_at": started_at,
        "request_finished_at": finished_at,
        "duration_ms": duration_ms,
        "request_meta_json": json.dumps(request_meta or {}, ensure_ascii=False),
    }

    try:
        insert_usage_record(payload)
    except Exception as exc:
        logger.warning(f"写入 token 记录失败: {exc}")
