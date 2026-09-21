#!/usr/bin/env python3
"""Fail closed unless the first-batch release ledger is 19/19 PASS."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


EXPECTED_IDS = {
    "C-01", "C-02", "C-03", "C-04", "C-05",
    "X-01", "X-02", "X-03", "X-04", "X-05", "X-06",
    "A-01", "A-02", "A-03", "A-04", "A-05", "A-06",
    "E-01", "E-02",
}
BINDING_FIELDS = {"evidence_schema", "rc_version", "rc_commit", "bound_gate_ids", "source_sha256"}
ROW = re.compile(r"^\|\s*([CXAE]-\d{2})\s*\|.*?\|\s*(PASS|PARTIAL|FAIL|UNVERIFIED|BLOCKED)\s*\|\s*(.*?)\s*\|\s*$")


class LedgerError(RuntimeError):
    pass


def parse_ledger(source: str) -> dict[str, tuple[str, str]]:
    rows: dict[str, tuple[str, str]] = {}
    for line in source.splitlines():
        match = ROW.match(line)
        if not match:
            continue
        gate_id, status, evidence = match.groups()
        if gate_id in rows:
            raise LedgerError(f"duplicate gate row: {gate_id}")
        rows[gate_id] = (status, evidence.strip())
    missing = sorted(EXPECTED_IDS.difference(rows))
    unexpected = sorted(set(rows).difference(EXPECTED_IDS))
    if missing or unexpected:
        raise LedgerError(f"ledger gate set mismatch: missing={missing}, unexpected={unexpected}")
    return rows


def summarize_ledger(source: str) -> dict[str, object]:
    rows = parse_ledger(source)
    statuses = ("PASS", "PARTIAL", "FAIL", "UNVERIFIED", "BLOCKED")
    counts = {status: sum(1 for value, _evidence in rows.values() if value == status) for status in statuses}
    remaining = {status: sorted(gate_id for gate_id, (value, _evidence) in rows.items() if value == status) for status in statuses if status != "PASS"}
    return {
        "release_approved": counts["PASS"] == len(EXPECTED_IDS),
        "passed": counts["PASS"],
        "required": len(EXPECTED_IDS),
        "counts": counts,
        "remaining": remaining,
    }


def _normalized_check_id(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")


def _cloud_base_url(evidence: dict[str, Any]) -> str | None:
    value = evidence.get("base_url", evidence.get("cloud_base_url"))
    return value.rstrip("/") if isinstance(value, str) and value else None


def _host_device_sha256(evidence: dict[str, Any]) -> str | None:
    value = evidence.get("host_device_sha256")
    if isinstance(value, str):
        return value
    device_id = evidence.get("host_device_id")
    if isinstance(device_id, str) and device_id:
        return hashlib.sha256(device_id.encode("utf-8")).hexdigest()
    return None


def _validate_evidence(
    rows: dict[str, tuple[str, str]],
    evidence_root: Path,
    *,
    expected_version: str | None,
    expected_commit: str | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    root = evidence_root.resolve()
    validated: dict[str, dict[str, Any]] = {}
    evidence_by_gate: dict[str, dict[str, Any]] = {}
    for gate_id, (_status, reference) in sorted(rows.items()):
        relative = Path(reference)
        if relative.is_absolute() or relative.suffix.lower() != ".json":
            raise LedgerError(f"{gate_id} evidence must be one relative JSON path")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise LedgerError(f"{gate_id} evidence file is missing or escapes the ledger directory")
        try:
            raw = path.read_bytes()
            evidence = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise LedgerError(f"{gate_id} evidence JSON is invalid: {exc}") from exc
        if not isinstance(evidence, dict) or evidence.get("evidence_schema") != "notemeld.first-batch-live-evidence.v1":
            raise LedgerError(f"{gate_id} evidence was not produced by the first-batch evidence binder")
        bound_gate_ids = evidence.get("bound_gate_ids")
        if (
            not isinstance(bound_gate_ids, list)
            or not bound_gate_ids
            or any(not isinstance(value, str) or value not in EXPECTED_IDS for value in bound_gate_ids)
            or bound_gate_ids != sorted(set(bound_gate_ids))
            or gate_id not in bound_gate_ids
        ):
            raise LedgerError(f"{gate_id} evidence is not explicitly bound to that gate")
        source_sha256 = evidence.get("source_sha256")
        if not isinstance(source_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None:
            raise LedgerError(f"{gate_id} evidence is missing its bound source SHA-256")
        source = {key: value for key, value in evidence.items() if key not in BINDING_FIELDS}
        canonical_source = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if hashlib.sha256(canonical_source).hexdigest() != source_sha256:
            raise LedgerError(f"{gate_id} evidence content changed after it was bound")
        checks = evidence.get("release_checks") if isinstance(evidence, dict) else None
        matching = [
            value for key, value in checks.items()
            if _normalized_check_id(str(key)) == gate_id or _normalized_check_id(str(key)).startswith(f"{gate_id}-")
        ] if isinstance(checks, dict) else []
        if "PASS" not in matching:
            raise LedgerError(f"{gate_id} evidence does not contain a matching PASS release check")
        if expected_version is not None and evidence.get("rc_version") != expected_version:
            raise LedgerError(f"{gate_id} evidence is not bound to RC version {expected_version}")
        if expected_commit is not None and evidence.get("rc_commit") != expected_commit:
            raise LedgerError(f"{gate_id} evidence is not bound to RC commit {expected_commit}")
        validated[gate_id] = {
            "path": relative.as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        evidence_by_gate[gate_id] = evidence
    android_artifact = evidence_by_gate["A-01"]
    source_sha256 = android_artifact.get("source_sha256")
    installed_package = android_artifact.get("installed_package")
    apk_sha256 = installed_package.get("apk_sha256") if isinstance(installed_package, dict) else None
    if not isinstance(source_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None:
        raise LedgerError("A-01 evidence is missing its bound source SHA-256")
    if not isinstance(apk_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", apk_sha256) is None:
        raise LedgerError("A-01 evidence is missing its signed APK SHA-256")
    for gate_id in ("A-02", "A-03", "A-04", "A-05", "A-06"):
        evidence = evidence_by_gate[gate_id]
        current_package = evidence.get("installed_package")
        current_apk_sha256 = current_package.get("apk_sha256") if isinstance(current_package, dict) else None
        if evidence.get("a_01_evidence_sha256") != source_sha256:
            raise LedgerError(f"{gate_id} evidence is not linked to the ledger A-01 evidence")
        if current_apk_sha256 != apk_sha256:
            raise LedgerError(f"{gate_id} did not run the APK proven by ledger A-01 evidence")
    recovery = evidence_by_gate["A-06"]
    if recovery.get("transport") != "relay":
        raise LedgerError("A-06 evidence must prove recovery over Relay")
    if recovery.get("offline_read_only") is not True:
        raise LedgerError("A-06 evidence does not prove offline read-only mode")
    if recovery.get("interrupted_command_count") != 1:
        raise LedgerError("A-06 evidence must retain exactly one interrupted command")
    cursor_before = recovery.get("cursor_before")
    cursor_after = recovery.get("cursor_after")
    if (
        not isinstance(cursor_before, int)
        or isinstance(cursor_before, bool)
        or not isinstance(cursor_after, int)
        or isinstance(cursor_after, bool)
        or cursor_after <= cursor_before
    ):
        raise LedgerError("A-06 evidence does not prove a strictly increasing Relay cursor")
    for field in ("interrupted_challenge_sha256", "recovered_answer_sha256", "offline_ui_sha256"):
        value = recovery.get(field)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise LedgerError(f"A-06 evidence is missing its {field} hash")
    if recovery.get("process_recovery") is not True:
        raise LedgerError("A-06 evidence does not prove Android process recovery")
    if recovery.get("process_recovery_user_count") != 1:
        raise LedgerError("A-06 process recovery must retain exactly one user input")
    if recovery.get("process_recovery_terminal") != "turn.interrupted:needs_attention":
        raise LedgerError("A-06 process recovery must end in needs_attention")
    process_ui_hash = recovery.get("process_recovery_ui_sha256")
    if not isinstance(process_ui_hash, str) or re.fullmatch(r"[0-9a-f]{64}", process_ui_hash) is None:
        raise LedgerError("A-06 evidence is missing its process recovery UI hash")
    windows_baseline = evidence_by_gate["X-01"]
    executable_sha256 = windows_baseline.get("executable_sha256")
    signer_thumbprint = windows_baseline.get("signer_thumbprint")
    windows_installer_sha256 = windows_baseline.get("windows_installer_sha256")
    if not isinstance(executable_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", executable_sha256) is None:
        raise LedgerError("X-01 evidence is missing the installed Windows executable SHA-256")
    if not isinstance(signer_thumbprint, str) or re.fullmatch(r"[0-9a-f]{40,64}", signer_thumbprint) is None:
        raise LedgerError("X-01 evidence is missing the Windows signer thumbprint")
    if not isinstance(windows_installer_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", windows_installer_sha256) is None:
        raise LedgerError("X-01 evidence is missing the tested Windows installer SHA-256")
    for gate_id in ("X-02", "X-03", "X-04", "X-05"):
        evidence = evidence_by_gate[gate_id]
        if evidence.get("executable_sha256") != executable_sha256:
            raise LedgerError(f"{gate_id} did not run the Windows executable proven by X-01")
        if evidence.get("signer_thumbprint") != signer_thumbprint:
            raise LedgerError(f"{gate_id} Windows signer does not match X-01")
    cloud_base_url = _cloud_base_url(evidence_by_gate["C-01"])
    if cloud_base_url is None or not cloud_base_url.startswith("https://"):
        raise LedgerError("C-01 evidence is missing the production HTTPS Cloud URL")
    cloud_build_commit = evidence_by_gate["C-01"].get("build_commit")
    cloud_image_digest = evidence_by_gate["C-01"].get("cloud_image_digest")
    if cloud_build_commit != evidence_by_gate["C-01"].get("rc_commit"):
        raise LedgerError("C-01 runtime build commit does not match the bound RC commit")
    if not isinstance(cloud_image_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", cloud_image_digest) is None:
        raise LedgerError("C-01 evidence is missing the deployed immutable Cloud image digest")
    cloud_gates = ("C-02", "C-03", "C-04", "C-05", "X-03", "X-04", "X-05", "X-06", "A-03", "A-04", "A-05", "A-06", "E-01", "E-02")
    for gate_id in cloud_gates:
        if _cloud_base_url(evidence_by_gate[gate_id]) != cloud_base_url:
            raise LedgerError(f"{gate_id} evidence does not target the ledger C-01 Cloud deployment")
        if evidence_by_gate[gate_id].get("build_commit") != cloud_build_commit or evidence_by_gate[gate_id].get("cloud_image_digest") != cloud_image_digest:
            raise LedgerError(f"{gate_id} evidence does not target the ledger C-01 Cloud build identity")
    host_device_sha256 = _host_device_sha256(evidence_by_gate["X-03"])
    if not isinstance(host_device_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", host_device_sha256) is None:
        raise LedgerError("X-03 evidence is missing the remote Host identity hash")
    host_gates = ("C-05", "X-04", "X-05", "X-06", "A-04", "A-05", "A-06", "E-01", "E-02")
    for gate_id in host_gates:
        if _host_device_sha256(evidence_by_gate[gate_id]) != host_device_sha256:
            raise LedgerError(f"{gate_id} evidence does not target the ledger X-03 Host")
    return validated, {
        "android_apk_sha256": apk_sha256,
        "windows_installer_sha256": windows_installer_sha256,
        "cloud_image_digest": cloud_image_digest,
    }


def verify_ledger(
    source: str,
    *,
    evidence_root: Path | None = None,
    expected_version: str | None = None,
    expected_commit: str | None = None,
) -> dict[str, object]:
    rows = parse_ledger(source)
    incomplete = {gate_id: status for gate_id, (status, _evidence) in sorted(rows.items()) if status != "PASS"}
    if incomplete:
        raise LedgerError(f"first-batch live gates are not complete: {json.dumps(incomplete, sort_keys=True)}")
    empty_evidence = sorted(gate_id for gate_id, (_status, evidence) in rows.items() if not evidence or evidence in {"-", "—"})
    if empty_evidence:
        raise LedgerError(f"PASS rows require evidence: {empty_evidence}")
    if evidence_root is None:
        raise LedgerError("release approval requires an evidence root and all 19 JSON files")
    validated_evidence, artifact_claims = _validate_evidence(
        rows,
        evidence_root,
        expected_version=expected_version,
        expected_commit=expected_commit,
    )
    result: dict[str, object] = {
        "verification_schema": "notemeld.first-batch-ledger-verification.v1",
        "release_approved": True,
        "passed": len(rows),
        "required": len(EXPECTED_IDS),
        "gate_ids": sorted(rows),
        "evidence": validated_evidence,
        "artifact_claims": artifact_claims,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--report", action="store_true", help="Report validated progress without requiring 19/19 PASS")
    parser.add_argument("--expected-version")
    parser.add_argument("--expected-commit")
    args = parser.parse_args()
    try:
        source = args.ledger.read_text(encoding="utf-8")
        result = summarize_ledger(source) if args.report else verify_ledger(
            source,
            evidence_root=args.ledger.parent,
            expected_version=args.expected_version,
            expected_commit=args.expected_commit,
        )
    except (OSError, LedgerError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
