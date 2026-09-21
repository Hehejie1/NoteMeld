#!/usr/bin/env python3
"""Synthesize E-02 only from matching revocation, Host denial, and expiry evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


class E02VerificationError(RuntimeError):
    pass


def _check_pass(data: dict[str, Any], check: str) -> None:
    checks = data.get("release_checks")
    if not isinstance(checks, dict) or checks.get(check) != "PASS":
        raise E02VerificationError(f"evidence does not prove {check}")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def synthesize(
    denial_remote: dict[str, Any],
    denial_host: dict[str, Any],
    expiry_remote: dict[str, Any],
    expiry_host: dict[str, Any],
) -> dict[str, Any]:
    for remote in (denial_remote, expiry_remote):
        _check_pass(remote, "c_04_real_host")
        _check_pass(remote, "x_06_remote_agent")
        if remote.get("evidence_schema") != "notemeld.first-batch-live-evidence.v1":
            raise E02VerificationError("remote approval evidence is not bound to an immutable RC")
    _check_pass(denial_host, "host_approval_deny_ui")
    _check_pass(expiry_host, "host_approval_timeout_ui")

    version = denial_remote.get("rc_version")
    commit = denial_remote.get("rc_commit")
    base_url = denial_remote.get("base_url")
    host_device_id = denial_remote.get("host_device_id")
    if not all(isinstance(value, str) and value for value in (version, commit, base_url, host_device_id)):
        raise E02VerificationError("denial evidence omitted RC or Host identity")
    for item in (expiry_remote, denial_host, expiry_host):
        item_base_url = item.get("base_url", item.get("cloud_base_url"))
        if item.get("rc_version") != version or item.get("rc_commit") != commit or item_base_url != base_url:
            raise E02VerificationError("E-02 evidence is not bound to one RC and Cloud deployment")
    cloud_identities = {(item.get("build_commit"), item.get("cloud_image_digest")) for item in (denial_remote, expiry_remote, denial_host, expiry_host)}
    if len(cloud_identities) != 1:
        raise E02VerificationError("E-02 evidence targets different Cloud build identities")
    build_commit, cloud_image_digest = cloud_identities.pop()
    if build_commit != commit or not isinstance(cloud_image_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", cloud_image_digest) is None:
        raise E02VerificationError("E-02 evidence has no valid candidate Cloud build identity")

    host_hash = _sha(host_device_id)
    if denial_host.get("host_device_sha256") != host_hash or expiry_host.get("host_device_sha256") != host_hash:
        raise E02VerificationError("Host UI evidence targets a different device")
    if expiry_remote.get("host_device_id") != host_device_id:
        raise E02VerificationError("remote approval evidence targets different Hosts")

    denial = denial_remote.get("approval")
    expiry = expiry_remote.get("approval")
    if not isinstance(denial, dict) or denial.get("decision") != "deny" or denial.get("tool_dispatched") is not False:
        raise E02VerificationError("remote denial evidence is incomplete")
    if not isinstance(expiry, dict) or expiry.get("decision") != "expired" or expiry.get("terminal_event") != "turn.failed" or expiry.get("tool_dispatched") is not False:
        raise E02VerificationError("remote expiry evidence is incomplete")
    if denial_host.get("decision") != "deny" or expiry_host.get("decision") != "expired":
        raise E02VerificationError("Host UI decision evidence is inconsistent")
    if denial_host.get("approval_id_sha256") != denial.get("approval_id_sha256"):
        raise E02VerificationError("Host denial UI did not resolve the remote approval")
    if expiry_host.get("approval_id_sha256") != expiry.get("approval_id_sha256"):
        raise E02VerificationError("Host timeout UI did not observe the remote approval")
    if denial.get("approval_id_sha256") == expiry.get("approval_id_sha256"):
        raise E02VerificationError("denial and expiry must be independent approval runs")

    revocation = denial_remote.get("revocation")
    expected_revocation = {
        "grant_revoked": True,
        "grant_existing_connection": "rejected",
        "grant_new_connection": "rejected",
        "device_revoked": True,
        "device_existing_connection": "rejected",
        "device_new_connection": "denied",
        "host_delivery": False,
    }
    if revocation != expected_revocation:
        raise E02VerificationError("denial run does not prove fail-closed Grant/device revocation")

    source_hashes = {}
    for name, value in {
        "denial_remote": denial_remote,
        "denial_host": denial_host,
        "expiry_remote": expiry_remote,
        "expiry_host": expiry_host,
    }.items():
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        source_hashes[name] = hashlib.sha256(canonical).hexdigest()
    return {
        "release_checks": {"e_02": "PASS"},
        "rc_version": version,
        "rc_commit": commit,
        "base_url": base_url,
        "build_commit": build_commit,
        "cloud_image_digest": cloud_image_digest,
        "host_device_sha256": host_hash,
        "denial": {
            "approval_id_sha256": denial["approval_id_sha256"],
            "tool_dispatched": False,
        },
        "expiry": {
            "approval_id_sha256": expiry["approval_id_sha256"],
            "terminal_event": "turn.failed",
            "tool_dispatched": False,
        },
        "revocation": expected_revocation,
        "component_sha256": source_hashes,
    }


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise E02VerificationError(f"evidence is not an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--denial-remote", type=Path, required=True)
    parser.add_argument("--denial-host", type=Path, required=True)
    parser.add_argument("--expiry-remote", type=Path, required=True)
    parser.add_argument("--expiry-host", type=Path, required=True)
    args = parser.parse_args()
    paths = [args.denial_remote, args.denial_host, args.expiry_remote, args.expiry_host]
    if len({path.resolve() for path in paths}) != 4:
        parser.error("E-02 requires four distinct evidence files")
    try:
        result = synthesize(*(_read(path) for path in paths))
    except (OSError, json.JSONDecodeError, E02VerificationError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
