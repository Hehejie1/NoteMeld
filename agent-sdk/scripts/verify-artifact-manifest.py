#!/usr/bin/env python3
"""Create and verify fail-closed NoteMeld Agent SDK artifact manifests."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Iterable
import zipfile

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility for source installs.
    import tomli as tomllib  # type: ignore[no-redef]


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
ANDROID_ABIS = ("armeabi-v7a", "arm64-v8a", "x86", "x86_64")
ANDROID_TARGETS = (
    "aarch64-linux-android",
    "armv7-linux-androideabi",
    "i686-linux-android",
    "x86_64-linux-android",
)
IOS_TARGETS = ("aarch64-apple-ios", "aarch64-apple-ios-sim")
DESKTOP_TARGETS = {
    "x86_64-apple-darwin",
    "aarch64-apple-darwin",
    "x86_64-pc-windows-msvc",
    "x86_64-unknown-linux-gnu",
    "aarch64-unknown-linux-gnu",
}
TARGET_REQUIRED_KINDS = {
    **{
        target: frozenset(
            {
                "native-library",
                "python-wheel",
                "c-header",
                "abi-contract",
                "license-inventory",
                "cargo-lock",
            }
        )
        for target in DESKTOP_TARGETS
    },
    **{
        target: frozenset(
            {
                "static-library",
                "swift-xcframework",
                "swift-package",
                "abi-contract",
                "license-inventory",
                "cargo-lock",
            }
        )
        for target in IOS_TARGETS
    },
    **{
        target: frozenset(
            {
                "native-library",
                "kotlin-aar",
                "abi-contract",
                "license-inventory",
                "cargo-lock",
            }
        )
        for target in ANDROID_TARGETS
    },
    "aarch64-unknown-linux-ohos": frozenset(
        {
            "native-library",
            "openharmony-har",
            "abi-contract",
            "license-inventory",
            "cargo-lock",
        }
    ),
}
KNOWN_KINDS = frozenset().union(*TARGET_REQUIRED_KINDS.values())
CONTAINER_MARKERS = {
    "python-wheel": "notemeld_agent_sdk/notemeld-agent-sdk.json",
    "kotlin-aar": "META-INF/notemeld-agent-sdk.json",
    "swift-xcframework": "notemeld-agent-sdk.json",
    "swift-package": "notemeld-agent-sdk.json",
    "openharmony-har": "notemeld-agent-sdk.json",
}


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


def _read_license_inventory(path: Path) -> dict[str, object]:
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"invalid license inventory {path}: {error}") from error
    if not isinstance(inventory, dict) or inventory.get("format_version") != 1:
        raise ManifestError(f"license inventory must be a versioned object: {path}")
    lock_digest = inventory.get("cargo_lock_sha256")
    if not isinstance(lock_digest, str) or not SHA256_PATTERN.fullmatch(lock_digest):
        raise ManifestError(f"license inventory has invalid cargo lock digest: {path}")
    root_package = inventory.get("root_package")
    if not isinstance(root_package, str) or not root_package:
        raise ManifestError(f"license inventory has invalid root package: {path}")
    resolve_digest = inventory.get("resolve_sha256")
    if not isinstance(resolve_digest, str) or not SHA256_PATTERN.fullmatch(
        resolve_digest
    ):
        raise ManifestError(f"license inventory has invalid resolve digest: {path}")
    packages = inventory.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ManifestError(f"license inventory packages must be a non-empty list: {path}")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in packages:
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(field), str) and entry[field]
            for field in ("component", "license")
        ):
            raise ManifestError(f"invalid license inventory entry in {path}")
        component = entry["component"]
        if component in seen:
            raise ManifestError(f"duplicate license component {component} in {path}")
        seen.add(component)
        normalized_entry = {"component": component, "license": entry["license"]}
        checksum = entry.get("checksum")
        if checksum is not None:
            if not isinstance(checksum, str) or not SHA256_PATTERN.fullmatch(checksum):
                raise ManifestError(f"invalid package checksum for {component} in {path}")
            normalized_entry["checksum"] = checksum
        normalized.append(normalized_entry)
    return {
        "format_version": 1,
        "cargo_lock_sha256": lock_digest,
        "root_package": root_package,
        "resolve_sha256": resolve_digest,
        "packages": sorted(normalized, key=lambda entry: entry["component"]),
    }


def _read_cargo_lock(path: Path) -> tuple[set[str], dict[str, str]]:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ManifestError(f"invalid Cargo.lock {path}: {error}") from error
    packages = document.get("package") if isinstance(document, dict) else None
    if not isinstance(packages, list) or not packages:
        raise ManifestError(f"Cargo.lock contains no packages: {path}")
    components: set[str] = set()
    checksums: dict[str, str] = {}
    for package in packages:
        if not isinstance(package, dict):
            raise ManifestError(f"invalid package in Cargo.lock: {path}")
        name = package.get("name")
        version = package.get("version")
        if not all(isinstance(value, str) and value for value in (name, version)):
            raise ManifestError(f"Cargo.lock package missing name/version: {path}")
        component = f"{name}@{version}"
        if component in components:
            raise ManifestError(f"ambiguous duplicate locked package {component}")
        components.add(component)
        checksum = package.get("checksum")
        if checksum is not None:
            if not isinstance(checksum, str) or not SHA256_PATTERN.fullmatch(checksum):
                raise ManifestError(f"invalid Cargo.lock checksum for {component}")
            checksums[component] = checksum
    return components, checksums


def _validate_inventory_against_lock(
    inventory: dict[str, object], lock_path: Path
) -> None:
    actual_digest = _sha256(lock_path)
    if inventory["cargo_lock_sha256"] != actual_digest:
        raise ManifestError("cargo lock digest mismatch")
    locked_components, locked_checksums = _read_cargo_lock(lock_path)
    packages = inventory["packages"]
    assert isinstance(packages, list)
    inventory_components = {entry["component"] for entry in packages}
    if not inventory_components <= locked_components:
        extra = sorted(inventory_components - locked_components)
        raise ManifestError(
            f"license inventory contains packages absent from Cargo.lock; extra={extra}"
        )
    inventory_checksums = {
        entry["component"]: entry["checksum"]
        for entry in packages
        if "checksum" in entry
    }
    expected_checksums = {
        component: checksum
        for component, checksum in locked_checksums.items()
        if component in inventory_components
    }
    if inventory_checksums != expected_checksums:
        raise ManifestError("license inventory package checksums do not match Cargo.lock")


def _inventory_from_metadata(
    metadata_path: Path, cargo_lock: Path, root_package: str
) -> dict[str, object]:
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"invalid cargo metadata: {error}") from error
    packages = metadata.get("packages") if isinstance(metadata, dict) else None
    resolve = metadata.get("resolve") if isinstance(metadata, dict) else None
    nodes = resolve.get("nodes") if isinstance(resolve, dict) else None
    if not isinstance(packages, list) or not packages:
        raise ManifestError("cargo metadata contains no packages")
    if not isinstance(nodes, list) or not nodes:
        raise ManifestError("cargo metadata contains no resolve graph")

    packages_by_id: dict[str, dict[str, object]] = {}
    roots: list[str] = []
    for package in packages:
        if not isinstance(package, dict):
            raise ManifestError("cargo metadata package must be an object")
        package_id = package.get("id")
        name = package.get("name")
        if not isinstance(package_id, str) or not package_id:
            raise ManifestError("cargo metadata package is missing id")
        if package_id in packages_by_id:
            raise ManifestError(f"duplicate cargo metadata package id {package_id}")
        packages_by_id[package_id] = package
        if name == root_package:
            roots.append(package_id)
    if len(roots) != 1:
        raise ManifestError(
            f"cargo metadata must contain exactly one {root_package} package"
        )

    dependencies_by_id: dict[str, list[str]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise ManifestError("cargo metadata resolve node must be an object")
        node_id = node.get("id")
        dependencies = node.get("dependencies")
        if not isinstance(node_id, str) or not isinstance(dependencies, list) or not all(
            isinstance(dependency, str) and dependency for dependency in dependencies
        ):
            raise ManifestError("cargo metadata resolve node is malformed")
        if node_id in dependencies_by_id:
            raise ManifestError(f"duplicate cargo metadata resolve node {node_id}")
        dependencies_by_id[node_id] = dependencies

    closure: set[str] = set()
    pending = [roots[0]]
    while pending:
        package_id = pending.pop()
        if package_id in closure:
            continue
        if package_id not in packages_by_id or package_id not in dependencies_by_id:
            raise ManifestError(f"unresolved cargo package id {package_id}")
        closure.add(package_id)
        pending.extend(dependencies_by_id[package_id])

    _, locked_checksums = _read_cargo_lock(cargo_lock)
    inventory: dict[str, dict[str, str]] = {}
    component_by_id: dict[str, str] = {}
    for package_id in closure:
        package = packages_by_id[package_id]
        name = package.get("name")
        version = package.get("version")
        license_name = package.get("license")
        if not all(isinstance(value, str) and value for value in (name, version)):
            raise ManifestError("cargo metadata package is missing name or version")
        if not isinstance(license_name, str) or not license_name:
            raise ManifestError(f"package {name}@{version} has no SPDX license")
        component = f"{name}@{version}"
        if component in inventory:
            raise ManifestError(f"duplicate cargo resolve component {component}")
        entry = {"component": component, "license": license_name}
        if component in locked_checksums:
            entry["checksum"] = locked_checksums[component]
        inventory[component] = entry
        component_by_id[package_id] = component

    resolve_summary = [
        {
            "component": component_by_id[package_id],
            "dependencies": sorted(
                component_by_id[dependency]
                for dependency in dependencies_by_id[package_id]
                if dependency in closure
            ),
        }
        for package_id in sorted(closure, key=lambda item: component_by_id[item])
    ]
    resolve_bytes = json.dumps(
        resolve_summary, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    document: dict[str, object] = {
        "format_version": 1,
        "cargo_lock_sha256": _sha256(cargo_lock),
        "root_package": component_by_id[roots[0]],
        "resolve_sha256": hashlib.sha256(resolve_bytes).hexdigest(),
        "packages": [inventory[component] for component in sorted(inventory)],
    }
    _validate_inventory_against_lock(document, cargo_lock)
    return document


def create_license_inventory(args: argparse.Namespace) -> dict[str, object]:
    document = _inventory_from_metadata(
        args.cargo_metadata, args.cargo_lock, args.root_package
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"license_count": len(document["packages"]), "output": str(args.output)}


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

    licenses = _read_license_inventory(args.license_inventory_file)
    cargo_lock = args.cargo_lock_file.resolve()
    try:
        cargo_lock.relative_to(artifact_root)
    except ValueError as error:
        raise ManifestError("Cargo.lock artifact escapes artifact root") from error
    _validate_inventory_against_lock(licenses, cargo_lock)
    kinds = [entry["kind"] for entry in entries]
    if kinds.count("license-inventory") != 1:
        raise ManifestError("manifest requires exactly one license-inventory artifact")
    if kinds.count("cargo-lock") != 1:
        raise ManifestError("manifest requires exactly one cargo-lock artifact")
    document: dict[str, object] = {
        "manifest_version": 1,
        "license_inventory": licenses,
        "cargo_lock_sha256": licenses["cargo_lock_sha256"],
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
    if "license_inventory" not in document:
        raise ManifestError(f"missing license_inventory in {path}")
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


def _verify_binding_marker(
    marker: object,
    *,
    target: str,
    sdk_version: str,
    schema_version: str,
    binding_version: str,
) -> None:
    if not isinstance(marker, dict):
        raise ManifestError("container binding metadata must be an object")
    for field, expected in (
        ("sdk_version", sdk_version),
        ("schema_version", schema_version),
        ("binding_version", binding_version),
    ):
        if marker.get(field) != expected:
            raise ManifestError(
                f"container {field} mismatch: expected {expected}, got {marker.get(field)}"
            )
    targets = marker.get("target_triples")
    if not isinstance(targets, list) or target not in targets or not all(
        isinstance(item, str) and item for item in targets
    ):
        raise ManifestError(f"container target_triples do not include {target}")


def _read_zip_json(archive: zipfile.ZipFile, name: str, label: str) -> object:
    try:
        raw = archive.read(name)
    except KeyError as error:
        raise ManifestError(f"{label} is missing {name}") from error
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"invalid JSON in {label}: {name}") from error


def _python_constants(source: bytes) -> dict[str, object]:
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as error:
        raise ManifestError("python wheel runtime.py is invalid") from error
    constants: dict[str, object] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
        ):
            constants[node.targets[0].id] = node.value.value
    return constants


def _inspect_container(
    path: Path,
    *,
    kind: str,
    target: str,
    sdk_version: str,
    schema_version: str,
    binding_version: str,
) -> None:
    if not zipfile.is_zipfile(path):
        raise ManifestError(f"{kind} is not a valid ZIP container: {path.name}")
    marker_name = CONTAINER_MARKERS[kind]
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        marker = _read_zip_json(archive, marker_name, kind)
        _verify_binding_marker(
            marker,
            target=target,
            sdk_version=sdk_version,
            schema_version=schema_version,
            binding_version=binding_version,
        )
        if kind == "python-wheel":
            metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
            if len(metadata_names) != 1:
                raise ManifestError("python wheel requires exactly one METADATA file")
            metadata = archive.read(metadata_names[0]).decode("utf-8", errors="strict")
            if f"Version: {sdk_version}\n" not in metadata.replace("\r\n", "\n"):
                raise ManifestError("python wheel METADATA version mismatch")
            runtime_name = "notemeld_agent_sdk/runtime.py"
            if runtime_name not in names:
                raise ManifestError("python wheel is missing runtime.py")
            constants = _python_constants(archive.read(runtime_name))
            if constants.get("SDK_VERSION") != sdk_version:
                raise ManifestError("python wheel SDK_VERSION mismatch")
            if constants.get("SCHEMA_VERSION") != schema_version:
                raise ManifestError("python wheel SCHEMA_VERSION mismatch")
            expected_native = (
                "notemeld_agent.dll"
                if target.endswith("windows-msvc")
                else "libnotemeld_agent.dylib"
                if target.endswith("apple-darwin")
                else "libnotemeld_agent.so"
            )
            if f"notemeld_agent_sdk/native/{expected_native}" not in names:
                raise ManifestError("python wheel is missing packaged native library")
        elif kind == "kotlin-aar":
            for abi in ANDROID_ABIS:
                for library in (
                    "libnotemeld_agent.so",
                    "libnotemeld_agent_jni.so",
                ):
                    member = f"jni/{abi}/{library}"
                    if member not in names:
                        raise ManifestError(f"Android AAR is missing {member}")
                    if not archive.read(member).startswith(b"\x7fELF"):
                        raise ManifestError(f"Android AAR contains invalid {member}")
        elif kind == "swift-xcframework":
            static_libraries = [name for name in names if name.endswith("libnotemeld_agent.a")]
            if len(static_libraries) < 2:
                raise ManifestError("XCFramework is missing device/simulator static libraries")
            if not any(name.endswith("Headers/notemeld_agent.h") for name in names):
                raise ManifestError("XCFramework is missing notemeld_agent.h")
            if not any(name.endswith("Headers/module.modulemap") for name in names):
                raise ManifestError("XCFramework is missing module.modulemap")
        elif kind == "swift-package":
            try:
                package = archive.read("Package.swift").decode("utf-8")
            except (KeyError, UnicodeDecodeError) as error:
                raise ManifestError("Swift package is missing valid Package.swift") from error
            if ".binaryTarget(" not in package or "NoteMeldAgentNative.xcframework" not in package:
                raise ManifestError("Swift package does not link its XCFramework binary target")
            if not any(
                name.startswith("NoteMeldAgentNative.xcframework/")
                and name.endswith("Info.plist")
                for name in names
            ):
                raise ManifestError("Swift package is missing embedded XCFramework")
            embedded_prefix = "NoteMeldAgentNative.xcframework/"
            embedded_libraries = [
                name
                for name in names
                if name.startswith(embedded_prefix)
                and name.endswith("libnotemeld_agent.a")
            ]
            if len(embedded_libraries) < 2:
                raise ManifestError(
                    "Swift package embedded XCFramework is missing device/simulator libraries"
                )
            for required_suffix in (
                "Headers/notemeld_agent.h",
                "Headers/module.modulemap",
            ):
                if not any(
                    name.startswith(embedded_prefix)
                    and name.endswith(required_suffix)
                    for name in names
                ):
                    raise ManifestError(
                        "Swift package embedded XCFramework is missing "
                        + required_suffix
                    )
        elif kind == "openharmony-har":
            for library in ("libnotemeld_agent.so", "libnotemeld_agent_napi.so"):
                if not any(name.endswith(library) for name in names):
                    raise ManifestError(f"OpenHarmony HAR is missing {library}")
            if not any(name.endswith("Index.ets") or name.endswith("index.ets") for name in names):
                raise ManifestError("OpenHarmony HAR is missing ArkTS binding")


def _inspect_non_container(
    path: Path,
    *,
    kind: str,
    target: str,
    sdk_version: str,
    schema_version: str,
) -> None:
    if kind == "abi-contract":
        try:
            abi = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ManifestError(f"invalid ABI contract: {path.name}") from error
        if not isinstance(abi, dict) or abi.get("abi_version") != 1:
            raise ManifestError("invalid ABI contract version")
        if abi.get("sdk_version") != sdk_version:
            raise ManifestError("ABI contract sdk_version mismatch")
        if abi.get("schema_version") != schema_version:
            raise ManifestError("ABI contract schema_version mismatch")
    elif kind == "c-header":
        try:
            header = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ManifestError("invalid C header") from error
        if "notemeld_agent_sdk_version" not in header:
            raise ManifestError("C header is missing Agent SDK declarations")
    elif kind in {"native-library", "static-library"}:
        prefix = path.read_bytes()[:8]
        if kind == "static-library":
            valid = prefix == b"!<arch>\n"
        elif target.endswith("windows-msvc"):
            valid = prefix.startswith(b"MZ")
        elif target.endswith("apple-darwin"):
            valid = prefix[:4] in {
                b"\xfe\xed\xfa\xce",
                b"\xce\xfa\xed\xfe",
                b"\xfe\xed\xfa\xcf",
                b"\xcf\xfa\xed\xfe",
            }
        else:
            valid = prefix.startswith(b"\x7fELF")
        if not valid:
            raise ManifestError(f"placeholder or invalid {kind}: {path.name}")


def verify_manifests(args: argparse.Namespace) -> dict[str, object]:
    artifact_root = args.artifact_root.resolve()
    if not artifact_root.is_dir():
        raise ManifestError(f"artifact root does not exist: {artifact_root}")
    manifests = sorted(artifact_root.rglob(MANIFEST_NAME))
    if not manifests:
        raise ManifestError("no artifact-manifest.json files found")

    expected_targets = set(args.expected_target)
    expected_inventory = _inventory_from_metadata(
        args.expected_cargo_metadata,
        args.expected_cargo_lock,
        args.root_package,
    )
    observed_targets: set[str] = set()
    manifest_targets: set[str] = set()
    seen_paths: set[Path] = set()
    artifact_count = 0

    for manifest in manifests:
        document = _load_manifest(manifest)
        local_targets: set[str] = set()
        artifacts_by_kind: dict[str, list[Path]] = {}
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
            kind = entry["kind"]
            if kind not in KNOWN_KINDS:
                raise ManifestError(f"unknown artifact kind {kind}")
            artifacts_by_kind.setdefault(kind, []).append(artifact)
            if kind in CONTAINER_MARKERS:
                _inspect_container(
                    artifact,
                    kind=kind,
                    target=target,
                    sdk_version=args.sdk_version,
                    schema_version=args.schema_version,
                    binding_version=args.binding_version,
                )
            elif kind not in {"license-inventory", "cargo-lock"}:
                _inspect_non_container(
                    artifact,
                    kind=kind,
                    target=target,
                    sdk_version=args.sdk_version,
                    schema_version=args.schema_version,
                )
            artifact_count += 1

        if len(local_targets) != 1:
            raise ManifestError(f"manifest mixes target triples: {manifest}")
        only_target = next(iter(local_targets))
        if only_target in manifest_targets:
            raise ManifestError(f"duplicate target manifest: {only_target}")
        required_kinds = TARGET_REQUIRED_KINDS.get(only_target)
        if required_kinds is None:
            raise ManifestError(f"unsupported target triple: {only_target}")

        license_paths = artifacts_by_kind.get("license-inventory", [])
        if len(license_paths) != 1:
            raise ManifestError(
                "required artifact kind license-inventory: "
                "exactly one license-inventory artifact is required"
            )
        lock_paths = artifacts_by_kind.get("cargo-lock", [])
        if len(lock_paths) != 1:
            raise ManifestError(
                "required artifact kind cargo-lock: exactly one cargo-lock artifact is required"
            )
        inventory = _read_license_inventory(license_paths[0])
        _validate_inventory_against_lock(inventory, lock_paths[0])
        if inventory != expected_inventory:
            raise ManifestError(
                "license inventory does not match the checkout Cargo resolve closure"
            )
        if _sha256(lock_paths[0]) != _sha256(args.expected_cargo_lock):
            raise ManifestError("artifact Cargo.lock does not match expected Cargo.lock")
        if inventory != document["license_inventory"]:
            raise ManifestError("license inventory manifest/file mismatch")
        if document.get("cargo_lock_sha256") != inventory["cargo_lock_sha256"]:
            raise ManifestError("manifest cargo lock digest mismatch")

        for kind in sorted(required_kinds):
            if len(artifacts_by_kind.get(kind, [])) != 1:
                raise ManifestError(
                    f"required artifact kind {kind} must appear exactly once for {only_target}"
                )
        unexpected_kinds = set(artifacts_by_kind) - required_kinds
        if unexpected_kinds:
            raise ManifestError(
                f"artifact kind(s) not allowed for {only_target}: "
                + ", ".join(sorted(unexpected_kinds))
            )
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
    create.add_argument("--license-inventory-file", type=Path, required=True)
    create.add_argument("--cargo-lock-file", type=Path, required=True)
    create.set_defaults(handler=create_manifest)

    licenses = subparsers.add_parser(
        "licenses", help="create a deterministic inventory from cargo metadata"
    )
    licenses.add_argument("--cargo-metadata", type=Path, required=True)
    licenses.add_argument("--cargo-lock", type=Path, required=True)
    licenses.add_argument("--root-package", required=True)
    licenses.add_argument("--output", type=Path, required=True)
    licenses.set_defaults(handler=create_license_inventory)

    verify = subparsers.add_parser("verify", help="verify downloaded artifacts")
    verify.add_argument("--artifact-root", type=Path, required=True)
    verify.add_argument("--sdk-version", required=True)
    verify.add_argument("--schema-version", required=True)
    verify.add_argument("--binding-version", required=True)
    verify.add_argument("--expected-target", action="append", default=[])
    verify.add_argument("--expected-cargo-metadata", type=Path, required=True)
    verify.add_argument("--expected-cargo-lock", type=Path, required=True)
    verify.add_argument("--root-package", required=True)
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
