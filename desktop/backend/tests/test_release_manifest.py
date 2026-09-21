from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("generate_release_manifest", ROOT / "scripts/acceptance/generate-release-manifest.py")
assert SPEC and SPEC.loader
manifest_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest_tool)
LEDGER_SPEC = importlib.util.spec_from_file_location("verify_release_ledger", ROOT / "scripts/acceptance/verify-release-ledger.py")
assert LEDGER_SPEC and LEDGER_SPEC.loader
ledger_tool = importlib.util.module_from_spec(LEDGER_SPEC)
LEDGER_SPEC.loader.exec_module(ledger_tool)


def _approved_ledger(tmp_path: Path) -> Path:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    gates = {}
    for gate_id in ledger_tool.EXPECTED_GATES:
        evidence_data = {
            "evidence_schema": "notemeld.release-evidence.v1",
            "gate_id": gate_id,
            "status": "PASS",
            "rc_version": "1.2.3",
            "rc_commit": "a" * 40,
            "result": {"observed": True},
        }
        import hashlib
        import json
        source = json.dumps({"result": evidence_data["result"], "status": "PASS"}, separators=(",", ":"), sort_keys=True).encode()
        evidence_data["source_sha256"] = hashlib.sha256(source).hexdigest()
        filename = f"{gate_id}.json"
        (evidence / filename).write_text(json.dumps(evidence_data), encoding="utf-8")
        gates[gate_id] = {"status": "PASS", "evidence": f"evidence/{filename}"}
    ledger = tmp_path / "ledger.json"
    import json
    ledger.write_text(json.dumps({"ledger_schema": "notemeld.release-ledger.v1", "rc": {"version": "1.2.3", "commit": "a" * 40}, "gates": gates}), encoding="utf-8")
    return ledger


def _artifacts(tmp_path: Path) -> list[str]:
    values = []
    for name in manifest_tool.REQUIRED_ARTIFACTS:
        path = tmp_path / f"{name}.artifact"
        path.write_bytes(name.encode())
        values.append(f"{name}={path}")
    return values


def test_manifest_binds_all_required_artifacts_to_approved_56_gate_rc(tmp_path: Path):
    ledger = _approved_ledger(tmp_path)
    output = tmp_path / "manifest.json"
    result = manifest_tool.generate_manifest(
        ledger, output, _artifacts(tmp_path),
        sdk_commit="b" * 40, abi_version="2", schema_version="3", protocol_version="4",
        config_sync_version="5", ui_contract_version="6",
    )
    assert result["manifest_schema"] == "notemeld.release-manifest.v1"
    assert result["ledger"]["gate_count"] == 56
    assert set(result["artifacts"]) == manifest_tool.REQUIRED_ARTIFACTS
    assert output.is_file()


def test_manifest_rejects_missing_artifact_or_unapproved_ledger(tmp_path: Path):
    ledger = _approved_ledger(tmp_path)
    values = _artifacts(tmp_path)
    with pytest.raises(manifest_tool.ManifestError, match="required RC artifacts"):
        manifest_tool.generate_manifest(ledger, tmp_path / "out.json", values[:-1], sdk_commit="b" * 40, abi_version="2", schema_version="3", protocol_version="4", config_sync_version="5", ui_contract_version="6")
    data = ledger.read_text(encoding="utf-8").replace('"status": "PASS"', '"status": "UNVERIFIED"', 1)
    ledger.write_text(data, encoding="utf-8")
    with pytest.raises(manifest_tool.ManifestError, match="not approved"):
        manifest_tool.generate_manifest(ledger, tmp_path / "out.json", values, sdk_commit="b" * 40, abi_version="2", schema_version="3", protocol_version="4", config_sync_version="5", ui_contract_version="6")
