#!/usr/bin/env python3
"""Generate the immutable Cloud/Windows/Android first-batch RC manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ManifestError(RuntimeError):
    pass


def artifact_record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return {"name": path.name, "bytes": size, "sha256": digest.hexdigest()}


def generate_manifest(
    version: str,
    commit: str,
    artifact_dir: Path,
    cloud_metadata_path: Path,
    *,
    approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if SEMVER.fullmatch(version) is None:
        raise ManifestError("version must be SemVer without a leading v")
    commit = commit.lower()
    if COMMIT.fullmatch(commit) is None:
        raise ManifestError("commit must be a full 40-character lowercase SHA")
    if not artifact_dir.is_dir():
        raise ManifestError(f"artifact directory does not exist: {artifact_dir}")

    files = sorted(path for path in artifact_dir.iterdir() if path.is_file())
    windows_installers = [path for path in files if path.suffix.lower() in {".msi", ".exe"}]
    windows_updater_signatures = [path for path in files if path.name.lower().endswith((".msi.zip.sig", ".exe.sig"))]
    android_apks = [path for path in files if path.name.endswith("_android.apk")]
    if not windows_installers:
        raise ManifestError("Windows x86_64 installer is missing")
    if not windows_updater_signatures:
        raise ManifestError("Windows updater signature is missing")
    if len(android_apks) != 1:
        raise ManifestError(f"exactly one signed Android APK is required, got {len(android_apks)}")
    versioned = windows_installers + android_apks
    if any(version not in path.name for path in versioned):
        raise ManifestError("Windows and Android artifact names must contain the RC version")

    try:
        cloud = json.loads(cloud_metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Cloud image metadata is invalid: {exc}") from exc
    if not isinstance(cloud, dict) or not isinstance(cloud.get("image"), str) or not cloud["image"].startswith("ghcr.io/"):
        raise ManifestError("Cloud image must be an explicit ghcr.io reference")
    if cloud.get("commit") != commit:
        raise ManifestError("Cloud image commit does not match the RC commit")
    if not isinstance(cloud.get("digest"), str) or DIGEST.fullmatch(cloud["digest"]) is None:
        raise ManifestError("Cloud image digest must be a full sha256 digest")

    if approval is not None and not (
        approval.get("verification_schema") == "notemeld.first-batch-ledger-verification.v1"
        and approval.get("gate_ids") == sorted({
            "C-01", "C-02", "C-03", "C-04", "C-05",
            "X-01", "X-02", "X-03", "X-04", "X-05", "X-06",
            "A-01", "A-02", "A-03", "A-04", "A-05", "A-06",
            "E-01", "E-02",
        })
        and approval.get("release_approved") is True
        and approval.get("passed") == 19
        and approval.get("required") == 19
        and isinstance(approval.get("evidence"), dict)
        and len(approval["evidence"]) == 19
        and isinstance(approval.get("artifact_claims"), dict)
    ):
        raise ManifestError("release approval must come from a bound 19/19 evidence ledger")

    windows_records = [artifact_record(path) for path in windows_installers]
    android_record = artifact_record(android_apks[0])
    if approval is not None:
        claims = approval["artifact_claims"]
        if claims.get("android_apk_sha256") != android_record["sha256"]:
            raise ManifestError("released Android APK was not the APK proven by A-01")
        if claims.get("windows_installer_sha256") not in {record["sha256"] for record in windows_records}:
            raise ManifestError("released Windows installer was not the installer proven by X-01")
        if claims.get("cloud_image_digest") != cloud["digest"]:
            raise ManifestError("released Cloud image was not the deployment proven by C-01")

    manifest = {
        "schema_version": "notemeld.first-batch-rc.v1",
        "version": version,
        "commit": commit,
        "protocol_version": "notemeld.sync.v1",
        "artifacts": {
            "windows_x86_64": windows_records,
            "windows_updater_signatures": [artifact_record(path) for path in windows_updater_signatures],
            "android": android_record,
            "cloud": {"image": cloud["image"], "digest": cloud["digest"], "commit": cloud["commit"]},
        },
        "required_live_gates": 19,
        "release_approved": approval is not None,
    }
    if approval is not None:
        manifest["live_gate_evidence"] = approval["evidence"]
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--cloud-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--approval-ledger", type=Path, help="19/19 PASS ledger whose JSON evidence is bound to this RC")
    args = parser.parse_args()
    try:
        approval = None
        if args.approval_ledger is not None:
            from verify_first_batch_ledger import verify_ledger

            approval = verify_ledger(
                args.approval_ledger.read_text(encoding="utf-8"),
                evidence_root=args.approval_ledger.parent,
                expected_version=args.version,
                expected_commit=args.commit.lower(),
            )
        manifest = generate_manifest(args.version, args.commit, args.artifact_dir, args.cloud_metadata, approval=approval)
    except (ManifestError, OSError, RuntimeError) as exc:
        parser.error(str(exc))
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"first-batch RC manifest: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
