from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_first_batch_cloud.py"
SPEC = importlib.util.spec_from_file_location("verify_first_batch_cloud", SCRIPT)
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)

COMMIT = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64


def production_ready():
    return {
        "ready": True,
        "environment": "production",
        "agent_backend": "canonical-sdk",
        "build_commit": COMMIT,
        "image_digest": IMAGE_DIGEST,
        "checks": {key: "ok" for key in verifier.REQUIRED_READY_CHECKS},
    }


def release_capabilities():
    return {
        "protocol_version": "notemeld.sync.v1",
        "device_proof_required": True,
        "e2ee_relay_envelope": True,
        "relay_persists_payload": False,
        "relay_backend": "redis",
        "relay_multi_worker": True,
    }


def test_release_verifier_rejects_development_and_memory_relay():
    ready = production_ready()
    ready["environment"] = "development"
    with pytest.raises(verifier.VerificationError, match="environment=production"):
        verifier.validate_ready("https://cloud.example.com", ready, COMMIT, IMAGE_DIGEST)

    capabilities = release_capabilities()
    capabilities["relay_backend"] = "memory"
    with pytest.raises(verifier.VerificationError, match="not release-safe"):
        verifier.validate_capabilities(capabilities)


def test_release_verifier_rejects_http_deterministic_and_duplicate_terminal():
    with pytest.raises(verifier.VerificationError, match="HTTPS"):
        verifier.validate_ready("http://cloud.example.com", production_ready(), COMMIT, IMAGE_DIGEST)

    wrong_image = production_ready()
    wrong_image["image_digest"] = "sha256:" + "c" * 64
    with pytest.raises(verifier.VerificationError, match="runtime identity"):
        verifier.validate_ready("https://cloud.example.com", wrong_image, COMMIT, IMAGE_DIGEST)

    events = [{"sequence": 1, "event_type": "turn.completed", "payload": {"output": "NM-RC-test", "model": "deterministic-cloud-agent"}}]
    with pytest.raises(verifier.VerificationError, match="real Provider"):
        verifier.validate_terminal_events(events, "NM-RC-test", "provider-model")

    events.append({"sequence": 2, "event_type": "turn.failed", "payload": {}})
    with pytest.raises(verifier.VerificationError, match="exactly one terminal"):
        verifier.validate_terminal_events(events, "NM-RC-test", "provider-model")


def test_release_verifier_accepts_unique_real_provider_terminal():
    assert verifier.validate_ready("https://cloud.example.com", production_ready(), COMMIT, IMAGE_DIGEST)["relay"] == "ok"
    assert verifier.validate_capabilities(release_capabilities())["relay_backend"] == "redis"
    result = verifier.validate_terminal_events(
        [
            {"sequence": 1, "event_type": "command.queued", "payload": {}},
            {"sequence": 2, "event_type": "turn.completed", "payload": {"output": "answer NM-RC-test", "model": "provider-model"}},
        ],
        "NM-RC-test",
        "provider-model",
    )
    assert result == {"event_count": 2, "terminal_event": "turn.completed", "model": "provider-model"}


def test_release_verifier_runs_the_complete_cloud_evidence_sequence():
    calls = []
    events = [
        {"sequence": 1, "event_type": "command.queued", "payload": {}},
        {"sequence": 2, "event_type": "turn.completed", "payload": {"output": "NM-RC-live", "model": "provider-model"}},
    ]

    def fake_request(base_url, method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/ready":
            return production_ready()
        if path == "/v1/auth/login":
            return {"token": "secret-token"}
        if path == "/v1/capabilities":
            return release_capabilities()
        if path == "/v1/cloud/sessions":
            return {"id": "session-1"}
        if path == "/v1/cloud/sessions/session-1/commands":
            return {"command_id": "command-1", "status": "completed"}
        if path.endswith("/events?after=0"):
            return events
        if path.endswith("/snapshot"):
            return {"snapshot_seq": 2}
        if path.endswith("/archive"):
            return {"archived": True}
        raise AssertionError(path)

    result = verifier.run(
        "https://cloud.example.com",
        "rc-user",
        "rc-password",
        1,
        "provider-model",
        COMMIT,
        IMAGE_DIGEST,
        request_fn=fake_request,
        challenge="NM-RC-live",
    )
    assert result["release_checks"] == {"c_01": "PASS", "c_02": "PASS"}
    assert result["build_commit"] == COMMIT
    assert result["cloud_image_digest"] == IMAGE_DIGEST
    assert result["snapshot_seq"] == 2
    command_call = next(call for call in calls if call[1] == "/v1/cloud/sessions/session-1/commands")
    assert command_call[2]["timeout_seconds"] == 15.0
    assert calls[-1][0:2] == ("POST", "/v1/cloud/sessions/session-1/archive")
    assert "token" not in result and "password" not in result
    assert "NM-RC-live" not in str(result)
    assert len(result["challenge_sha256"]) == 64


def test_release_verifier_rejects_non_positive_agent_timeout():
    with pytest.raises(verifier.VerificationError, match="timeout must be positive"):
        verifier.run(
            "https://cloud.example.com",
            "rc-user",
            "rc-password",
            0,
            "provider-model",
            COMMIT,
            IMAGE_DIGEST,
            request_fn=lambda *_args, **_kwargs: None,
        )
