#!/usr/bin/env python3
"""Compose C-05 evidence from transport recovery and a real Host restart run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


class VerificationError(RuntimeError):
    pass


def _check_id(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")


def _requires_pass(evidence: dict[str, Any], prefix: str) -> None:
    checks = evidence.get("release_checks")
    if not isinstance(checks, dict) or not any(
        value == "PASS" and (_check_id(str(key)) == prefix or _check_id(str(key)).startswith(f"{prefix}-"))
        for key, value in checks.items()
    ):
        raise VerificationError(f"evidence does not prove {prefix}")


def _bound_identity(evidence: dict[str, Any]) -> tuple[str, str]:
    version, commit = evidence.get("rc_version"), evidence.get("rc_commit")
    if not isinstance(version, str) or not version or not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise VerificationError("all evidence must be bound to an immutable RC")
    return version, commit


def _base_url(evidence: dict[str, Any]) -> str:
    value = evidence.get("base_url", evidence.get("cloud_base_url"))
    if not isinstance(value, str) or not value.startswith("https://"):
        raise VerificationError("evidence has no production HTTPS Cloud URL")
    return value.rstrip("/")


def compose(
    relay: dict[str, Any],
    restart: dict[str, Any],
    post_restart: dict[str, Any],
    *,
    post_restart_sha256: str,
) -> dict[str, Any]:
    _requires_pass(relay, "C-05-TRANSPORT-RECOVERY")
    _requires_pass(restart, "X-03")
    _requires_pass(post_restart, "C-04-REAL-HOST")
    _requires_pass(post_restart, "X-06-REMOTE-AGENT")
    identities = {_bound_identity(item) for item in (relay, restart, post_restart)}
    if len(identities) != 1:
        raise VerificationError("C-05 evidence is not bound to the same RC")
    urls = {_base_url(item) for item in (relay, restart, post_restart)}
    if len(urls) != 1:
        raise VerificationError("C-05 evidence targets different Cloud deployments")
    cloud_identities = {(item.get("build_commit"), item.get("cloud_image_digest")) for item in (relay, restart, post_restart)}
    if len(cloud_identities) != 1:
        raise VerificationError("C-05 evidence targets different Cloud build identities")
    build_commit, cloud_image_digest = cloud_identities.pop()
    if build_commit != next(iter(identities))[1] or not isinstance(cloud_image_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", cloud_image_digest) is None:
        raise VerificationError("C-05 evidence has no valid candidate Cloud build identity")
    if relay.get("offline_error") != "host_offline":
        raise VerificationError("transport evidence does not prove fail-closed Host offline behavior")
    if not isinstance(relay.get("controller_recovery_sequence"), int) or not isinstance(relay.get("host_recovery_sequence"), int):
        raise VerificationError("transport evidence has no recovered persistent cursors")
    if restart.get("platform") != "windows-x86_64" or restart.get("identity_stable_after_restart") is not True or restart.get("cloud_heartbeat_advanced") is not True:
        raise VerificationError("restart evidence does not prove the signed Windows x64 Host recovered")
    pre_hash = restart.get("pre_restart_remote_evidence_sha256")
    if not isinstance(pre_hash, str) or re.fullmatch(r"[0-9a-f]{64}", pre_hash) is None or pre_hash == post_restart_sha256:
        raise VerificationError("post-restart Agent evidence must be a distinct field run")
    host_id = post_restart.get("host_device_id")
    if not isinstance(host_id, str) or not host_id:
        raise VerificationError("post-restart evidence has no Host device")
    if hashlib.sha256(host_id.encode()).hexdigest() != restart.get("host_device_sha256"):
        raise VerificationError("post-restart Agent used a different Host identity")
    before, after, observed = restart.get("last_seen_before"), restart.get("last_seen_after"), post_restart.get("host_last_seen_at")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in (before, after, observed)):
        raise VerificationError("Host heartbeat timestamps are invalid")
    if not before < after <= observed:
        raise VerificationError("post-restart Agent run is not temporally after Host recovery")
    if post_restart.get("transport") != "relay" or post_restart.get("cloud_persisted_commands") != 0 or post_restart.get("cloud_persisted_events") != 0:
        raise VerificationError("post-restart Host run is not an opaque Relay execution")
    version, commit = identities.pop()
    return {
        "release_checks": {"c_05": "PASS"},
        "rc_version": version,
        "rc_commit": commit,
        "base_url": urls.pop(),
        "build_commit": build_commit,
        "cloud_image_digest": cloud_image_digest,
        "host_device_sha256": restart["host_device_sha256"],
        "last_seen_before": before,
        "last_seen_after_restart": after,
        "last_seen_at_post_restart_agent": observed,
        "offline_error": "host_offline",
        "controller_recovery_sequence": relay["controller_recovery_sequence"],
        "host_recovery_sequence": relay["host_recovery_sequence"],
        "post_restart_challenge_sha256": post_restart.get("challenge_sha256"),
        "component_sha256": {
            "pre_restart_remote": pre_hash,
            "post_restart_remote": post_restart_sha256,
        },
    }


def _load(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise VerificationError(f"{path} is not a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--relay-evidence", type=Path, required=True)
    parser.add_argument("--restart-evidence", type=Path, required=True)
    parser.add_argument("--post-restart-host-evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        relay, _ = _load(args.relay_evidence)
        restart, _ = _load(args.restart_evidence)
        post_restart, post_hash = _load(args.post_restart_host_evidence)
        result = compose(relay, restart, post_restart, post_restart_sha256=post_hash)
    except (OSError, json.JSONDecodeError, VerificationError) as exc:
        print(f"first-batch C-05 verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
