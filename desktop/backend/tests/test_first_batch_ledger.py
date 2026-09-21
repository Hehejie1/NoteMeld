from __future__ import annotations

import importlib.util
from pathlib import Path
import hashlib
import json

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_first_batch_ledger.py"
SPEC = importlib.util.spec_from_file_location("verify_first_batch_ledger", SCRIPT)
assert SPEC and SPEC.loader
ledger_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger_tool)


def ledger(statuses: dict[str, str] | None = None) -> str:
    statuses = statuses or {}
    return "\n".join(
        f"| {gate_id} | acceptance | {statuses.get(gate_id, 'PASS')} | evidence/{gate_id}.json |"
        for gate_id in sorted(ledger_tool.EXPECTED_IDS)
    )


def refresh_source_sha256(evidence: dict) -> dict:
    source = {
        key: value
        for key, value in evidence.items()
        if key not in ledger_tool.BINDING_FIELDS
    }
    canonical = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    evidence["source_sha256"] = hashlib.sha256(canonical).hexdigest()
    return evidence


def complete_evidence(gate_id: str) -> dict:
    evidence = {
        "evidence_schema": "notemeld.first-batch-live-evidence.v1",
        "bound_gate_ids": [gate_id],
        "rc_version": "1.2.3",
        "rc_commit": "a" * 40,
        "release_checks": {gate_id.lower().replace("-", "_") + "_live": "PASS"},
    }
    if gate_id == "A-01":
        evidence.update({
            "installed_package": {"apk_sha256": "d" * 64, "signer_sha256": "e" * 64},
        })
    elif gate_id in {"A-02", "A-03", "A-04", "A-05", "A-06"}:
        evidence.update({
            "a_01_evidence_sha256": complete_evidence("A-01")["source_sha256"],
            "installed_package": {"apk_sha256": "d" * 64},
        })
        if gate_id == "A-06":
            evidence.update({
                "transport": "relay",
                "offline_read_only": True,
                "interrupted_command_count": 1,
                "cursor_before": 7,
                "cursor_after": 12,
                "interrupted_challenge_sha256": "a" * 64,
                "recovered_answer_sha256": "b" * 64,
                "offline_ui_sha256": "c" * 64,
                "process_recovery": True,
                "process_recovery_user_count": 1,
                "process_recovery_terminal": "turn.interrupted:needs_attention",
                "process_recovery_ui_sha256": "f" * 64,
            })
    if gate_id in {"X-01", "X-02", "X-03", "X-04", "X-05"}:
        evidence.update({
            "executable_sha256": "1" * 64,
            "signer_thumbprint": "2" * 40,
        })
    if gate_id == "X-01":
        evidence["windows_installer_sha256"] = "3" * 64
    if gate_id in {"C-01", "C-02", "C-03", "C-04", "C-05", "X-03", "X-04", "X-05", "X-06", "A-03", "A-04", "A-05", "A-06", "E-01", "E-02"}:
        evidence["base_url"] = "https://cloud.example.test"
        evidence.update(build_commit="a" * 40, cloud_image_digest="sha256:" + "7" * 64)
    if gate_id in {"X-03", "C-05", "X-04", "X-05", "X-06", "A-04", "A-05", "A-06", "E-01", "E-02"}:
        evidence["host_device_sha256"] = "5" * 64
    return refresh_source_sha256(evidence)


def test_ledger_gate_refuses_approval_without_reading_evidence_files():
    with pytest.raises(ledger_tool.LedgerError, match="requires an evidence root"):
        ledger_tool.verify_ledger(ledger())


def test_ledger_gate_rejects_partial_missing_duplicate_and_empty_evidence():
    with pytest.raises(ledger_tool.LedgerError, match="not complete"):
        ledger_tool.verify_ledger(ledger({"C-02": "UNVERIFIED"}))
    with pytest.raises(ledger_tool.LedgerError, match="gate set mismatch"):
        ledger_tool.verify_ledger("\n".join(ledger().splitlines()[:-1]))
    with pytest.raises(ledger_tool.LedgerError, match="duplicate"):
        ledger_tool.verify_ledger(ledger() + "\n| C-01 | acceptance | PASS | evidence/again.json |")
    with pytest.raises(ledger_tool.LedgerError, match="require evidence"):
        ledger_tool.verify_ledger(ledger().replace("evidence/C-01.json", "—"))


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda evidence: evidence.pop("evidence_schema"), "was not produced by the first-batch evidence binder"),
        (lambda evidence: evidence.update(evidence_schema="invented.v1"), "was not produced by the first-batch evidence binder"),
        (lambda evidence: evidence.update(bound_gate_ids=["C-02"]), "is not explicitly bound to that gate"),
        (lambda evidence: evidence.update(bound_gate_ids=[{}]), "is not explicitly bound to that gate"),
        (lambda evidence: evidence.pop("source_sha256"), "missing its bound source SHA-256"),
    ],
)
def test_ledger_rejects_unbound_or_handwritten_evidence(tmp_path: Path, mutation, message):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for gate_id in ledger_tool.EXPECTED_IDS:
        evidence = complete_evidence(gate_id)
        if gate_id == "C-01":
            mutation(evidence)
        (evidence_dir / f"{gate_id}.json").write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ledger_tool.LedgerError, match=message):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)


def test_ledger_rejects_evidence_content_changed_after_binding(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for gate_id in ledger_tool.EXPECTED_IDS:
        evidence = complete_evidence(gate_id)
        if gate_id == "C-03":
            evidence["base_url"] = "https://edited-after-binding.example.test"
        (evidence_dir / f"{gate_id}.json").write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ledger_tool.LedgerError, match="C-03 evidence content changed after it was bound"):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)


def test_ledger_binds_every_pass_to_matching_versioned_commit_evidence(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for gate_id in ledger_tool.EXPECTED_IDS:
        (evidence_dir / f"{gate_id}.json").write_text(json.dumps(complete_evidence(gate_id)), encoding="utf-8")

    result = ledger_tool.verify_ledger(
        ledger(),
        evidence_root=tmp_path,
        expected_version="1.2.3",
        expected_commit="a" * 40,
    )

    assert result["release_approved"] is True
    assert result["verification_schema"] == "notemeld.first-batch-ledger-verification.v1"
    assert len(result["evidence"]) == 19
    assert all(len(record["sha256"]) == 64 for record in result["evidence"].values())
    assert result["artifact_claims"] == {
        "android_apk_sha256": "d" * 64,
        "windows_installer_sha256": "3" * 64,
        "cloud_image_digest": "sha256:" + "7" * 64,
    }


def test_ledger_rejects_android_gates_from_another_a01_or_replaced_apk(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for gate_id in ledger_tool.EXPECTED_IDS:
        (evidence_dir / f"{gate_id}.json").write_text(json.dumps(complete_evidence(gate_id)), encoding="utf-8")

    a04_path = evidence_dir / "A-04.json"
    a04 = json.loads(a04_path.read_text(encoding="utf-8"))
    a04["a_01_evidence_sha256"] = "f" * 64
    refresh_source_sha256(a04)
    a04_path.write_text(json.dumps(a04), encoding="utf-8")
    with pytest.raises(ledger_tool.LedgerError, match="not linked to the ledger A-01"):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)

    a04["a_01_evidence_sha256"] = complete_evidence("A-01")["source_sha256"]
    a04["installed_package"]["apk_sha256"] = "f" * 64
    refresh_source_sha256(a04)
    a04_path.write_text(json.dumps(a04), encoding="utf-8")
    with pytest.raises(ledger_tool.LedgerError, match="did not run the APK proven by ledger A-01"):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)


def test_ledger_rejects_windows_gates_from_different_executable_or_signer(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for gate_id in ledger_tool.EXPECTED_IDS:
        (evidence_dir / f"{gate_id}.json").write_text(json.dumps(complete_evidence(gate_id)), encoding="utf-8")

    x03_path = evidence_dir / "X-03.json"
    x03 = json.loads(x03_path.read_text(encoding="utf-8"))
    x03["executable_sha256"] = "3" * 64
    refresh_source_sha256(x03)
    x03_path.write_text(json.dumps(x03), encoding="utf-8")
    with pytest.raises(ledger_tool.LedgerError, match="did not run the Windows executable proven by X-01"):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)

    x03["executable_sha256"] = "1" * 64
    x03["signer_thumbprint"] = "4" * 40
    refresh_source_sha256(x03)
    x03_path.write_text(json.dumps(x03), encoding="utf-8")
    with pytest.raises(ledger_tool.LedgerError, match="Windows signer does not match X-01"):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)


def test_ledger_requires_x01_to_identify_the_field_tested_installer(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for gate_id in ledger_tool.EXPECTED_IDS:
        evidence = complete_evidence(gate_id)
        if gate_id == "X-01":
            evidence.pop("windows_installer_sha256")
            refresh_source_sha256(evidence)
        (evidence_dir / f"{gate_id}.json").write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ledger_tool.LedgerError, match="tested Windows installer SHA-256"):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)


def test_ledger_rejects_cross_cloud_or_cross_host_evidence(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for gate_id in ledger_tool.EXPECTED_IDS:
        (evidence_dir / f"{gate_id}.json").write_text(json.dumps(complete_evidence(gate_id)), encoding="utf-8")

    a03_path = evidence_dir / "A-03.json"
    a03 = json.loads(a03_path.read_text(encoding="utf-8"))
    a03["base_url"] = "https://other-cloud.example.test"
    refresh_source_sha256(a03)
    a03_path.write_text(json.dumps(a03), encoding="utf-8")
    with pytest.raises(ledger_tool.LedgerError, match="does not target the ledger C-01 Cloud deployment"):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)

    a03["base_url"] = "https://cloud.example.test"
    refresh_source_sha256(a03)
    a03_path.write_text(json.dumps(a03), encoding="utf-8")
    a04_path = evidence_dir / "A-04.json"
    a04 = json.loads(a04_path.read_text(encoding="utf-8"))
    a04["host_device_sha256"] = "6" * 64
    refresh_source_sha256(a04)
    a04_path.write_text(json.dumps(a04), encoding="utf-8")
    with pytest.raises(ledger_tool.LedgerError, match="does not target the ledger X-03 Host"):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)


def test_ledger_rejects_cross_cloud_image_evidence(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for gate_id in ledger_tool.EXPECTED_IDS:
        (evidence_dir / f"{gate_id}.json").write_text(json.dumps(complete_evidence(gate_id)), encoding="utf-8")
    a03_path = evidence_dir / "A-03.json"
    a03 = json.loads(a03_path.read_text(encoding="utf-8"))
    a03["cloud_image_digest"] = "sha256:" + "8" * 64
    refresh_source_sha256(a03)
    a03_path.write_text(json.dumps(a03), encoding="utf-8")
    with pytest.raises(ledger_tool.LedgerError, match="does not target the ledger C-01 Cloud build identity"):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("offline_read_only", False, "offline read-only"),
        ("interrupted_command_count", 2, "exactly one interrupted command"),
        ("cursor_after", 7, "strictly increasing Relay cursor"),
        ("recovered_answer_sha256", "not-a-hash", "recovered_answer_sha256 hash"),
    ],
)
def test_ledger_rejects_incomplete_android_recovery_evidence(tmp_path: Path, field, value, message):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for gate_id in ledger_tool.EXPECTED_IDS:
        evidence = complete_evidence(gate_id)
        if gate_id == "A-06":
            evidence[field] = value
            refresh_source_sha256(evidence)
        (evidence_dir / f"{gate_id}.json").write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ledger_tool.LedgerError, match=message):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)


def test_ledger_requires_c01_runtime_to_identify_the_bound_cloud_image(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for gate_id in ledger_tool.EXPECTED_IDS:
        (evidence_dir / f"{gate_id}.json").write_text(json.dumps(complete_evidence(gate_id)), encoding="utf-8")

    c01_path = evidence_dir / "C-01.json"
    c01 = json.loads(c01_path.read_text(encoding="utf-8"))
    c01["build_commit"] = "b" * 40
    refresh_source_sha256(c01)
    c01_path.write_text(json.dumps(c01), encoding="utf-8")
    with pytest.raises(ledger_tool.LedgerError, match="runtime build commit"):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)

    c01["build_commit"] = "a" * 40
    c01.pop("cloud_image_digest")
    refresh_source_sha256(c01)
    c01_path.write_text(json.dumps(c01), encoding="utf-8")
    with pytest.raises(ledger_tool.LedgerError, match="immutable Cloud image digest"):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path)

def test_ledger_rejects_wrong_rc_binding_and_path_escape(tmp_path: Path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for gate_id in ledger_tool.EXPECTED_IDS:
        evidence = complete_evidence(gate_id)
        evidence.update(rc_version="other", rc_commit="b" * 40)
        (evidence_dir / f"{gate_id}.json").write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ledger_tool.LedgerError, match="not bound to RC version"):
        ledger_tool.verify_ledger(ledger(), evidence_root=tmp_path, expected_version="1.2.3")
    with pytest.raises(ledger_tool.LedgerError, match="relative JSON path"):
        ledger_tool.verify_ledger(ledger().replace("evidence/C-01.json", "/tmp/C-01.json"), evidence_root=tmp_path)


def test_ledger_report_counts_incomplete_gates_without_approving_release():
    result = ledger_tool.summarize_ledger(ledger({"C-02": "UNVERIFIED", "X-01": "PARTIAL", "E-01": "FAIL"}))
    assert result["release_approved"] is False
    assert result["passed"] == 16
    assert result["required"] == 19
    assert result["counts"] == {"PASS": 16, "PARTIAL": 1, "FAIL": 1, "UNVERIFIED": 1, "BLOCKED": 0}
    assert result["remaining"]["PARTIAL"] == ["X-01"]
    assert result["remaining"]["FAIL"] == ["E-01"]
    assert result["remaining"]["UNVERIFIED"] == ["C-02"]
