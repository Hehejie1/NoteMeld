from __future__ import annotations

import importlib.util
from pathlib import Path
import threading
import time

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_first_batch_c03.py"
COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64
SPEC = importlib.util.spec_from_file_location("verify_first_batch_c03", SCRIPT)
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class FakeCloud:
    def __init__(self, *, duplicate_queued_terminal: bool = False, replay_after_restart: bool = False):
        self.lock = threading.Lock()
        self.commands: dict[str, dict] = {}
        self.restarted = False
        self.recovered = False
        self.archived = False
        self.duplicate_queued_terminal = duplicate_queued_terminal
        self.replay_after_restart = replay_after_restart

    def restart(self, command):
        assert command == ["platformctl", "restart", "notemeld-cloud"]
        with self.lock:
            self.restarted = True

    def request(self, _base_url, method, path, *, token=None, payload=None, timeout_seconds=15):
        del timeout_seconds
        if path == "/ready":
            return {"ready": True, "environment": "production", "agent_backend": "canonical-sdk", "build_commit": COMMIT, "image_digest": DIGEST}
        if path == "/v1/auth/login":
            assert method == "POST" and payload == {"username": "operator", "password": "secret"}
            return {"token": "account-token-after-restart" if self.restarted else "account-token"}
        assert token in {"account-token", "account-token-after-restart"}
        if path == "/v1/cloud/sessions" and method == "POST":
            return {"id": "session-c03"}
        if path.endswith("/commands") and method == "POST":
            with self.lock:
                index = len(self.commands)
                self.commands[payload["request_id"]] = {
                    "id": f"command-{index}",
                    "request_id": payload["request_id"],
                    "status": "running" if index == 0 else "queued",
                    "attempt_count": 1 if index == 0 else 0,
                    "input": payload["input"],
                }
            return {"command_id": f"command-{index}"}
        if "/commands?" in path and method == "GET":
            with self.lock:
                rows = [dict(row) for row in self.commands.values()]
                if self.restarted and len(rows) == 2:
                    rows[0]["status"] = "needs_attention"
                    if self.replay_after_restart and not self.recovered:
                        rows[1]["status"] = "running"
                        rows[1]["attempt_count"] = 1
                    elif self.recovered:
                        rows[0]["status"] = "abandoned"
                        rows[1]["status"] = "completed"
                        rows[1]["attempt_count"] = 1
                return rows
        if path.endswith("/events?after=0") and method == "GET":
            with self.lock:
                rows = list(self.commands.values())
                if len(rows) != 2 or not self.restarted:
                    return []
                events = [{
                    "event_type": "turn.needs_attention",
                    "payload": {
                        "command_id": rows[0]["id"],
                        "error": {"code": "process_restarted"},
                    },
                }]
                if self.recovered:
                    challenge = rows[1]["input"].rsplit(": ", 1)[-1]
                    events.extend([
                        {"event_type": "command.abandoned", "payload": {"command_id": rows[0]["id"]}},
                        {
                            "event_type": "turn.completed",
                            "payload": {
                                "command_id": rows[1]["id"],
                                "model": "provider/model-live",
                                "output": challenge,
                            },
                        },
                    ])
                    if self.duplicate_queued_terminal:
                        events.append({
                            "event_type": "turn.completed",
                            "payload": {
                                "command_id": rows[1]["id"],
                                "model": "provider/model-live",
                                "output": challenge,
                            },
                        })
                return events
        if path.endswith("/recover") and method == "POST":
            assert payload == {"mode": "abandon"}
            with self.lock:
                self.recovered = True
            return {"status": "abandoned"}
        if path.endswith("/archive") and method == "POST":
            self.archived = True
            return {"archived": True}
        raise AssertionError((method, path, payload))


def run(fake: FakeCloud):
    return verifier.run(
        "https://cloud.example.test",
        "operator",
        "secret",
        "provider/model-live",
        ["platformctl", "restart", "notemeld-cloud"],
        1,
        request_fn=fake.request,
        restart_fn=fake.restart,
        sleep_fn=lambda _seconds: time.sleep(0.001),
        challenges=("NM-C03-A", "NM-C03-B"),
    )


def test_c03_verifier_proves_restart_attention_then_explicit_abandon_and_queue_progress():
    fake = FakeCloud()

    result = run(fake)

    assert result["release_checks"] == {"c_03": "PASS"}
    assert result["base_url"] == "https://cloud.example.test"
    assert result["build_commit"] == COMMIT
    assert result["cloud_image_digest"] == DIGEST
    assert result["interrupted_status_after_restart"] == "needs_attention"
    assert result["interrupted_status_after_recovery"] == "abandoned"
    assert result["queued_status_after_restart"] == "queued"
    assert result["queued_status_after_recovery"] == "completed"
    assert result["interrupted_attempt_count"] == result["queued_attempt_count"] == 1
    assert fake.archived is True
    assert "secret" not in str(result)
    assert "account-token" not in str(result)
    assert "NM-C03" not in str(result)


def test_c03_verifier_rejects_queued_replay_before_operator_recovery():
    fake = FakeCloud(replay_after_restart=True)

    with pytest.raises(verifier.VerificationError, match="timed out waiting for interrupted command attention"):
        run(fake)

    assert fake.recovered is False
    assert fake.archived is True


def test_c03_verifier_rejects_duplicate_queued_terminal_event():
    fake = FakeCloud(duplicate_queued_terminal=True)

    with pytest.raises(verifier.VerificationError, match="exactly one successful terminal"):
        run(fake)

    assert fake.archived is True


@pytest.mark.parametrize(
    ("base_url", "model", "restart_command", "message"),
    [
        ("http://cloud.example.test", "provider/model-live", ["restart"], "production HTTPS"),
        ("https://cloud.example.test", "deterministic-test", ["restart"], "real Provider model"),
        ("https://cloud.example.test", "provider/model-live", [], "non-empty JSON argv"),
    ],
)
def test_c03_verifier_rejects_non_release_inputs(base_url, model, restart_command, message):
    with pytest.raises(verifier.VerificationError, match=message):
        verifier.run(
            base_url,
            "operator",
            "secret",
            model,
            restart_command,
            1,
            request_fn=lambda *_args, **_kwargs: {
                "ready": True,
                "environment": "production",
                "agent_backend": "canonical-sdk",
                "build_commit": COMMIT,
                "image_digest": DIGEST,
            },
        )
