from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_first_batch_e02.py"
PS_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_first_batch_windows_host_approval.ps1"
SPEC = importlib.util.spec_from_file_location("verify_first_batch_e02", SCRIPT)
assert SPEC and SPEC.loader
e02 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(e02)
CLOUD_DIGEST = "sha256:" + "7" * 64


def _remote(decision: str, approval_hash: str):
    terminal = "turn.failed" if decision == "expired" else "turn.succeeded"
    return {
        "release_checks": {
            "c_04_real_host": "PASS",
            "x_06_remote_agent": "PASS",
        },
        "evidence_schema": "notemeld.first-batch-live-evidence.v1",
        "rc_version": "1.2.3-rc.1",
        "rc_commit": "a" * 40,
        "base_url": "https://cloud.example.test",
        "host_device_id": "windows-host",
        "build_commit": "a" * 40,
        "cloud_image_digest": CLOUD_DIGEST,
        "approval": {
            "decision": decision,
            "approval_id_sha256": approval_hash,
            "terminal_event": terminal,
            "tool_dispatched": False,
        },
        "revocation": {
            "grant_revoked": True,
            "grant_existing_connection": "rejected",
            "grant_new_connection": "rejected",
            "device_revoked": True,
            "device_existing_connection": "rejected",
            "device_new_connection": "denied",
            "host_delivery": False,
        },
    }


def _host(decision: str, approval_hash: str):
    check = "host_approval_deny_ui" if decision == "deny" else "host_approval_timeout_ui"
    return {
        "release_checks": {check: "PASS"},
        "rc_version": "1.2.3-rc.1",
        "rc_commit": "a" * 40,
        "cloud_base_url": "https://cloud.example.test",
        "host_device_sha256": e02._sha("windows-host"),
        "build_commit": "a" * 40,
        "cloud_image_digest": CLOUD_DIGEST,
        "decision": decision,
        "approval_id_sha256": approval_hash,
    }


def test_e02_requires_and_synthesizes_all_three_fail_closed_paths():
    result = e02.synthesize(
        _remote("deny", "1" * 64),
        _host("deny", "1" * 64),
        _remote("expired", "2" * 64),
        _host("expired", "2" * 64),
    )

    assert result["release_checks"] == {"e_02": "PASS"}
    assert result["build_commit"] == "a" * 40
    assert result["cloud_image_digest"] == CLOUD_DIGEST
    assert result["denial"]["tool_dispatched"] is False
    assert result["expiry"] == {
        "approval_id_sha256": "2" * 64,
        "terminal_event": "turn.failed",
        "tool_dispatched": False,
    }
    assert result["revocation"]["host_delivery"] is False
    assert set(result["component_sha256"]) == {"denial_remote", "denial_host", "expiry_remote", "expiry_host"}


@pytest.mark.parametrize("mutation", ["hash", "dispatch", "revocation", "rc"])
def test_e02_rejects_mismatched_or_incomplete_evidence(mutation):
    denial_remote = _remote("deny", "1" * 64)
    denial_host = _host("deny", "1" * 64)
    expiry_remote = _remote("expired", "2" * 64)
    expiry_host = _host("expired", "2" * 64)
    if mutation == "hash":
        denial_host["approval_id_sha256"] = "3" * 64
    elif mutation == "dispatch":
        expiry_remote["approval"]["tool_dispatched"] = True
    elif mutation == "revocation":
        denial_remote["revocation"]["host_delivery"] = True
    else:
        expiry_host["rc_commit"] = "b" * 40

    with pytest.raises(e02.E02VerificationError):
        e02.synthesize(denial_remote, denial_host, expiry_remote, expiry_host)


def test_windows_host_approval_gate_uses_safe_distinct_subchecks():
    source = PS_SCRIPT.read_text(encoding="utf-8")
    assert 'ValidateSet("deny", "expired")' in source
    assert "Get-AuthenticodeSignature" in source
    assert "0x8664" in source
    assert '"notemeld-host-approval-count:0"' in source
    assert '"notemeld-host-approval-deny:$approvalId"' in source
    assert '"host_approval_deny_ui"' in source
    assert '"host_approval_timeout_ui"' in source
    assert '"notemeld-build-commit:$ExpectedCommit"' in PS_SCRIPT.read_text(encoding="utf-8")
    assert "$host.cloud_image_digest -ne $cloud.cloud_image_digest" in source
    assert "build_commit = $cloud.build_commit" in source
    assert "cloud_image_digest = $cloud.cloud_image_digest" in source
    assert '"e_02_host_' not in source
