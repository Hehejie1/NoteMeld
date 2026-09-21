from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_first_batch_c05.py"
SPEC = importlib.util.spec_from_file_location("verify_first_batch_c05", SCRIPT)
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)

COMMIT = "a" * 40
VERSION = "1.2.3-rc.1"
HOST_ID = "windows-host-stable"
HOST_HASH = hashlib.sha256(HOST_ID.encode()).hexdigest()
POST_HASH = "c" * 64
CLOUD_DIGEST = "sha256:" + "7" * 64


def evidence():
    relay = {
        "release_checks": {"c_05_transport_recovery": "PASS"},
        "rc_version": VERSION,
        "rc_commit": COMMIT,
        "base_url": "https://cloud.example",
        "offline_error": "host_offline",
        "controller_recovery_sequence": 3,
        "host_recovery_sequence": 2,
    }
    restart = {
        "release_checks": {"x_03": "PASS"},
        "rc_version": VERSION,
        "rc_commit": COMMIT,
        "cloud_base_url": "https://cloud.example",
        "platform": "windows-x86_64",
        "identity_stable_after_restart": True,
        "cloud_heartbeat_advanced": True,
        "host_device_sha256": HOST_HASH,
        "last_seen_before": 100,
        "last_seen_after": 110,
        "pre_restart_remote_evidence_sha256": "b" * 64,
    }
    post = {
        "release_checks": {"c_04_real_host": "PASS", "x_06_remote_agent": "PASS"},
        "rc_version": VERSION,
        "rc_commit": COMMIT,
        "base_url": "https://cloud.example",
        "host_device_id": HOST_ID,
        "host_last_seen_at": 111,
        "transport": "relay",
        "cloud_persisted_commands": 0,
        "cloud_persisted_events": 0,
        "challenge_sha256": "d" * 64,
    }
    for item in (relay, restart, post):
        item.update(build_commit=COMMIT, cloud_image_digest=CLOUD_DIGEST)
    return relay, restart, post


def test_c05_composer_requires_restart_and_post_restart_real_host_run():
    relay, restart, post = evidence()
    result = verifier.compose(relay, restart, post, post_restart_sha256=POST_HASH)
    assert result["release_checks"] == {"c_05": "PASS"}
    assert result["host_device_sha256"] == HOST_HASH
    assert result["build_commit"] == COMMIT
    assert result["cloud_image_digest"] == CLOUD_DIGEST
    assert result["component_sha256"] == {"pre_restart_remote": "b" * 64, "post_restart_remote": POST_HASH}


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda relay, restart, post: relay.update(offline_error="other"), "offline"),
        (lambda relay, restart, post: restart.update(host_device_sha256="0" * 64), "different Host"),
        (lambda relay, restart, post: post.update(host_last_seen_at=109), "temporally after"),
        (lambda relay, restart, post: post.update(cloud_persisted_events=1), "opaque Relay"),
    ],
)
def test_c05_composer_rejects_incomplete_bound_chain(mutation, message):
    relay, restart, post = evidence()
    mutation(relay, restart, post)
    with pytest.raises(verifier.VerificationError, match=message):
        verifier.compose(relay, restart, post, post_restart_sha256=POST_HASH)


def test_c05_composer_rejects_reusing_pre_restart_agent_evidence():
    relay, restart, post = evidence()
    with pytest.raises(verifier.VerificationError, match="distinct field run"):
        verifier.compose(relay, restart, post, post_restart_sha256="b" * 64)


def test_c05_composer_rejects_cross_image_evidence():
    relay, restart, post = evidence()
    post["cloud_image_digest"] = "sha256:" + "8" * 64
    with pytest.raises(verifier.VerificationError, match="different Cloud build identities"):
        verifier.compose(relay, restart, post, post_restart_sha256=POST_HASH)
