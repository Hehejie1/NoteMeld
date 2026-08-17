from __future__ import annotations

import types
import sys

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


@pytest.mark.parametrize("mode", ["python", "python-oracle", "legacy"])
def test_loader_rejects_legacy_python_runtime(mode):
    with pytest.raises(AgentSdkUnavailable, match="legacy Python Agent runtime is removed"):
        AgentSdkRuntime.load(mode=mode)


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


def test_loader_uses_explicit_external_sdk_source(monkeypatch, tmp_path):
    source_root = tmp_path / "notemeld-agent-sdk" / "bindings" / "python"
    (source_root / "notemeld_agent_sdk").mkdir(parents=True)
    imported = types.SimpleNamespace(SDK_VERSION="0.1.0", SCHEMA_VERSION="1")
    observed: list[str] = []
    monkeypatch.setenv("NOTEMELD_AGENT_SDK_PYTHON_PATH", str(source_root))
    monkeypatch.setattr(
        "app.agent_host.runtime.importlib.import_module",
        lambda name: (observed.append(name) or imported),
    )

    AgentSdkRuntime._load_binding("development")

    assert observed == ["notemeld_agent_sdk.runtime"]
    assert str(source_root) in sys.path
