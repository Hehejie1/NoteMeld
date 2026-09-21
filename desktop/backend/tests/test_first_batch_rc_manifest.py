from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "generate_first_batch_rc_manifest.py"
SPEC = importlib.util.spec_from_file_location("generate_first_batch_rc_manifest", SCRIPT)
assert SPEC and SPEC.loader
manifest_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest_tool)


COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64


def release_files(tmp_path: Path) -> tuple[Path, Path]:
    artifacts = tmp_path / "release"
    artifacts.mkdir()
    (artifacts / "NoteMeld_1.2.3_x64_en-US.msi").write_bytes(b"windows")
    (artifacts / "NoteMeld_1.2.3_x64_en-US.msi.zip.sig").write_text("signature", encoding="utf-8")
    (artifacts / "NoteMeld_1.2.3_android.apk").write_bytes(b"android")
    cloud = artifacts / "cloud-image.json"
    cloud.write_text(json.dumps({"image": "ghcr.io/example/notemeld/cloud", "digest": DIGEST, "commit": COMMIT}), encoding="utf-8")
    return artifacts, cloud


def test_manifest_locks_all_first_batch_artifacts_to_one_commit(tmp_path):
    artifacts, cloud = release_files(tmp_path)
    windows_sha256 = manifest_tool.artifact_record(artifacts / "NoteMeld_1.2.3_x64_en-US.msi")["sha256"]
    android_sha256 = manifest_tool.artifact_record(artifacts / "NoteMeld_1.2.3_android.apk")["sha256"]
    manifest = manifest_tool.generate_manifest("1.2.3", COMMIT, artifacts, cloud)
    assert manifest["schema_version"] == "notemeld.first-batch-rc.v1"
    assert manifest["commit"] == manifest["artifacts"]["cloud"]["commit"] == COMMIT
    assert manifest["artifacts"]["windows_x86_64"][0]["sha256"] == manifest_tool.artifact_record(artifacts / "NoteMeld_1.2.3_x64_en-US.msi")["sha256"]
    assert manifest["artifacts"]["android"]["sha256"] == manifest_tool.artifact_record(artifacts / "NoteMeld_1.2.3_android.apk")["sha256"]
    assert manifest["required_live_gates"] == 19 and manifest["release_approved"] is False
    approval = {
        "verification_schema": "notemeld.first-batch-ledger-verification.v1",
        "release_approved": True,
        "passed": 19,
        "required": 19,
        "gate_ids": sorted({
            "C-01", "C-02", "C-03", "C-04", "C-05",
            "X-01", "X-02", "X-03", "X-04", "X-05", "X-06",
            "A-01", "A-02", "A-03", "A-04", "A-05", "A-06",
            "E-01", "E-02",
        }),
        "evidence": {f"gate-{index}": {"path": f"evidence/{index}.json", "sha256": "c" * 64} for index in range(19)},
        "artifact_claims": {
            "windows_installer_sha256": windows_sha256,
            "android_apk_sha256": android_sha256,
            "cloud_image_digest": DIGEST,
        },
    }
    approved = manifest_tool.generate_manifest("1.2.3", COMMIT, artifacts, cloud, approval=approval)
    assert approved["release_approved"] is True
    assert approved["live_gate_evidence"] == approval["evidence"]


def test_manifest_rejects_unbound_or_incomplete_approval(tmp_path):
    artifacts, cloud = release_files(tmp_path)
    with pytest.raises(manifest_tool.ManifestError, match="bound 19/19"):
        manifest_tool.generate_manifest(
            "1.2.3", COMMIT, artifacts, cloud,
            approval={"release_approved": True, "passed": 19, "required": 19, "evidence": {}},
        )


def test_manifest_rejects_artifacts_different_from_field_tested_packages(tmp_path):
    artifacts, cloud = release_files(tmp_path)
    approval = {
        "verification_schema": "notemeld.first-batch-ledger-verification.v1",
        "release_approved": True,
        "passed": 19,
        "required": 19,
        "gate_ids": sorted({
            "C-01", "C-02", "C-03", "C-04", "C-05",
            "X-01", "X-02", "X-03", "X-04", "X-05", "X-06",
            "A-01", "A-02", "A-03", "A-04", "A-05", "A-06",
            "E-01", "E-02",
        }),
        "evidence": {f"gate-{index}": {"path": f"evidence/{index}.json", "sha256": "c" * 64} for index in range(19)},
        "artifact_claims": {
            "windows_installer_sha256": "d" * 64,
            "android_apk_sha256": "e" * 64,
            "cloud_image_digest": DIGEST,
        },
    }

    with pytest.raises(manifest_tool.ManifestError, match="Android APK was not the APK proven by A-01"):
        manifest_tool.generate_manifest("1.2.3", COMMIT, artifacts, cloud, approval=approval)

    approval["artifact_claims"]["android_apk_sha256"] = manifest_tool.artifact_record(
        artifacts / "NoteMeld_1.2.3_android.apk"
    )["sha256"]
    with pytest.raises(manifest_tool.ManifestError, match="Windows installer was not the installer proven by X-01"):
        manifest_tool.generate_manifest("1.2.3", COMMIT, artifacts, cloud, approval=approval)

    approval["artifact_claims"]["windows_installer_sha256"] = manifest_tool.artifact_record(
        artifacts / "NoteMeld_1.2.3_x64_en-US.msi"
    )["sha256"]
    approval["artifact_claims"]["cloud_image_digest"] = "sha256:" + "f" * 64
    with pytest.raises(manifest_tool.ManifestError, match="Cloud image was not the deployment proven by C-01"):
        manifest_tool.generate_manifest("1.2.3", COMMIT, artifacts, cloud, approval=approval)


def test_manifest_rejects_cross_commit_cloud_and_missing_signatures(tmp_path):
    artifacts, cloud = release_files(tmp_path)
    cloud.write_text(json.dumps({"image": "ghcr.io/example/notemeld/cloud", "digest": DIGEST, "commit": "c" * 40}), encoding="utf-8")
    with pytest.raises(manifest_tool.ManifestError, match="does not match"):
        manifest_tool.generate_manifest("1.2.3", COMMIT, artifacts, cloud)

    cloud.write_text(json.dumps({"image": "ghcr.io/example/notemeld/cloud", "digest": DIGEST, "commit": COMMIT}), encoding="utf-8")
    (artifacts / "NoteMeld_1.2.3_x64_en-US.msi.zip.sig").unlink()
    with pytest.raises(manifest_tool.ManifestError, match="updater signature"):
        manifest_tool.generate_manifest("1.2.3", COMMIT, artifacts, cloud)
