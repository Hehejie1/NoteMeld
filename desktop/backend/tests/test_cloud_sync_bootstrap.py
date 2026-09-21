from pathlib import Path
from types import SimpleNamespace

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.routers import cloud_sync


_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))


class _Identity:
    private_key = bytes(range(32))
    public_key = _PRIVATE_KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


class _Client:
    def __init__(self, base_url, *, token, device_id):
        self.base_url = base_url
        self.token = token
        self.device_id = device_id
        self.registered = None
        self.challenge_verified = None
        self.device_token = None
        self.closed = False

    def register_device(self, *args, **kwargs):
        self.registered = (args, kwargs)
        return {"device_id": args[0]}

    def request_device_challenge(self, device_id):
        assert device_id == self.device_id
        return {"challenge": "host-proof-challenge"}

    def verify_device_challenge(self, challenge, signature, device_id):
        self.challenge_verified = (challenge, signature, device_id)
        return {"verified": True}

    def create_device_token(self, scopes, **kwargs):
        self.device_token = (scopes, kwargs)
        self.token = "device-token"
        return {"token": self.token}

    def close(self):
        self.closed = True


class _Runtime:
    instances = []

    def __init__(self, **kwargs):
        self.host_device_id = kwargs["host_device_id"]
        self.cloud_client = kwargs["cloud_client"]
        self.installed = False
        self.closed = False
        self.__class__.instances.append(self)

    def install(self, app):
        self.installed = True

    def close(self):
        self.closed = True
        self.cloud_client.close()

    def host_status(self):
        return {
            "status": "stopped" if self.closed else "running",
            "device_id": self.host_device_id,
            "public_key_sha256": "fingerprint",
        }


def test_bootstrap_installs_os_identity_backed_runtime(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cloud_sync, "OsIdentityStore", lambda: SimpleNamespace(load_or_create=lambda: _Identity()))
    monkeypatch.setattr(cloud_sync, "CloudClient", _Client)
    monkeypatch.setattr(cloud_sync, "CloudSyncHostRuntime", _Runtime)
    monkeypatch.setattr(cloud_sync, "data_root", lambda: tmp_path)
    _Runtime.instances.clear()
    app = SimpleNamespace(state=SimpleNamespace())

    result = cloud_sync.bootstrap_host(
        cloud_sync.HostBootstrapRequest(
            base_url="https://cloud.example",
            token="short-lived-token",
            device_id="desktop-1",
            display_name="Desktop",
            lan_endpoints=["127.0.0.1:8584"],
        ),
        SimpleNamespace(app=app),
    )

    runtime = _Runtime.instances[0]
    assert result["status"] == "started"
    assert result["device_id"] == "desktop-1"
    assert runtime.installed is True
    assert runtime.cloud_client.registered[0] == ("desktop-1", "desktop", "Desktop")
    assert runtime.cloud_client.registered[1]["public_key"] == "A6EHv_POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg"
    assert runtime.cloud_client.registered[1]["lan_endpoints"] == ["127.0.0.1:8584"]
    assert runtime.cloud_client.challenge_verified[0] == "host-proof-challenge"
    assert runtime.cloud_client.challenge_verified[2] == "desktop-1"
    assert runtime.cloud_client.device_token == (["device.read", "device.write", "grant.read", "session.read"], {"device_id": "desktop-1", "revoke_source_token": False})
    assert runtime.cloud_client.token == "device-token"
    assert app.state.cloud_sync_runtime is runtime


def test_bootstrap_replaces_runtime_for_a_different_device(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(cloud_sync, "OsIdentityStore", lambda: SimpleNamespace(load_or_create=lambda: _Identity()))
    monkeypatch.setattr(cloud_sync, "CloudClient", _Client)
    monkeypatch.setattr(cloud_sync, "CloudSyncHostRuntime", _Runtime)
    monkeypatch.setattr(cloud_sync, "data_root", lambda: tmp_path)
    _Runtime.instances.clear()
    previous = _Runtime(host_device_id="old", cloud_client=_Client("https://cloud.example", token="old", device_id="old"))
    app = SimpleNamespace(state=SimpleNamespace(cloud_sync_runtime=previous))

    cloud_sync.bootstrap_host(
        cloud_sync.HostBootstrapRequest(base_url="https://cloud.example", token="new", device_id="new"),
        SimpleNamespace(app=app),
    )

    assert previous.closed is True
    assert app.state.cloud_sync_runtime.host_device_id == "new"


def test_host_status_is_credential_free():
    runtime = _Runtime(host_device_id="desktop-1", cloud_client=_Client("https://cloud.example", token="secret-token", device_id="desktop-1"))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(cloud_sync_runtime=runtime)))

    result = cloud_sync.host_status(request)

    assert result == {"status": "running", "device_id": "desktop-1", "public_key_sha256": "fingerprint"}
    assert "token" not in result


def test_host_status_reports_stopped_without_runtime():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    assert cloud_sync.host_status(request) == {
        "status": "stopped",
        "device_id": None,
        "public_key_sha256": None,
    }
