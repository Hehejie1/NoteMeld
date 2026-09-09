from __future__ import annotations

import pytest

from app.agent_host.preferences import ModelConfigurationRequired, select_model


def test_model_precedence(monkeypatch):
    monkeypatch.setattr(
        "app.agent_host.preferences.agent_store.get_model_preference",
        lambda session_id: {"default_model_id": "saved", "fallback_models": ["fallback"]}
        if session_id != "missing"
        else {"default_model_id": None, "fallback_models": []},
    )
    assert select_model("explicit", "s1", ["first"]) == "explicit"
    assert select_model(None, "s1", ["first"]) == "saved"
    assert select_model(None, "missing", ["first"]) == "first"


def test_model_required_when_empty(monkeypatch):
    monkeypatch.setattr("app.agent_host.preferences.agent_store.get_model_preference", lambda _: {"default_model_id": None, "fallback_models": []})
    with pytest.raises(ModelConfigurationRequired):
        select_model(None, "s1", [])
