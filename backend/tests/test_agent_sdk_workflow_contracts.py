from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "agent-sdk.yml"
SCRIPTS = ROOT / "agent-sdk" / "scripts"
VALIDATOR = SCRIPTS / "verify-artifact-manifest.py"

EXPECTED_TARGETS = {
    "x86_64-apple-darwin",
    "aarch64-apple-darwin",
    "x86_64-pc-windows-msvc",
    "x86_64-unknown-linux-gnu",
    "aarch64-unknown-linux-gnu",
    "aarch64-apple-ios",
    "aarch64-apple-ios-sim",
    "aarch64-linux-android",
    "armv7-linux-androideabi",
    "i686-linux-android",
    "x86_64-linux-android",
    "aarch64-unknown-linux-ohos",
}


def _workflow() -> tuple[dict, str]:
    source = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.load(source, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    return parsed, source


def _run_validator(root: Path, *expected_targets: str) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(VALIDATOR),
        "verify",
        "--artifact-root",
        str(root),
        "--sdk-version",
        "0.1.0",
        "--schema-version",
        "1",
        "--binding-version",
        "0.1.0",
    ]
    for target in expected_targets:
        command.extend(("--expected-target", target))
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _entry(path: str, payload: bytes, target: str) -> dict[str, object]:
    return {
        "path": path,
        "kind": "native-library",
        "sdk_version": "0.1.0",
        "schema_version": "1",
        "target_triple": target,
        "binding_version": "0.1.0",
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _write_manifest(root: Path, entries: list[dict[str, object]]) -> Path:
    manifest = root / "artifact-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "license_inventory": [
                    {"component": "notemeld-agent-sdk", "license": "MIT"}
                ],
                "artifacts": entries,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_workflow_has_contract_first_platform_matrix_and_final_verification() -> None:
    parsed, source = _workflow()
    jobs = parsed["jobs"]

    assert "contracts" in jobs
    build_jobs = {
        "build-native",
        "build-swift",
        "build-android",
        "build-harmony",
    }
    assert build_jobs <= jobs.keys()
    assert all(jobs[name].get("needs") == "contracts" for name in build_jobs)

    final = jobs["verify-manifests"]
    assert set(final["needs"]) == build_jobs
    assert "verify-artifact-manifest.py verify" in source
    assert "actions/download-artifact@v4" in source


def test_workflow_requires_every_platform_target_and_real_target_tooling() -> None:
    _, source = _workflow()

    assert EXPECTED_TARGETS <= {target for target in EXPECTED_TARGETS if target in source}
    for evidence in (
        "cargo build",
        "xcodebuild",
        "connectedAndroidTest",
        "assembleHar",
        "ohpm",
        "hvigor",
    ):
        assert evidence in source
    assert "chmod +x" in source
    assert "continue-on-error: true" not in source


@pytest.mark.parametrize(
    ("script_name", "tool_markers"),
    [
        ("build-python.sh", ("cargo build", "verify-artifact-manifest.py create")),
        ("build-swift.sh", ("cargo rustc", "xcodebuild", "swift build")),
        ("build-kotlin.sh", ("cargo ndk", "assembleRelease")),
        ("build-harmony.sh", ("cargo build", "ohpm", "assembleHar")),
    ],
)
def test_build_scripts_are_fail_closed_and_create_real_artifacts(
    script_name: str, tool_markers: tuple[str, ...]
) -> None:
    script = SCRIPTS / script_name
    source = script.read_text(encoding="utf-8")

    assert os.access(script, os.X_OK)
    assert "set -euo pipefail" in source
    assert "git rev-parse --show-toplevel" in source
    assert "touch " not in source
    assert "|| true" not in source
    assert "cargo metadata" in source
    assert "license-inventory.json" in source
    assert "SOURCE_DATE_EPOCH" in source
    for marker in tool_markers:
        assert marker in source


@pytest.mark.parametrize(
    "script_name",
    ["build-swift.sh", "build-kotlin.sh", "build-harmony.sh"],
)
def test_platform_archives_are_repacked_deterministically(script_name: str) -> None:
    source = (SCRIPTS / script_name).read_text(encoding="utf-8")

    assert "ZipInfo" in source
    assert "SOURCE_DATE_EPOCH" in source


def test_swift_packager_reads_cargo_rustc_staticlib_from_deps_directory() -> None:
    source = (SCRIPTS / "build-swift.sh").read_text(encoding="utf-8")

    assert "release/deps/libnotemeld_agent.a" in source


def test_manifest_validator_accepts_complete_matching_artifact(tmp_path: Path) -> None:
    payload = b"real native payload"
    (tmp_path / "libnotemeld_agent.so").write_bytes(payload)
    _write_manifest(
        tmp_path,
        [_entry("libnotemeld_agent.so", payload, "x86_64-unknown-linux-gnu")],
    )

    result = _run_validator(tmp_path, "x86_64-unknown-linux-gnu")

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["targets"] == ["x86_64-unknown-linux-gnu"]
    assert summary["artifact_count"] == 1


def test_license_inventory_is_derived_from_cargo_metadata(tmp_path: Path) -> None:
    metadata = tmp_path / "cargo-metadata.json"
    output = tmp_path / "license-inventory.json"
    metadata.write_text(
        json.dumps(
            {
                "packages": [
                    {"name": "serde", "version": "1.0.229", "license": "MIT OR Apache-2.0"},
                    {"name": "agent-ffi", "version": "0.1.0", "license": "MIT"},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "licenses",
            "--cargo-metadata",
            str(metadata),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8")) == [
        {"component": "agent-ffi@0.1.0", "license": "MIT"},
        {"component": "serde@1.0.229", "license": "MIT OR Apache-2.0"},
    ]


def test_manifest_validator_rejects_duplicate_target_manifests(tmp_path: Path) -> None:
    for directory_name in ("first", "second"):
        directory = tmp_path / directory_name
        directory.mkdir()
        payload = directory_name.encode()
        (directory / "agent.bin").write_bytes(payload)
        _write_manifest(
            directory,
            [_entry("agent.bin", payload, "x86_64-unknown-linux-gnu")],
        )

    result = _run_validator(tmp_path, "x86_64-unknown-linux-gnu")

    assert result.returncode != 0
    assert "duplicate target manifest" in result.stderr.lower()


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("missing_field", "missing field"),
        ("duplicate", "duplicate artifact path"),
        ("escape", "escapes artifact root"),
        ("checksum", "checksum mismatch"),
        ("target", "unexpected target"),
        ("version", "sdk_version mismatch"),
        ("missing_target", "missing expected target"),
    ],
)
def test_manifest_validator_rejects_invalid_or_incomplete_manifests(
    tmp_path: Path, mutation: str, expected_error: str
) -> None:
    payload = b"payload"
    (tmp_path / "agent.bin").write_bytes(payload)
    entry = _entry("agent.bin", payload, "x86_64-unknown-linux-gnu")
    entries = [entry]
    expected_targets = ["x86_64-unknown-linux-gnu"]

    if mutation == "missing_field":
        del entry["binding_version"]
    elif mutation == "duplicate":
        entries.append(dict(entry))
    elif mutation == "escape":
        outside = tmp_path.parent / "outside.bin"
        outside.write_bytes(payload)
        entry["path"] = "../outside.bin"
    elif mutation == "checksum":
        entry["sha256"] = "0" * 64
    elif mutation == "target":
        entry["target_triple"] = "unknown-target"
    elif mutation == "version":
        entry["sdk_version"] = "9.9.9"
    elif mutation == "missing_target":
        expected_targets.append("aarch64-unknown-linux-gnu")

    _write_manifest(tmp_path, entries)
    result = _run_validator(tmp_path, *expected_targets)

    assert result.returncode != 0
    assert expected_error in result.stderr.lower()
