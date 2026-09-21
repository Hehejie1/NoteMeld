#!/usr/bin/env python3
"""Fail-closed verifier for the Cloud/macOS x64/Android 56-gate release ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


EXPECTED_GATES = (
    "BUILD-CLOUD-01", "BUILD-MAC-01", "BUILD-ANDROID-01", "BUILD-COMPAT-01", "BUILD-EVIDENCE-01",
    "RUNTIME-CLOUD-01", "RUNTIME-CLOUD-02", "RUNTIME-MAC-01", "RUNTIME-MAC-02", "RUNTIME-ANDROID-01",
    "RUNTIME-ANDROID-02", "RUNTIME-PARITY-01", "RUNTIME-ISOLATION-01", "SYNC-BASELINE-01", "SYNC-CHANGE-01",
    "SYNC-CONFLICT-01", "SYNC-DELETE-01", "SYNC-OFFLINE-01", "SYNC-SECRET-01", "SYNC-RECOVERY-01",
    "SYNC-SCOPE-01", "E2E-PAIR-01", "E2E-WEB-MAC-01", "E2E-ANDROID-MAC-01", "E2E-FALLBACK-01",
    "E2E-CLOUD-CLIENT-01", "E2E-OPAQUE-01", "E2E-REPLAY-01", "E2E-OFFLINE-01", "E2E-RECOVERY-01",
    "E2E-REVOKE-01", "E2E-APPROVAL-01", "E2E-LIMIT-01", "UI-DATA-01", "UI-STATE-01", "UI-CLOUD-01",
    "UI-MAC-01", "UI-ANDROID-01", "UI-RESPONSIVE-01", "UI-THEME-01", "UI-A11Y-01", "UI-NAV-01",
    "DS-WEB-PACKAGE-01", "DS-WEB-CONSUME-01", "DS-ANDROID-MODULE-01", "DS-CONTRACT-01", "DS-CATALOG-01",
    "DS-SELECT-01", "DS-ICON-01", "DS-MOTION-01", "DS-VISUAL-01", "SEC-IDENTITY-01", "SEC-AUTH-01",
    "DATA-MIGRATION-01", "OBS-01", "CLEAN-01",
)
EXPECTED_GATE_SET = set(EXPECTED_GATES)
STATUSES = ("PASS", "PARTIAL", "FAIL", "UNVERIFIED", "BLOCKED")
BINDING_FIELDS = {"evidence_schema", "gate_id", "rc_version", "rc_commit", "source_sha256"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class LedgerError(RuntimeError):
    pass


def _canonical_source(evidence: dict[str, Any]) -> bytes:
    source = {key: value for key, value in evidence.items() if key not in BINDING_FIELDS}
    return json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _validate_rc(rc: Any) -> tuple[str, str]:
    if not isinstance(rc, dict):
        raise LedgerError("ledger rc must be an object")
    version = rc.get("version")
    commit = rc.get("commit")
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
        raise LedgerError("ledger rc version must be SemVer")
    if not isinstance(commit, str) or COMMIT.fullmatch(commit) is None:
        raise LedgerError("ledger rc commit must be a full lowercase SHA")
    return version, commit


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("ledger_schema") != "notemeld.release-ledger.v1":
        raise LedgerError("unsupported release ledger schema")
    gates = data.get("gates")
    if not isinstance(gates, dict):
        raise LedgerError("ledger gates must be an object")
    missing = sorted(EXPECTED_GATE_SET - set(gates))
    unexpected = sorted(set(gates) - EXPECTED_GATE_SET)
    if missing or unexpected:
        raise LedgerError(f"gate set mismatch: missing={missing}, unexpected={unexpected}")
    counts = {status: 0 for status in STATUSES}
    for gate_id, row in gates.items():
        if not isinstance(row, dict) or row.get("status") not in STATUSES:
            raise LedgerError(f"{gate_id} has an invalid status")
        counts[row["status"]] += 1
    return {
        "verification_schema": "notemeld.release-ledger-verification.v1",
        "gate_count": len(EXPECTED_GATES),
        "counts": counts,
        "passed": counts["PASS"],
        "required": len(EXPECTED_GATES),
        "release_approved": counts["PASS"] == len(EXPECTED_GATES),
    }


def verify(data: dict[str, Any], evidence_root: Path) -> dict[str, Any]:
    version, commit = _validate_rc(data.get("rc"))
    summary = summarize(data)
    if not summary["release_approved"]:
        raise LedgerError(f"release gates are incomplete: {summary['counts']}")
    records: dict[str, dict[str, str]] = {}
    for gate_id in EXPECTED_GATES:
        row = data["gates"][gate_id]
        reference = row.get("evidence")
        if not isinstance(reference, str) or not reference or Path(reference).is_absolute() or Path(reference).suffix != ".json":
            raise LedgerError(f"{gate_id} evidence must be a relative JSON path")
        path = (evidence_root / reference).resolve()
        if not path.is_relative_to(evidence_root.resolve()) or not path.is_file():
            raise LedgerError(f"{gate_id} evidence file is missing or escapes the evidence root")
        try:
            evidence = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LedgerError(f"{gate_id} evidence is invalid: {exc}") from exc
        if not isinstance(evidence, dict) or evidence.get("evidence_schema") != "notemeld.release-evidence.v1":
            raise LedgerError(f"{gate_id} evidence has the wrong schema")
        if evidence.get("gate_id") != gate_id:
            raise LedgerError(f"{gate_id} evidence is bound to a different gate")
        if evidence.get("status") != "PASS":
            raise LedgerError(f"{gate_id} evidence does not prove PASS")
        if evidence.get("rc_version") != version or evidence.get("rc_commit") != commit:
            raise LedgerError(f"{gate_id} evidence is bound to a different RC")
        source_sha256 = evidence.get("source_sha256")
        if not isinstance(source_sha256, str) or SHA256.fullmatch(source_sha256) is None:
            raise LedgerError(f"{gate_id} evidence is missing source SHA-256")
        if hashlib.sha256(_canonical_source(evidence)).hexdigest() != source_sha256:
            raise LedgerError(f"{gate_id} evidence changed after binding")
        records[gate_id] = {"path": reference, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return {
        **summary,
        "release_approved": True,
        "rc_version": version,
        "rc_commit": commit,
        "evidence": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.ledger.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise LedgerError("ledger root must be an object")
        result = summarize(data) if args.report else verify(data, args.evidence_root or args.ledger.parent)
    except (OSError, json.JSONDecodeError, LedgerError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
