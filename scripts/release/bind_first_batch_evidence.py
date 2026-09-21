#!/usr/bin/env python3
"""Bind redacted live-gate evidence to one immutable first-batch RC."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
GATE = re.compile(r"^[CXAE]-\d{2}$")
BINDING_FIELDS = {"evidence_schema", "rc_version", "rc_commit", "bound_gate_ids", "source_sha256"}


class EvidenceBindingError(RuntimeError):
    pass


def _normalized_check_id(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")


def bind_evidence(data: Any, rc_version: str, rc_commit: str, gate_ids: list[str]) -> dict[str, Any]:
    rc_commit = rc_commit.lower()
    if SEMVER.fullmatch(rc_version) is None:
        raise EvidenceBindingError("RC version must be SemVer without a leading v")
    if COMMIT.fullmatch(rc_commit) is None:
        raise EvidenceBindingError("RC commit must be a full 40-character SHA")
    gates = sorted(set(gate_ids))
    if not gates or len(gates) != len(gate_ids) or any(GATE.fullmatch(gate) is None for gate in gates):
        raise EvidenceBindingError("gate ids must be unique canonical first-batch IDs")
    if not isinstance(data, dict) or not isinstance(data.get("release_checks"), dict):
        raise EvidenceBindingError("evidence must contain release_checks")
    checks = data["release_checks"]
    for gate in gates:
        values = [
            value for key, value in checks.items()
            if _normalized_check_id(str(key)) == gate or _normalized_check_id(str(key)).startswith(f"{gate}-")
        ]
        if "PASS" not in values:
            raise EvidenceBindingError(f"evidence does not prove {gate}")
    source = {key: value for key, value in data.items() if key not in BINDING_FIELDS}
    canonical_source = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        **source,
        "evidence_schema": "notemeld.first-batch-live-evidence.v1",
        "rc_version": rc_version,
        "rc_commit": rc_commit,
        "bound_gate_ids": gates,
        "source_sha256": hashlib.sha256(canonical_source).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rc-version", required=True)
    parser.add_argument("--rc-commit", required=True)
    parser.add_argument("--gate", action="append", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and not args.force:
        parser.error("output already exists; use --force to replace it intentionally")
    try:
        source = json.loads(args.input.read_text(encoding="utf-8"))
        evidence = bind_evidence(source, args.rc_version, args.rc_commit, args.gate)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, EvidenceBindingError) as exc:
        parser.error(str(exc))
    print(f"bound first-batch evidence: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
