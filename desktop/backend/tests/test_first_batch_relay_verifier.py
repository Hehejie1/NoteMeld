from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_first_batch_relay.py"
COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64
SPEC = importlib.util.spec_from_file_location("verify_first_batch_relay", SCRIPT)
assert SPEC and SPEC.loader
relay_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay_tool)


class FakeSocket:
    def __init__(self, relay, device_id: str):
        self.relay = relay
        self.device_id = device_id
        self.inbox: list[str] = []

    def __enter__(self):
        self.relay.connected[self.device_id] = self
        self.inbox.append(json.dumps({"type": "relay_ready", "next_sequence": self.relay.last_sequence.get(self.device_id, 0) + 1}))
        return self

    def __exit__(self, *_args):
        self.relay.connected.pop(self.device_id, None)

    def send(self, raw: str):
        frame = json.loads(raw)
        expected = self.relay.last_sequence.get(self.device_id, 0) + 1
        assert frame["sequence"] == expected
        self.relay.last_sequence[self.device_id] = frame["sequence"]
        target = self.relay.connected.get(frame["recipient_device_id"])
        if target is None:
            self.inbox.append(json.dumps({"type": "failed", "error": "host_offline", "frame_id": frame["frame_id"]}))
            return
        target.inbox.append(raw)
        self.inbox.append(json.dumps({"type": "relay_accepted", "frame_id": frame["frame_id"]}))

    def recv(self, timeout: float):
        assert timeout == 15
        assert self.inbox
        return self.inbox.pop(0)


class FakeRelay:
    def __init__(self):
        self.connected: dict[str, FakeSocket] = {}
        self.last_sequence: dict[str, int] = {}
        self.connect_calls: list[tuple[str, dict]] = []

    def connect(self, url: str, **kwargs):
        self.connect_calls.append((url, kwargs))
        device_id = parse_qs(urlparse(url).query)["device_id"][0]
        return FakeSocket(self, device_id)


def fake_api():
    calls: list[tuple[str, str, object, object]] = []

    def request(_base_url, method, path, *, token=None, payload=None):
        calls.append((method, path, token, payload))
        if path == "/ready":
            return {"build_commit": COMMIT, "image_digest": DIGEST}
        if path == "/v1/auth/login":
            return {"token": "account-secret-token"}
        if path.endswith("/challenge"):
            return {"challenge": "proof-challenge"}
        if path.endswith("/token"):
            return {"token": f"device-secret-{len(calls)}"}
        if path == "/v1/grants":
            return {"grant_id": "grant-live"}
        if path == "/v1/sessions":
            return {"id": "session-live"}
        return {"ok": True}

    return request, calls


def test_live_relay_verifier_proves_offline_and_bidirectional_e2ee_without_leaking_secrets():
    pytest.importorskip("cryptography")
    request, calls = fake_api()
    relay = FakeRelay()
    plaintext = b"this-plaintext-must-not-appear-in-evidence"

    result = relay_tool.run(
        "https://cloud.example.test/api",
        "admin",
        "password-secret",
        request_fn=request,
        connect_fn=relay.connect,
        verification_plaintext=plaintext,
    )

    assert result["release_checks"] == {"c_04": "PASS", "c_05_transport_recovery": "PASS"}
    assert result["offline_error"] == "host_offline"
    assert result["forward_transport"] == "relay"
    assert result["forward_cipher"] == "AES-256-GCM"
    assert result["key_agreement"] == "X25519+HKDF-SHA256"
    assert result["build_commit"] == COMMIT
    assert result["cloud_image_digest"] == DIGEST
    assert result["controller_recovery_sequence"] == 3
    assert result["host_recovery_sequence"] == 2
    assert result["recovery_command_frame_id"] != result["command_frame_id"]
    serialized = json.dumps(result)
    assert plaintext.decode() not in serialized
    assert "password-secret" not in serialized
    assert "account-secret-token" not in serialized
    assert "device-secret" not in serialized
    assert len(relay.connect_calls) == 4
    assert all(url.startswith("wss://cloud.example.test/api/v1/relay/connect/session-live") for url, _ in relay.connect_calls)
    assert all("Authorization" in kwargs["additional_headers"] for _, kwargs in relay.connect_calls)
    assert [method for method, path, *_ in calls if path.startswith("/v1/devices/") and method == "DELETE"] == ["DELETE", "DELETE"]
    assert any(method == "DELETE" and path == "/v1/sessions/session-live" for method, path, *_ in calls)


def test_live_relay_verifier_rejects_non_https_cloud():
    request, _calls = fake_api()
    with pytest.raises(relay_tool.VerificationError, match="HTTPS"):
        relay_tool.run("http://127.0.0.1:8583", "admin", "password", request_fn=request, connect_fn=FakeRelay().connect)


def test_live_relay_verifier_rejects_cursor_reset_after_reconnect():
    pytest.importorskip("cryptography")
    request, _calls = fake_api()

    class ResettingRelay(FakeRelay):
        def connect(self, url: str, **kwargs):
            if len(self.connect_calls) == 2:
                self.last_sequence.clear()
            return super().connect(url, **kwargs)

    with pytest.raises(relay_tool.VerificationError, match="continue monotonically"):
        relay_tool.run(
            "https://cloud.example.test/api",
            "admin",
            "password",
            request_fn=request,
            connect_fn=ResettingRelay().connect,
        )


def test_websocket_url_preserves_cloud_base_path_and_escapes_identifiers():
    assert relay_tool._websocket_url("https://cloud.example.test/api", "session/id", "device id") == (
        "wss://cloud.example.test/api/v1/relay/connect/session%2Fid?device_id=device+id"
    )
