import asyncio
from pathlib import Path

from app.cloud_sync.runtime import CloudSyncHostRuntime


class _Client:
    device_id = "host"
    base_url = "https://cloud.example"
    token = "token"

    def close(self):
        pass


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
