import asyncio
from pathlib import Path
import threading

from fastapi import FastAPI

from app.cloud_sync.runtime import CloudSyncHostRuntime, eligible_relay_session_ids


def test_pair_grant_discovers_all_active_device_remote_sessions():
    assert eligible_relay_session_ids(
        [{"host_device_id": "host", "controller_device_id": "controller", "revoked_at": None}],
        [
            {"id": "active", "kind": "device_remote", "status": "idle"},
            {"id": "cloud", "kind": "cloud_native", "status": "idle"},
            {"id": "archived", "kind": "device_remote", "status": "archived"},
        ],
        "host",
    ) == {"active"}


def test_revoked_or_foreign_grants_do_not_start_remote_relays():
    assert eligible_relay_session_ids(
        [
            {"host_device_id": "host", "revoked_at": 1},
            {"host_device_id": "other-host", "revoked_at": None},
        ],
        [{"id": "active", "kind": "device_remote", "status": "idle"}],
        "host",
    ) == set()


class _Client:
    device_id = "host"
    base_url = "https://cloud.example"
    token = "token"

    def heartbeat(self, device_id, lan_endpoints=None):
        return {"device_id": device_id, "lan_endpoints": lan_endpoints or []}

    def close(self):
        pass


def test_sync_runtime_install_starts_relay_discovery(tmp_path: Path, monkeypatch):
    """FastAPI sync bootstrap must not silently skip Relay discovery."""

    class DiscoveringClient(_Client):
        def __init__(self):
            self.heartbeat_seen = threading.Event()

        def heartbeat(self, device_id, lan_endpoints=None):
            self.heartbeat_seen.set()
            return super().heartbeat(device_id, lan_endpoints)

        def list_grants(self):
            return [{"host_device_id": "host", "controller_device_id": "controller", "revoked_at": None}]

        def list_sessions(self, archived):
            assert archived is False
            return [{"id": "session", "kind": "device_remote", "status": "idle"}]

    discovered = threading.Event()
    client = DiscoveringClient()
    runtime = CloudSyncHostRuntime(
        cloud_client=client,
        host_device_id="host",
        mailbox_path=tmp_path / "mailbox.sqlite",
        cipher_resolver=lambda _authorization: None,
    )

    async def start(session_id):
        assert session_id == "session"
        discovered.set()
        return {"status": "started", "session_id": session_id}

    monkeypatch.setattr(runtime, "start_relay_session", start)
    try:
        runtime.install(FastAPI())
        assert discovered.wait(1), "sync bootstrap skipped Relay discovery"
        assert client.heartbeat_seen.wait(1), "Host runtime did not maintain Cloud presence"
    finally:
        runtime.close()


def test_runtime_owns_and_stops_relay_session(monkeypatch, tmp_path: Path):
    class _Relay:
        def __init__(self):
            self.stopped = False

        async def run(self):
            await asyncio.Event().wait()

        async def stop(self):
            self.stopped = True

    relay = _Relay()
    runtime = CloudSyncHostRuntime(
        cloud_client=_Client(),
        host_device_id="host",
        mailbox_path=tmp_path / "mailbox.sqlite",
        cipher_resolver=lambda _authorization: None,
    )
    monkeypatch.setattr(runtime, "relay_session", lambda _session_id: relay)

    async def scenario():
        assert await runtime.start_relay_session("session") == {"status": "started", "session_id": "session"}
        assert await runtime.start_relay_session("session") == {"status": "already_running", "session_id": "session"}
        assert await runtime.stop_relay_session("session") == {"status": "stopped", "session_id": "session"}
        assert relay.stopped is True

    asyncio.run(scenario())
    runtime.close()
