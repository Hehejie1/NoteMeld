from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[3]
LEDGER_SPEC = importlib.util.spec_from_file_location(
    "ledger_fixture_helpers",
    ROOT / "desktop" / "backend" / "tests" / "test_first_batch_ledger.py",
)
assert LEDGER_SPEC and LEDGER_SPEC.loader
ledger_fixture = importlib.util.module_from_spec(LEDGER_SPEC)
LEDGER_SPEC.loader.exec_module(ledger_fixture)

SCRIPT = ROOT / "scripts" / "release" / "package_first_batch_live_evidence.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("package_first_batch_live_evidence", SCRIPT)
assert SPEC and SPEC.loader
packager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packager)


def complete_tree(tmp_path: Path) -> Path:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for gate_id in ledger_fixture.ledger_tool.EXPECTED_IDS:
        (evidence_dir / f"{gate_id}.json").write_text(
            json.dumps(ledger_fixture.complete_evidence(gate_id)),
            encoding="utf-8",
        )
    ledger = tmp_path / "field-ledger.md"
    ledger.write_text(ledger_fixture.ledger(), encoding="utf-8")
    return ledger


def test_packager_validates_and_writes_only_the_ledger_and_19_referenced_files(tmp_path: Path):
    ledger = complete_tree(tmp_path)
    output = tmp_path / "first-batch-live-evidence.zip"

    result = packager.package_evidence(ledger, output, "1.2.3", "a" * 40)

    assert result["gate_count"] == 19 and result["file_count"] == 20
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ["ledger.md"] + [
            f"evidence/{gate_id}.json" for gate_id in sorted(ledger_fixture.ledger_tool.EXPECTED_IDS)
        ]
        assert all((item.external_attr >> 16) & 0o777 == 0o600 for item in archive.infolist())


def test_packager_refuses_incomplete_or_existing_output(tmp_path: Path):
    ledger = complete_tree(tmp_path)
    output = tmp_path / "first-batch-live-evidence.zip"
    output.write_bytes(b"keep")
    with pytest.raises(packager.PackageError, match="already exists"):
        packager.package_evidence(ledger, output, "1.2.3", "a" * 40)
    output.unlink()
    ledger.write_text(ledger_fixture.ledger({"C-02": "UNVERIFIED"}), encoding="utf-8")
    with pytest.raises(packager.LedgerError, match="not complete"):
        packager.package_evidence(ledger, output, "1.2.3", "a" * 40)
