from __future__ import annotations

import importlib.util
from pathlib import Path
import hashlib
import json

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "bind_first_batch_evidence.py"
SPEC = importlib.util.spec_from_file_location("bind_first_batch_evidence", SCRIPT)
assert SPEC and SPEC.loader
binding_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(binding_tool)


def test_binding_preserves_result_and_binds_multiple_gates():
    source = {
        "release_checks": {"c_04": "PASS", "c_05_transport_recovery": "PASS"},
        "challenge_sha256": "a" * 64,
    }

    result = binding_tool.bind_evidence(source, "1.2.3-rc.1", "B" * 40, ["C-04", "C-05"])

    assert result["evidence_schema"] == "notemeld.first-batch-live-evidence.v1"
    assert result["rc_version"] == "1.2.3-rc.1"
    assert result["rc_commit"] == "b" * 40
    assert result["bound_gate_ids"] == ["C-04", "C-05"]
    assert result["release_checks"] == source["release_checks"]
    expected_source = json.dumps(source, sort_keys=True, separators=(",", ":")).encode()
    assert result["source_sha256"] == hashlib.sha256(expected_source).hexdigest()


def test_binding_replaces_untrusted_binding_metadata_before_hashing():
    source = {
        "evidence_schema": "forged.v1",
        "rc_version": "9.9.9",
        "rc_commit": "f" * 40,
        "bound_gate_ids": ["E-02"],
        "source_sha256": "0" * 64,
        "release_checks": {"c_03": "PASS"},
        "base_url": "https://cloud.example.test",
    }

    result = binding_tool.bind_evidence(source, "1.2.3-rc.1", "a" * 40, ["C-03"])

    assert result["evidence_schema"] == "notemeld.first-batch-live-evidence.v1"
    assert result["rc_version"] == "1.2.3-rc.1"
    assert result["rc_commit"] == "a" * 40
    assert result["bound_gate_ids"] == ["C-03"]
    canonical = json.dumps(
        {"release_checks": {"c_03": "PASS"}, "base_url": "https://cloud.example.test"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert result["source_sha256"] == hashlib.sha256(canonical).hexdigest()


def test_host_approval_subcheck_cannot_be_promoted_to_complete_e02():
    source = {"release_checks": {"host_approval_deny_ui": "PASS"}}

    with pytest.raises(binding_tool.EvidenceBindingError, match="does not prove E-02"):
        binding_tool.bind_evidence(source, "1.2.3-rc.1", "a" * 40, ["E-02"])


def test_windows_runtime_subcheck_cannot_be_promoted_to_x01_or_x02():
    source = {"release_checks": {"windows_local_agent_runtime": "PASS"}}

    for gate in ("X-01", "X-02"):
        with pytest.raises(binding_tool.EvidenceBindingError, match=f"does not prove {gate}"):
            binding_tool.bind_evidence(source, "1.2.3-rc.1", "a" * 40, [gate])


def test_binding_rejects_weak_or_mismatched_evidence():
    with pytest.raises(binding_tool.EvidenceBindingError, match="does not prove C-05"):
        binding_tool.bind_evidence(
            {"release_checks": {"c_04": "PASS"}},
            "1.2.3",
            "a" * 40,
            ["C-04", "C-05"],
        )
    with pytest.raises(binding_tool.EvidenceBindingError, match="SemVer"):
        binding_tool.bind_evidence({"release_checks": {"c_04": "PASS"}}, "v1.2.3", "a" * 40, ["C-04"])
    with pytest.raises(binding_tool.EvidenceBindingError, match="unique canonical"):
        binding_tool.bind_evidence({"release_checks": {"c_04": "PASS"}}, "1.2.3", "a" * 40, ["C-04", "C-04"])
