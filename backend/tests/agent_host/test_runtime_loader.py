from __future__ import annotations

import types

import pytest

from app.agent_host.runtime import AgentSdkRuntime, AgentSdkUnavailable


def _compatible_binding() -> types.SimpleNamespace:
    return types.SimpleNamespace(SDK_VERSION="0.1.0", SCHEMA_VERSION="1")


def _contract(*, sdk: str = "0.1.0", schema: str = "1", abi: int = 1) -> dict:
    return {
        "sdk_version": sdk,
        "schema_version": schema,
        "abi_version": abi,
        "functions": [],
    }


def _stub_artifact(monkeypatch, binding, *, contract=None, native_library=None) -> None:
    monkeypatch.setattr(AgentSdkRuntime, "_load_binding", staticmethod(lambda _path: binding))
    monkeypatch.setattr(
        AgentSdkRuntime,
        "_read_artifact_contract",
        staticmethod(lambda _binding: (contract or _contract(), {
            "sdk_version": "0.1.0",
            "schema_version": "1",
            "binding_version": "0.1.0",
            "target_triples": ["aarch64-apple-ios"],
            "source_commit": "f926bd7674c98b27895734c0df18e0c0241cb132",
            "artifact_manifest_sha256": "e381e742a8c7916dc7e78756b69b8e5270f9f140d70e62605da9f6759e8abadf",
        })),
    )
    monkeypatch.setattr(
        AgentSdkRuntime,
        "_probe_native_artifact",
        staticmethod(lambda _binding, _path, _contract: native_library),
    )


def test_loader_accepts_compatible_versioned_wheel_and_native_artifact(monkeypatch):
    _stub_artifact(monkeypatch, _compatible_binding())

    runtime = AgentSdkRuntime.load(binding_path="packaged")

    assert runtime.mode == "rust"
    assert runtime.sdk_version == "0.1.0"
    assert runtime.schema_version == "1"
    assert runtime.abi_version == 1
    assert runtime.native_library is None
    assert runtime.source_commit == "f926bd7674c98b27895734c0df18e0c0241cb132"


def test_loader_fails_closed_when_artifact_provenance_is_missing(monkeypatch):
    binding = _compatible_binding()
    monkeypatch.setattr(AgentSdkRuntime, "_load_binding", staticmethod(lambda _path: binding))
    monkeypatch.setattr(
        AgentSdkRuntime,
        "_read_artifact_contract",
        staticmethod(lambda _binding: (_contract(), {
            "sdk_version": "0.1.0", "schema_version": "1", "binding_version": "0.1.0",
            "target_triples": ["aarch64-apple-ios"],
        })),
    )
    with pytest.raises(AgentSdkUnavailable, match="commit|hash"):
        AgentSdkRuntime.load(binding_path="packaged")


def test_loader_fails_closed_on_artifact_hash_mismatch(monkeypatch):
    binding = _compatible_binding()
    _stub_artifact(monkeypatch, binding)
    monkeypatch.setattr(
        AgentSdkRuntime,
        "_read_artifact_contract",
        staticmethod(lambda _binding: (_contract(), {
            "sdk_version": "0.1.0", "schema_version": "1", "binding_version": "0.1.0",
            "target_triples": ["aarch64-apple-ios"],
            "source_commit": "f926bd7674c98b27895734c0df18e0c0241cb132",
            "artifact_manifest_sha256": "0" * 64,
        })),
    )
    with pytest.raises(AgentSdkUnavailable, match="hash"):
        AgentSdkRuntime.load(binding_path="packaged")


def test_loader_fails_closed_when_sdk_package_is_missing(monkeypatch):
    missing = ModuleNotFoundError("package unavailable", name="notemeld_agent_sdk")
    monkeypatch.setattr(
        AgentSdkRuntime,
        "_load_binding",
        staticmethod(lambda _path: (_ for _ in ()).throw(missing)),
    )

    with pytest.raises(AgentSdkUnavailable, match="Agent SDK is not installed"):
        AgentSdkRuntime.load(binding_path="packaged")


def test_loader_fails_closed_on_incompatible_abi(monkeypatch):
    _stub_artifact(monkeypatch, _compatible_binding(), contract=_contract(abi=2))

    with pytest.raises(AgentSdkUnavailable, match="ABI"):
        AgentSdkRuntime.load(binding_path="packaged")


def test_loader_fails_closed_on_incompatible_schema(monkeypatch):
    binding = types.SimpleNamespace(SDK_VERSION="0.1.0", SCHEMA_VERSION="99")
    _stub_artifact(monkeypatch, binding)

    with pytest.raises(AgentSdkUnavailable, match="schema"):
        AgentSdkRuntime.load(binding_path="packaged")


def test_loader_fails_closed_on_incompatible_sdk_version(monkeypatch):
    binding = types.SimpleNamespace(SDK_VERSION="9.9.9", SCHEMA_VERSION="1")
    _stub_artifact(monkeypatch, binding)

    with pytest.raises(AgentSdkUnavailable, match="version"):
        AgentSdkRuntime.load(binding_path="packaged")


def test_loader_fails_closed_on_missing_native_artifact(monkeypatch):
    binding = _compatible_binding()
    _stub_artifact(monkeypatch, binding)
    monkeypatch.setattr(
        AgentSdkRuntime,
        "_probe_native_artifact",
        staticmethod(
            lambda _binding, _path, _contract: (_ for _ in ()).throw(
                AgentSdkUnavailable("Agent SDK native artifact is missing")
            )
        ),
    )

    with pytest.raises(AgentSdkUnavailable, match="native artifact is missing"):
        AgentSdkRuntime.load(binding_path="packaged")


@pytest.mark.parametrize("mode", ["python", "python-oracle", "legacy"])
def test_loader_rejects_legacy_without_calling_any_fallback(monkeypatch, mode):
    called = False

    def forbidden_loader(_path):
        nonlocal called
        called = True
        raise AssertionError("legacy fallback must not load a binding")

    monkeypatch.setattr(AgentSdkRuntime, "_load_binding", staticmethod(forbidden_loader))

    with pytest.raises(AgentSdkUnavailable, match="legacy Python Agent runtime is removed"):
        AgentSdkRuntime.load(mode=mode)
    assert called is False


def test_loader_does_not_expose_provider_payload_or_local_path(monkeypatch):
    monkeypatch.setattr(
        AgentSdkRuntime,
        "_load_binding",
        staticmethod(
            lambda _path: (_ for _ in ()).throw(
                RuntimeError("api_key=secret path=/private/user/provider-payload.json")
            )
        ),
    )

    with pytest.raises(AgentSdkUnavailable) as exc_info:
        AgentSdkRuntime.load(binding_path="packaged")
    assert str(exc_info.value) == "Agent SDK binding initialization failed"


def test_loader_rejects_external_sdk_source_directory(tmp_path):
    source_root = tmp_path / "notemeld-agent-sdk"
    source_root.mkdir()

    with pytest.raises(AgentSdkUnavailable, match="source directories"):
        AgentSdkRuntime._load_binding(str(source_root))
