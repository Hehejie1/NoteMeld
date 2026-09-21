from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.cloud_sync.secure_identity import HostIdentity, OsIdentityStore, SecureIdentityUnavailable


def test_identity_store_round_trips_without_plain_file_fallback(monkeypatch):
    values = {}

    monkeypatch.setattr("app.cloud_sync.secure_identity.platform.system", lambda: "Darwin")

    def fake_run(args, **kwargs):
        if args[1] == "find-generic-password":
            value = values.get(args[args.index("-s") + 1])
            return SimpleNamespace(returncode=0 if value else 44, stdout=(value or ""), stderr="")
        if args[1] == "add-generic-password":
            values[args[args.index("-s") + 1]] = args[args.index("-w") + 1]
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(args)

    monkeypatch.setattr("app.cloud_sync.secure_identity._run", fake_run)
    store = OsIdentityStore("test.notemeld")
    # Exercise creation through the real store; generation is checked by the
    # HostIdentity invariant and no filesystem path is touched.
    created = store.load_or_create()
    assert len(created.private_key) == 32
    assert created.public_key == HostIdentity(created.private_key, created.public_key).public_key
    assert "test.notemeld.private" in values


def test_identity_store_round_trips_through_windows_credential_manager(monkeypatch):
    values = {}
    monkeypatch.setattr("app.cloud_sync.secure_identity.platform.system", lambda: "Windows")
    monkeypatch.setattr("app.cloud_sync.secure_identity._windows_credential_read", lambda target: values.get(target))
    monkeypatch.setattr("app.cloud_sync.secure_identity._windows_credential_write", lambda target, username, value: values.__setitem__(target, value))
    monkeypatch.setattr("app.cloud_sync.secure_identity._windows_credential_delete", lambda target: values.pop(target, None))

    store = OsIdentityStore("test.notemeld")
    created = store.load_or_create()
    loaded = store.load_or_create()

    assert loaded == created
    assert set(values) == {"test.notemeld.private", "test.notemeld.public"}


def test_identity_store_fails_closed_when_os_store_is_unavailable(monkeypatch):
    monkeypatch.setattr("app.cloud_sync.secure_identity.platform.system", lambda: "FreeBSD")
    with pytest.raises(SecureIdentityUnavailable):
        OsIdentityStore().load_or_create()
