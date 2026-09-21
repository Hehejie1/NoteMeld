from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "acceptance" / "verify-release-ledger.py"
SPEC = importlib.util.spec_from_file_location("verify_release_ledger", SCRIPT)
assert SPEC and SPEC.loader
ledger_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger_tool)


def bound_evidence(gate_id: str, version: str = "1.2.3", commit: str = "a" * 40) -> dict:
    evidence = {
        "evidence_schema": "notemeld.release-evidence.v1",
        "gate_id": gate_id,
        "status": "PASS",
        "rc_version": version,
        "rc_commit": commit,
        "result": {"observed": True},
    }
    source = json.dumps({"result": evidence["result"], "status": evidence["status"]}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    evidence["source_sha256"] = hashlib.sha256(source).hexdigest()
    return evidence


def release_ledger(tmp_path: Path, *, status: str = "PASS") -> dict:
    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    gates = {}
    for gate_id in ledger_tool.EXPECTED_GATES:
        path = evidence / f"{gate_id}.json"
        path.write_text(json.dumps(bound_evidence(gate_id)), encoding="utf-8")
        gates[gate_id] = {"status": status, "evidence": f"evidence/{path.name}"}
    return {"ledger_schema": "notemeld.release-ledger.v1", "rc": {"version": "1.2.3", "commit": "a" * 40}, "gates": gates}


def test_new_release_ledger_requires_all_56_gates(tmp_path: Path):
    data = release_ledger(tmp_path)
    assert len(ledger_tool.EXPECTED_GATES) == 56
    result = ledger_tool.verify(data, tmp_path)
    assert result["release_approved"] is True
    assert result["passed"] == 56
    assert len(result["evidence"]) == 56


def test_new_release_ledger_fails_closed_on_incomplete_gate_set(tmp_path: Path):
    data = release_ledger(tmp_path, status="UNVERIFIED")
    report = ledger_tool.summarize(data)
    assert report["release_approved"] is False
    assert report["counts"]["UNVERIFIED"] == 56
    with pytest.raises(ledger_tool.LedgerError, match="incomplete"):
        ledger_tool.verify(data, tmp_path)


def test_new_release_ledger_rejects_cross_rc_and_bound_tampering(tmp_path: Path):
    data = release_ledger(tmp_path)
    path = tmp_path / data["gates"]["BUILD-MAC-01"]["evidence"]
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["rc_commit"] = "b" * 40
    path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ledger_tool.LedgerError, match="different RC"):
        ledger_tool.verify(data, tmp_path)

    data = release_ledger(tmp_path / "second")
    path = tmp_path / "second" / data["gates"]["BUILD-MAC-01"]["evidence"]
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["result"]["observed"] = False
    path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ledger_tool.LedgerError, match="changed after binding"):
        ledger_tool.verify(data, tmp_path / "second")
