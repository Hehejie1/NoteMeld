from __future__ import annotations

import types

import pytest

from app.agent_host.runtime import AgentSdkRuntime, AgentSdkUnavailable


def test_loader_accepts_compatible_python_binding(monkeypatch):
    module = types.SimpleNamespace(SDK_VERSION="0.1.0", SCHEMA_VERSION="1")
    monkeypatch.setattr(AgentSdkRuntime, "_load_binding", staticmethod(lambda _path: module))

    runtime = AgentSdkRuntime.load(binding_path="development")

    assert runtime.mode == "rust"
    assert runtime.sdk_version == "0.1.0"
    assert runtime.schema_version == "1"


def test_loader_fails_closed_on_incompatible_schema(monkeypatch):
    module = types.SimpleNamespace(SDK_VERSION="0.1.0", SCHEMA_VERSION="99")
    monkeypatch.setattr(AgentSdkRuntime, "_load_binding", staticmethod(lambda _path: module))

    with pytest.raises(AgentSdkUnavailable, match="schema"):
        AgentSdkRuntime.load(binding_path="development")


def test_loader_supports_explicit_python_oracle_rollback(monkeypatch):
    runtime = AgentSdkRuntime.load(mode="python-oracle")

    assert runtime.mode == "python-oracle"
    assert runtime.binding is None


def test_loader_does_not_expose_provider_payload(monkeypatch):
    module = types.SimpleNamespace(SDK_VERSION="0.1.0", SCHEMA_VERSION="1")
    monkeypatch.setattr(
        AgentSdkRuntime,
        "_load_binding",
        staticmethod(lambda _path: (_ for _ in ()).throw(RuntimeError("api_key=secret"))),
    )

    with pytest.raises(AgentSdkUnavailable) as exc_info:
        AgentSdkRuntime.load(binding_path="development")
    assert "secret" not in str(exc_info.value)
    assert "api_key" not in str(exc_info.value)
