from pathlib import Path
from types import SimpleNamespace

from app.routers import cloud_sync


class _Identity:
    private_key = b"private"
    public_key = b"public"


class _Client:
    def __init__(self, base_url, *, token, device_id):
        self.base_url = base_url
        self.token = token
        self.device_id = device_id
        self.registered = None
        self.closed = False

    def register_device(self, *args, **kwargs):
        self.registered = (args, kwargs)
        return {"device_id": args[0]}

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
    assert runtime.cloud_client.registered[1]["public_key"] == "cHVibGlj"
    assert runtime.cloud_client.registered[1]["lan_endpoints"] == ["127.0.0.1:8584"]
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
