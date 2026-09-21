from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_windows_secure_identity.py"
SPEC = importlib.util.spec_from_file_location("verify_windows_secure_identity", SCRIPT)
assert SPEC and SPEC.loader
identity_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(identity_tool)


def test_windows_identity_smoke_round_trips_and_cleans_both_credentials(monkeypatch):
    identity = SimpleNamespace(private_key=b"x" * 32, public_key=b"p" * 32)
    services = []
    deleted = []

    class Store:
        def __init__(self, service):
            services.append(service)

        def load_or_create(self):
            return identity

    monkeypatch.setattr(identity_tool.platform, "system", lambda: "Windows")
    monkeypatch.setattr(identity_tool, "OsIdentityStore", Store)
    monkeypatch.setattr(identity_tool, "_windows_credential_delete", deleted.append)

    result = identity_tool.run()

    assert result["status"] == "PASS"
    assert result["store"] == "Credential Manager"
    assert "private_key" not in result
    assert deleted == [f"{services[0]}.private", f"{services[0]}.public"]


def test_windows_identity_smoke_rejects_other_platforms(monkeypatch):
    monkeypatch.setattr(identity_tool.platform, "system", lambda: "Darwin")
    with pytest.raises(RuntimeError, match="must run on Windows"):
        identity_tool.run()
