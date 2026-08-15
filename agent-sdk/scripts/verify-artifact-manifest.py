#!/usr/bin/env python3
"""Create and verify fail-closed NoteMeld Agent SDK artifact manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Iterable


MANIFEST_NAME = "artifact-manifest.json"
REQUIRED_FIELDS = {
    "path": str,
    "kind": str,
    "sdk_version": str,
    "schema_version": str,
    "target_triple": str,
    "binding_version": str,
    "sha256": str,
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_artifact(root: Path, raw_path: str) -> tuple[Path, str]:
    pure = PurePosixPath(raw_path)
    if pure.is_absolute():
        raise ManifestError(f"artifact path escapes artifact root: {raw_path}")
    unresolved = root / Path(*pure.parts)
    if unresolved.is_symlink():
        raise ManifestError(f"artifact path is a symlink: {raw_path}")
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ManifestError(
            f"artifact path escapes artifact root: {raw_path}"
        ) from error
    if not candidate.is_file():
        raise ManifestError(f"artifact path is not a regular file: {raw_path}")
    return candidate, candidate.relative_to(root).as_posix()


def _parse_artifact(value: str) -> tuple[str, str]:
    kind, separator, path = value.partition("=")
    if not separator or not kind.strip() or not path.strip():
        raise argparse.ArgumentTypeError("artifact must use KIND=RELATIVE_PATH")
    return kind.strip(), path.strip()


def _parse_license(value: str) -> dict[str, str]:
    component, separator, license_name = value.partition("=")
    if not separator or not component.strip() or not license_name.strip():
        raise argparse.ArgumentTypeError("license must use COMPONENT=SPDX_EXPRESSION")
    return {"component": component.strip(), "license": license_name.strip()}


def _read_license_inventory(path: Path) -> list[dict[str, str]]:
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"invalid license inventory {path}: {error}") from error
    if not isinstance(inventory, list) or not inventory:
        raise ManifestError(f"license inventory must be a non-empty list: {path}")
    normalized: list[dict[str, str]] = []
    for entry in inventory:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(field), str) and entry[field]
            for field in ("component", "license")
        ):
            raise ManifestError(f"invalid license inventory entry in {path}")
        normalized.append(
            {"component": entry["component"], "license": entry["license"]}
        )
    return normalized


def create_license_inventory(args: argparse.Namespace) -> dict[str, object]:
    try:
        metadata = json.loads(args.cargo_metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"invalid cargo metadata: {error}") from error
    packages = metadata.get("packages") if isinstance(metadata, dict) else None
    if not isinstance(packages, list) or not packages:
        raise ManifestError("cargo metadata contains no packages")
    inventory: dict[str, str] = {}
    for package in packages:
        if not isinstance(package, dict):
            raise ManifestError("cargo metadata package must be an object")
        name = package.get("name")
        version = package.get("version")
        license_name = package.get("license")
        if not all(isinstance(value, str) and value for value in (name, version)):
            raise ManifestError("cargo metadata package is missing name or version")
        if not isinstance(license_name, str) or not license_name:
            raise ManifestError(f"package {name}@{version} has no SPDX license")
        inventory[f"{name}@{version}"] = license_name
    entries = [
        {"component": component, "license": inventory[component]}
        for component in sorted(inventory)
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"license_count": len(entries), "output": str(args.output)}


def create_manifest(args: argparse.Namespace) -> dict[str, object]:
    artifact_root = args.artifact_dir.resolve()
    if not artifact_root.is_dir():
        raise ManifestError(f"artifact directory does not exist: {artifact_root}")

    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for kind, raw_path in args.artifact:
        artifact, relative_path = _relative_artifact(artifact_root, raw_path)
        if relative_path in seen:
            raise ManifestError(f"duplicate artifact path: {relative_path}")
        seen.add(relative_path)
        entries.append(
            {
                "path": relative_path,
                "kind": kind,
                "sdk_version": args.sdk_version,
                "schema_version": args.schema_version,
                "target_triple": args.target_triple,
                "binding_version": args.binding_version,
                "sha256": _sha256(artifact),
            }
        )
    if not entries:
        raise ManifestError("manifest must contain at least one artifact")

    output = (args.output or artifact_root / MANIFEST_NAME).resolve()
    try:
        output.relative_to(artifact_root)
    except ValueError as error:
        raise ManifestError("manifest output escapes artifact root") from error

    licenses = (
        _read_license_inventory(args.license_inventory_file)
        if args.license_inventory_file
        else args.license
    )
    document: dict[str, object] = {
        "manifest_version": 1,
        "license_inventory": licenses,
        "artifacts": sorted(entries, key=lambda entry: entry["path"]),
    }
    output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "manifest": output.relative_to(artifact_root).as_posix(),
        "target": args.target_triple,
        "artifact_count": len(entries),
    }


def _load_manifest(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"invalid manifest {path}: {error}") from error
    if not isinstance(document, dict):
        raise ManifestError(f"manifest must be an object: {path}")
    if document.get("manifest_version") != 1:
        raise ManifestError(f"manifest_version mismatch in {path}")
    licenses = document.get("license_inventory")
    if not isinstance(licenses, list) or not licenses:
        raise ManifestError(f"missing license_inventory in {path}")
    for license_entry in licenses:
        if not isinstance(license_entry, dict) or not all(
            isinstance(license_entry.get(field), str) and license_entry[field]
            for field in ("component", "license")
        ):
            raise ManifestError(f"invalid license_inventory entry in {path}")
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ManifestError(f"manifest has no artifacts: {path}")
    return document


def _check_required_fields(entry: object, manifest: Path) -> dict[str, str]:
    if not isinstance(entry, dict):
        raise ManifestError(f"artifact entry must be an object in {manifest}")
    for field, field_type in REQUIRED_FIELDS.items():
        value = entry.get(field)
        if not isinstance(value, field_type) or not value:
            raise ManifestError(f"missing field {field} in {manifest}")
    return entry  # type: ignore[return-value]


def verify_manifests(args: argparse.Namespace) -> dict[str, object]:
    artifact_root = args.artifact_root.resolve()
    if not artifact_root.is_dir():
        raise ManifestError(f"artifact root does not exist: {artifact_root}")
    manifests = sorted(artifact_root.rglob(MANIFEST_NAME))
    if not manifests:
        raise ManifestError("no artifact-manifest.json files found")

    expected_targets = set(args.expected_target)
    observed_targets: set[str] = set()
    manifest_targets: set[str] = set()
    seen_paths: set[Path] = set()
    artifact_count = 0

    for manifest in manifests:
        document = _load_manifest(manifest)
        local_targets: set[str] = set()
        manifest_root = manifest.parent.resolve()
        for raw_entry in document["artifacts"]:  # type: ignore[index]
            entry = _check_required_fields(raw_entry, manifest)
            target = entry["target_triple"]
            local_targets.add(target)
            observed_targets.add(target)
            if expected_targets and target not in expected_targets:
                raise ManifestError(f"unexpected target {target} in {manifest}")
            for field, expected in (
                ("sdk_version", args.sdk_version),
                ("schema_version", args.schema_version),
                ("binding_version", args.binding_version),
            ):
                if entry[field] != expected:
                    raise ManifestError(
                        f"{field} mismatch in {manifest}: "
                        f"expected {expected}, got {entry[field]}"
                    )

            artifact, _ = _relative_artifact(manifest_root, entry["path"])
            try:
                artifact.relative_to(artifact_root)
            except ValueError as error:
                raise ManifestError(
                    f"artifact path escapes artifact root: {entry['path']}"
                ) from error
            if artifact in seen_paths:
                raise ManifestError(f"duplicate artifact path: {entry['path']}")
            seen_paths.add(artifact)
            checksum = entry["sha256"]
            if not SHA256_PATTERN.fullmatch(checksum):
                raise ManifestError(f"invalid sha256 in {manifest}: {entry['path']}")
            actual_checksum = _sha256(artifact)
            if actual_checksum != checksum:
                raise ManifestError(f"checksum mismatch for {entry['path']}")
            if entry["kind"] == "license-inventory":
                inventory = _read_license_inventory(artifact)
                if inventory != document["license_inventory"]:
                    raise ManifestError(
                        f"license inventory mismatch for {entry['path']}"
                    )
            artifact_count += 1

        if len(local_targets) != 1:
            raise ManifestError(f"manifest mixes target triples: {manifest}")
        only_target = next(iter(local_targets))
        if only_target in manifest_targets:
            raise ManifestError(f"duplicate target manifest: {only_target}")
        manifest_targets.add(only_target)

    missing = expected_targets - observed_targets
    if missing:
        raise ManifestError(
            "missing expected target(s): " + ", ".join(sorted(missing))
        )
    return {
        "manifest_count": len(manifests),
        "artifact_count": artifact_count,
        "targets": sorted(observed_targets),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="create a deterministic manifest")
    create.add_argument("--artifact-dir", type=Path, required=True)
    create.add_argument("--output", type=Path)
    create.add_argument("--target-triple", required=True)
    create.add_argument("--sdk-version", required=True)
    create.add_argument("--schema-version", required=True)
    create.add_argument("--binding-version", required=True)
    create.add_argument(
        "--artifact", action="append", type=_parse_artifact, default=[], required=True
    )
    create.add_argument(
        "--license",
        action="append",
        type=_parse_license,
        default=[{"component": "notemeld-agent-sdk", "license": "MIT"}],
    )
    create.add_argument("--license-inventory-file", type=Path)
    create.set_defaults(handler=create_manifest)

    licenses = subparsers.add_parser(
        "licenses", help="create a deterministic inventory from cargo metadata"
    )
    licenses.add_argument("--cargo-metadata", type=Path, required=True)
    licenses.add_argument("--output", type=Path, required=True)
    licenses.set_defaults(handler=create_license_inventory)

    verify = subparsers.add_parser("verify", help="verify downloaded artifacts")
    verify.add_argument("--artifact-root", type=Path, required=True)
    verify.add_argument("--sdk-version", required=True)
    verify.add_argument("--schema-version", required=True)
    verify.add_argument("--binding-version", required=True)
    verify.add_argument("--expected-target", action="append", default=[])
    verify.set_defaults(handler=verify_manifests)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        summary = args.handler(args)
    except ManifestError as error:
        print(f"artifact manifest verification failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
