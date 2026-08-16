from __future__ import annotations

from typing import Iterable

from app.services import agent_store


class ModelConfigurationRequired(RuntimeError):
    code = "model_not_configured"


def select_model(explicit: str | None, session_id: str, available: Iterable[str]) -> str:
    candidates = [str(item).strip() for item in available if str(item).strip()]
    if explicit and explicit.strip():
        return explicit.strip()
    preference = agent_store.get_model_preference(session_id)
    saved = str(preference.get("default_model_id") or "").strip()
    if saved:
        return saved
    fallback = [str(item).strip() for item in preference.get("fallback_models", []) if str(item).strip()]
    if fallback:
        return fallback[0]
    if candidates:
        return candidates[0]
    raise ModelConfigurationRequired("请先配置可用模型")

