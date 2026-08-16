"""Compatibility translation from Agent v1 events to the legacy free-chat SSE.

The translator is intentionally side-effect free.  The v1 Host remains the
single producer; callers can use this module when the legacy endpoint is
enabled during the migration window.
"""
from __future__ import annotations

import json
from typing import Any


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def agent_event_to_legacy(event: dict[str, Any], *, answer: str = "") -> dict[str, Any] | None:
    """Map one v1 event to the old ``delta/done/error`` event shape."""
    event_type = event.get("type") or event.get("event_type")
    payload = _payload(event)
    if event_type == "message.delta":
        delta = payload.get("delta")
        return {"type": "delta", "content": delta} if isinstance(delta, str) else None
    if event_type == "turn.succeeded":
        sources = payload.get("sources", [])
        return {"type": "done", "answer": answer, "sources": sources if isinstance(sources, list) else []}
    if event_type in {"turn.failed", "turn.cancelled", "turn.interrupted"}:
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("code") or "agent error"
        else:
            message = "agent cancelled" if event_type == "turn.cancelled" else "agent error"
        return {"type": "error", "message": str(message)}
    return None


def legacy_sse_frame(event: dict[str, Any]) -> str:
    """Serialize one legacy event using the existing SSE data framing."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


__all__ = ["agent_event_to_legacy", "legacy_sse_frame"]
