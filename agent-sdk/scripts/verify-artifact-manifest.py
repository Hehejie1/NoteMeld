#!/usr/bin/env python3
"""Create and verify fail-closed NoteMeld Agent SDK artifact manifests."""

from __future__ import annotations

import argparse
import ast
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import struct
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
CONTAINER_ABI_CONTRACTS = {
    "python-wheel": "notemeld_agent_sdk/abi-v1.json",
    "kotlin-aar": "META-INF/notemeld-agent-abi.json",
    "swift-xcframework": "abi-v1.json",
    "swift-package": "abi-v1.json",
    "openharmony-har": "notemeld-agent-abi.json",
}
TARGET_ARCHITECTURES = {
    "x86_64-apple-darwin": "x86_64",
    "aarch64-apple-darwin": "aarch64",
    "x86_64-pc-windows-msvc": "x86_64",
    "x86_64-unknown-linux-gnu": "x86_64",
    "aarch64-unknown-linux-gnu": "aarch64",
    "aarch64-apple-ios": "aarch64",
    "aarch64-apple-ios-sim": "aarch64",
    "aarch64-linux-android": "aarch64",
    "armv7-linux-androideabi": "armv7",
    "i686-linux-android": "x86",
    "x86_64-linux-android": "x86_64",
    "aarch64-unknown-linux-ohos": "aarch64",
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
    if pure.is_absolute() or not pure.parts or any(
        part in {"", ".", ".."} for part in pure.parts
    ):
        raise ManifestError(f"artifact path escapes artifact root: {raw_path}")
    unresolved = root
    for part in pure.parts:
        unresolved /= part
        if unresolved.is_symlink():
            raise ManifestError(
                f"artifact path contains a symlink component: {raw_path}"
            )
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


def _verify_container_marker_only(
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
    with zipfile.ZipFile(path) as archive:
        marker = _read_zip_json(archive, CONTAINER_MARKERS[kind], kind)
    _verify_binding_marker(
        marker,
        target=target,
        sdk_version=sdk_version,
        schema_version=schema_version,
        binding_version=binding_version,
    )


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


def _read_abi_contract_bytes(
    raw: bytes,
    *,
    label: str,
    sdk_version: str,
    schema_version: str,
) -> dict[str, object]:
    try:
        abi = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"invalid ABI contract in {label}") from error
    if not isinstance(abi, dict) or abi.get("abi_version") != 1:
        raise ManifestError(f"invalid ABI contract version in {label}")
    if abi.get("sdk_version") != sdk_version:
        raise ManifestError(f"ABI contract sdk_version mismatch in {label}")
    if abi.get("schema_version") != schema_version:
        raise ManifestError(f"ABI contract schema_version mismatch in {label}")
    return abi


def _binary_architecture(data: bytes, label: str) -> str:
    if data.startswith(b"\x7fELF"):
        if len(data) < 20 or data[4] not in {1, 2} or data[5] not in {1, 2}:
            raise ManifestError(f"invalid ELF architecture metadata in {label}")
        byte_order = "little" if data[5] == 1 else "big"
        machine = int.from_bytes(data[18:20], byte_order)
        architecture = {
            (1, 3): "x86",
            (1, 40): "armv7",
            (2, 62): "x86_64",
            (2, 183): "aarch64",
        }.get((data[4], machine))
        if architecture is None:
            raise ManifestError(
                f"unsupported ELF architecture class={data[4]} machine={machine} in {label}"
            )
        return architecture

    macho = {
        b"\xce\xfa\xed\xfe": ("little", 32),
        b"\xcf\xfa\xed\xfe": ("little", 64),
        b"\xfe\xed\xfa\xce": ("big", 32),
        b"\xfe\xed\xfa\xcf": ("big", 64),
    }.get(data[:4])
    if macho is not None:
        if len(data) < 8:
            raise ManifestError(f"truncated Mach-O header in {label}")
        byte_order, bits = macho
        cpu_type = int.from_bytes(data[4:8], byte_order)
        architecture = {
            (32, 7): "x86",
            (64, 0x01000007): "x86_64",
            (32, 12): "armv7",
            (64, 0x0100000C): "aarch64",
        }.get((bits, cpu_type))
        if architecture is None:
            raise ManifestError(
                f"unsupported Mach-O architecture cputype={cpu_type} in {label}"
            )
        return architecture

    if data.startswith(b"MZ"):
        if len(data) < 64:
            raise ManifestError(f"truncated PE header in {label}")
        pe_offset = int.from_bytes(data[0x3C:0x40], "little")
        if pe_offset + 6 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\0\0":
            raise ManifestError(f"invalid PE header in {label}")
        machine = int.from_bytes(data[pe_offset + 4 : pe_offset + 6], "little")
        architecture = {0x014C: "x86", 0x8664: "x86_64", 0xAA64: "aarch64"}.get(
            machine
        )
        if architecture is None:
            raise ManifestError(f"unsupported PE architecture {machine} in {label}")
        return architecture

    raise ManifestError(f"unrecognized native architecture format in {label}")


def _archive_architecture(data: bytes, label: str) -> str:
    if not data.startswith(b"!<arch>\n"):
        raise ManifestError(f"invalid static archive in {label}")
    offset = 8
    while offset < len(data):
        if offset + 60 > len(data):
            raise ManifestError(f"truncated static archive member in {label}")
        header = data[offset : offset + 60]
        if header[58:60] != b"`\n":
            raise ManifestError(f"invalid static archive member header in {label}")
        try:
            size = int(header[48:58].decode("ascii").strip())
        except (UnicodeDecodeError, ValueError) as error:
            raise ManifestError(f"invalid static archive member size in {label}") from error
        name = header[:16].decode("ascii", errors="replace").strip().rstrip("/")
        start = offset + 60
        end = start + size
        if end > len(data):
            raise ManifestError(f"truncated static archive member body in {label}")
        member = data[start:end]
        if name.startswith("#1/"):
            try:
                extended_name_size = int(name[3:])
            except ValueError as error:
                raise ManifestError(f"invalid BSD archive member name in {label}") from error
            member = member[extended_name_size:]
        if name not in {"", "/", "//", "SYM64", "__.SYMDEF", "__.SYMDEF SORTED"}:
            try:
                return _binary_architecture(member, f"{label}:{name}")
            except ManifestError as error:
                if "unrecognized native architecture format" not in str(error):
                    raise
        offset = end + (size % 2)
    raise ManifestError(f"static archive contains no native object architecture in {label}")


def _assert_binary_target(
    data: bytes, *, target: str, label: str, static_archive: bool = False
) -> None:
    expected = TARGET_ARCHITECTURES.get(target)
    if expected is None:
        raise ManifestError(f"no architecture mapping for target {target}")
    actual = (
        _archive_architecture(data, label)
        if static_archive
        else _binary_architecture(data, label)
    )
    if actual != expected:
        raise ManifestError(
            f"native architecture mismatch in {label}: expected {expected}, got {actual}"
        )


def _wheel_platform_matches_target(platform: str, target: str) -> bool:
    if target == "x86_64-pc-windows-msvc":
        return platform == "win_amd64"
    if target == "x86_64-apple-darwin":
        return platform.startswith("macosx_") and platform.endswith("_x86_64")
    if target == "aarch64-apple-darwin":
        return platform.startswith("macosx_") and platform.endswith("_arm64")
    if target == "x86_64-unknown-linux-gnu":
        return platform.startswith("manylinux_") and platform.endswith("_x86_64")
    if target == "aarch64-unknown-linux-gnu":
        return platform.startswith("manylinux_") and platform.endswith("_aarch64")
    return False


def _verify_wheel_record(
    archive: zipfile.ZipFile, names: set[str], record_name: str
) -> None:
    try:
        rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
    except (KeyError, UnicodeDecodeError, csv.Error) as error:
        raise ManifestError("python wheel has invalid RECORD") from error
    records: dict[str, tuple[str, str]] = {}
    for row in rows:
        if len(row) != 3 or not row[0] or row[0] in records:
            raise ManifestError("python wheel RECORD has malformed or duplicate rows")
        pure = PurePosixPath(row[0])
        if pure.is_absolute() or ".." in pure.parts:
            raise ManifestError("python wheel RECORD contains unsafe path")
        records[row[0]] = (row[1], row[2])
    if set(records) != names:
        raise ManifestError("python wheel RECORD does not cover every package file")
    for name, (digest, size) in records.items():
        if name == record_name:
            if digest or size:
                raise ManifestError("python wheel RECORD self-row must omit hash and size")
            continue
        payload = archive.read(name)
        expected_digest = base64.urlsafe_b64encode(
            hashlib.sha256(payload).digest()
        ).rstrip(b"=").decode("ascii")
        if digest != f"sha256={expected_digest}" or size != str(len(payload)):
            raise ManifestError(f"python wheel RECORD hash/size mismatch for {name}")


def _swift_constant(source: str, name: str, label: str) -> str:
    match = re.search(rf"\b{re.escape(name)}\s*=\s*\"([^\"]+)\"", source)
    if match is None:
        raise ManifestError(f"Swift runtime is missing {name} in {label}")
    return match.group(1)


def _java_constant_fields(class_data: bytes, label: str) -> dict[str, object]:
    if len(class_data) < 10 or class_data[:4] != b"\xca\xfe\xba\xbe":
        raise ManifestError(f"invalid Java class in {label}")
    offset = 8

    def read_u1() -> int:
        nonlocal offset
        if offset + 1 > len(class_data):
            raise ManifestError(f"truncated Java class in {label}")
        value = class_data[offset]
        offset += 1
        return value

    def read_u2() -> int:
        nonlocal offset
        if offset + 2 > len(class_data):
            raise ManifestError(f"truncated Java class in {label}")
        value = int.from_bytes(class_data[offset : offset + 2], "big")
        offset += 2
        return value

    def read_u4() -> int:
        nonlocal offset
        if offset + 4 > len(class_data):
            raise ManifestError(f"truncated Java class in {label}")
        value = int.from_bytes(class_data[offset : offset + 4], "big")
        offset += 4
        return value

    pool_count = read_u2()
    pool: list[object | None] = [None] * pool_count
    index = 1
    while index < pool_count:
        tag = read_u1()
        if tag == 1:
            length = read_u2()
            if offset + length > len(class_data):
                raise ManifestError(f"truncated Java UTF8 constant in {label}")
            try:
                pool[index] = class_data[offset : offset + length].decode("utf-8")
            except UnicodeDecodeError as error:
                raise ManifestError(f"invalid Java UTF8 constant in {label}") from error
            offset += length
        elif tag in {3, 4}:
            pool[index] = read_u4()
        elif tag in {5, 6}:
            read_u4()
            read_u4()
            index += 1
        elif tag in {7, 8, 16, 19, 20}:
            pool[index] = (tag, read_u2())
        elif tag in {9, 10, 11, 12, 17, 18}:
            read_u2()
            read_u2()
        elif tag == 15:
            read_u1()
            read_u2()
        else:
            raise ManifestError(f"unsupported Java constant-pool tag {tag} in {label}")
        index += 1

    def utf8(pool_index: int) -> str:
        value = pool[pool_index] if 0 < pool_index < len(pool) else None
        if not isinstance(value, str):
            raise ManifestError(f"invalid Java UTF8 reference in {label}")
        return value

    def constant(pool_index: int) -> object:
        value = pool[pool_index] if 0 < pool_index < len(pool) else None
        if isinstance(value, tuple) and value[0] == 8:
            return utf8(value[1])
        return value

    read_u2()
    read_u2()
    read_u2()
    interfaces_count = read_u2()
    for _ in range(interfaces_count):
        read_u2()
    fields: dict[str, object] = {}
    for _ in range(read_u2()):
        read_u2()
        name = utf8(read_u2())
        read_u2()
        attributes_count = read_u2()
        for _ in range(attributes_count):
            attribute_name = utf8(read_u2())
            length = read_u4()
            end = offset + length
            if end > len(class_data):
                raise ManifestError(f"truncated Java field attribute in {label}")
            if attribute_name == "ConstantValue" and length == 2:
                fields[name] = constant(read_u2())
            offset = end
    return fields


def _inspect_xcframework(
    archive: zipfile.ZipFile,
    names: set[str],
    *,
    prefix: str,
    label: str,
) -> None:
    info_name = f"{prefix}Info.plist"
    try:
        document = plistlib.loads(archive.read(info_name))
    except (KeyError, plistlib.InvalidFileException) as error:
        raise ManifestError(f"{label} is missing valid XCFramework Info.plist") from error
    libraries = document.get("AvailableLibraries") if isinstance(document, dict) else None
    if not isinstance(libraries, list):
        raise ManifestError(f"{label} XCFramework has no AvailableLibraries")
    variants: set[tuple[str, str, tuple[str, ...]]] = set()
    for library in libraries:
        if not isinstance(library, dict):
            raise ManifestError(f"{label} XCFramework library entry is invalid")
        identifier = library.get("LibraryIdentifier")
        library_path = library.get("LibraryPath")
        headers_path = library.get("HeadersPath")
        platform = library.get("SupportedPlatform")
        variant = library.get("SupportedPlatformVariant", "")
        architectures = library.get("SupportedArchitectures")
        if not all(isinstance(value, str) and value for value in (identifier, library_path, headers_path, platform)):
            raise ManifestError(f"{label} XCFramework library metadata is incomplete")
        if not isinstance(variant, str) or not isinstance(architectures, list) or not all(
            isinstance(item, str) and item for item in architectures
        ):
            raise ManifestError(f"{label} XCFramework architecture metadata is invalid")
        variants.add((platform, variant, tuple(sorted(architectures))))
        base = f"{prefix}{identifier}/"
        native_name = base + library_path
        if native_name not in names:
            raise ManifestError(f"{label} XCFramework is missing {native_name}")
        _assert_binary_target(
            archive.read(native_name),
            target="aarch64-apple-ios",
            label=native_name,
            static_archive=True,
        )
        for required in ("notemeld_agent.h", "module.modulemap"):
            header_name = f"{base}{headers_path}/{required}"
            if header_name not in names:
                raise ManifestError(f"{label} XCFramework is missing {header_name}")
    required_variants = {
        ("ios", "", ("arm64",)),
        ("ios", "simulator", ("arm64",)),
    }
    if not required_variants <= variants:
        raise ManifestError(
            f"{label} XCFramework does not declare arm64 device and simulator slices"
        )


def _inspect_container(
    path: Path,
    *,
    kind: str,
    target: str,
    sdk_version: str,
    schema_version: str,
    binding_version: str,
    abi_contract: dict[str, object],
) -> None:
    if not zipfile.is_zipfile(path):
        raise ManifestError(f"{kind} is not a valid ZIP container: {path.name}")
    marker_name = CONTAINER_MARKERS[kind]
    with zipfile.ZipFile(path) as archive:
        file_names = [
            info.filename for info in archive.infolist() if not info.is_dir()
        ]
        names = set(file_names)
        if len(names) != len(file_names):
            raise ManifestError(f"{kind} contains duplicate ZIP members")
        for name in names:
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts:
                raise ManifestError(f"{kind} contains unsafe ZIP path: {name}")
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
            wheel_names = [name for name in names if name.endswith(".dist-info/WHEEL")]
            record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
            if not (
                len(metadata_names) == len(wheel_names) == len(record_names) == 1
            ):
                raise ManifestError(
                    "python wheel requires exactly one METADATA, WHEEL, and RECORD file"
                )
            dist_info_dirs = {
                PurePosixPath(name).parent.as_posix()
                for name in (*metadata_names, *wheel_names, *record_names)
            }
            if len(dist_info_dirs) != 1:
                raise ManifestError("python wheel dist-info files do not share one directory")
            metadata = archive.read(metadata_names[0]).decode("utf-8", errors="strict")
            if f"Version: {sdk_version}\n" not in metadata.replace("\r\n", "\n"):
                raise ManifestError("python wheel METADATA version mismatch")
            if not path.name.endswith(".whl"):
                raise ManifestError("python wheel filename must end in .whl")
            try:
                distribution_version, python_tag, abi_tag, platform_tag = path.name[
                    :-4
                ].rsplit("-", 3)
            except ValueError as error:
                raise ManifestError("python wheel filename is malformed") from error
            if not distribution_version.endswith(f"-{sdk_version}"):
                raise ManifestError("python wheel filename version mismatch")
            filename_platforms = platform_tag.split(".")
            if not filename_platforms or not all(
                _wheel_platform_matches_target(item, target)
                for item in filename_platforms
            ):
                raise ManifestError(
                    f"python wheel filename platform tag is incompatible with {target}"
                )
            wheel_metadata = archive.read(wheel_names[0]).decode(
                "utf-8", errors="strict"
            )
            declared_tags = [
                line[5:].strip()
                for line in wheel_metadata.replace("\r\n", "\n").splitlines()
                if line.startswith("Tag:")
            ]
            if not declared_tags:
                raise ManifestError("python wheel WHEEL metadata has no Tag")
            for declared_tag in declared_tags:
                parts = declared_tag.split("-", 2)
                if (
                    len(parts) != 3
                    or parts[0] not in python_tag.split(".")
                    or parts[1] not in abi_tag.split(".")
                    or not _wheel_platform_matches_target(parts[2], target)
                ):
                    raise ManifestError(
                        f"python wheel tag is incompatible with filename/target: {declared_tag}"
                    )
            _verify_wheel_record(archive, names, record_names[0])
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
            native_name = f"notemeld_agent_sdk/native/{expected_native}"
            if native_name not in names:
                raise ManifestError("python wheel is missing packaged native library")
            _assert_binary_target(
                archive.read(native_name), target=target, label=native_name
            )
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
            abi_targets = dict(zip(ANDROID_ABIS, (
                "armv7-linux-androideabi",
                "aarch64-linux-android",
                "i686-linux-android",
                "x86_64-linux-android",
            )))
            for abi, abi_target in abi_targets.items():
                for library in (
                    "libnotemeld_agent.so",
                    "libnotemeld_agent_jni.so",
                ):
                    member = f"jni/{abi}/{library}"
                    _assert_binary_target(
                        archive.read(member), target=abi_target, label=member
                    )
            if "classes.jar" not in names:
                raise ManifestError("Android AAR is missing classes.jar")
            try:
                with zipfile.ZipFile(io.BytesIO(archive.read("classes.jar"))) as classes:
                    runtime_classes = [
                        name
                        for name in classes.namelist()
                        if name.endswith("/RuntimeKt.class")
                    ]
                    if len(runtime_classes) != 1:
                        raise ManifestError(
                            "Android AAR classes.jar requires exactly one RuntimeKt.class"
                        )
                    constants = _java_constant_fields(
                        classes.read(runtime_classes[0]), runtime_classes[0]
                    )
            except zipfile.BadZipFile as error:
                raise ManifestError("Android AAR has invalid classes.jar") from error
            if constants.get("SDK_VERSION") != sdk_version:
                raise ManifestError("Android binding SDK_VERSION mismatch")
            if constants.get("SCHEMA_VERSION") != schema_version:
                raise ManifestError("Android binding SCHEMA_VERSION mismatch")
        elif kind == "swift-xcframework":
            _inspect_xcframework(
                archive,
                names,
                prefix="NoteMeldAgentNative.xcframework/",
                label="XCFramework",
            )
            inner_marker_name = (
                "NoteMeldAgentNative.xcframework/notemeld-agent-sdk.json"
            )
            inner_marker = _read_zip_json(
                archive, inner_marker_name, "XCFramework"
            )
            _verify_binding_marker(
                inner_marker,
                target=target,
                sdk_version=sdk_version,
                schema_version=schema_version,
                binding_version=binding_version,
            )
            inner_abi = _read_abi_contract_bytes(
                archive.read("NoteMeldAgentNative.xcframework/abi-v1.json"),
                label="XCFramework embedded ABI",
                sdk_version=sdk_version,
                schema_version=schema_version,
            )
            if inner_abi != abi_contract:
                raise ManifestError("XCFramework embedded ABI contract mismatch")
        elif kind == "swift-package":
            try:
                package = archive.read("Package.swift").decode("utf-8")
            except (KeyError, UnicodeDecodeError) as error:
                raise ManifestError("Swift package is missing valid Package.swift") from error
            if ".binaryTarget(" not in package or "NoteMeldAgentNative.xcframework" not in package:
                raise ManifestError("Swift package does not link its XCFramework binary target")
            _inspect_xcframework(
                archive,
                names,
                prefix="NoteMeldAgentNative.xcframework/",
                label="Swift package embedded XCFramework",
            )
            runtime_name = "Sources/NoteMeldAgentSDK/Runtime.swift"
            try:
                runtime = archive.read(runtime_name).decode("utf-8")
            except (KeyError, UnicodeDecodeError) as error:
                raise ManifestError("Swift package is missing valid Runtime.swift") from error
            if _swift_constant(
                runtime, "noteMeldAgentSdkVersion", runtime_name
            ) != sdk_version:
                raise ManifestError("Swift runtime SDK version mismatch")
            if _swift_constant(
                runtime, "noteMeldAgentSchemaVersion", runtime_name
            ) != schema_version:
                raise ManifestError("Swift runtime schema version mismatch")
            inner_marker = _read_zip_json(
                archive,
                "NoteMeldAgentNative.xcframework/notemeld-agent-sdk.json",
                "Swift package embedded XCFramework",
            )
            _verify_binding_marker(
                inner_marker,
                target=target,
                sdk_version=sdk_version,
                schema_version=schema_version,
                binding_version=binding_version,
            )
            inner_abi = _read_abi_contract_bytes(
                archive.read("NoteMeldAgentNative.xcframework/abi-v1.json"),
                label="Swift package embedded XCFramework ABI",
                sdk_version=sdk_version,
                schema_version=schema_version,
            )
            if inner_abi != abi_contract:
                raise ManifestError("Swift package embedded ABI contract mismatch")
        elif kind == "openharmony-har":
            for library in ("libnotemeld_agent.so", "libnotemeld_agent_napi.so"):
                matches = [name for name in names if name.endswith(library)]
                if len(matches) != 1:
                    raise ManifestError(f"OpenHarmony HAR is missing {library}")
                _assert_binary_target(
                    archive.read(matches[0]),
                    target="aarch64-unknown-linux-ohos",
                    label=matches[0],
                )
            source_names = [
                name
                for name in names
                if name.endswith("Index.ets") or name.endswith("index.ets")
            ]
            if len(source_names) != 1:
                raise ManifestError("OpenHarmony HAR is missing ArkTS binding")
            try:
                source = archive.read(source_names[0]).decode("utf-8")
            except UnicodeDecodeError as error:
                raise ManifestError("OpenHarmony HAR has invalid ArkTS binding") from error
            sdk_match = re.search(r"\bSDK_VERSION\s*:[^=]+\=\s*['\"]([^'\"]+)", source)
            schema_match = re.search(r"\bSCHEMA_VERSION\s*:[^=]+\=\s*['\"]([^'\"]+)", source)
            if sdk_match is None or sdk_match.group(1) != sdk_version:
                raise ManifestError("OpenHarmony binding SDK_VERSION mismatch")
            if schema_match is None or schema_match.group(1) != schema_version:
                raise ManifestError("OpenHarmony binding SCHEMA_VERSION mismatch")
            package_names = [name for name in names if name.endswith("oh-package.json5")]
            package_versions = []
            for package_name in package_names:
                package_source = archive.read(package_name).decode("utf-8", errors="strict")
                if "@notemeld/agent-sdk" in package_source:
                    match = re.search(r"\bversion\s*:\s*['\"]([^'\"]+)", package_source)
                    if match:
                        package_versions.append(match.group(1))
            if package_versions != [sdk_version]:
                raise ManifestError("OpenHarmony package version mismatch")

        abi_name = CONTAINER_ABI_CONTRACTS[kind]
        try:
            internal_abi = _read_abi_contract_bytes(
                archive.read(abi_name),
                label=f"{kind} internal ABI",
                sdk_version=sdk_version,
                schema_version=schema_version,
            )
        except KeyError as error:
            raise ManifestError(f"{kind} is missing internal ABI contract {abi_name}") from error
        if internal_abi != abi_contract:
            raise ManifestError(f"{kind} internal ABI contract mismatch")


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
            _read_abi_contract_bytes(
                path.read_bytes(),
                label=path.name,
                sdk_version=sdk_version,
                schema_version=schema_version,
            )
        except OSError as error:
            raise ManifestError(f"invalid ABI contract: {path.name}") from error
    elif kind == "c-header":
        try:
            header = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ManifestError("invalid C header") from error
        if "notemeld_agent_sdk_version" not in header:
            raise ManifestError("C header is missing Agent SDK declarations")
    elif kind in {"native-library", "static-library"}:
        try:
            _assert_binary_target(
                path.read_bytes(),
                target=target,
                label=path.name,
                static_archive=kind == "static-library",
            )
        except ManifestError as error:
            raise ManifestError(f"placeholder, invalid, or wrong architecture {kind}: {error}") from error


def _closed_world_files(root: Path) -> set[Path]:
    files: set[Path] = set()
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in directories:
            directory = current_path / name
            if directory.is_symlink():
                raise ManifestError(
                    f"artifact root contains symlink directory: "
                    f"{directory.relative_to(root).as_posix()}"
                )
        for name in filenames:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise ManifestError(f"artifact root contains symlink file: {relative}")
            if not path.is_file():
                raise ManifestError(f"artifact root contains non-regular file: {relative}")
            files.add(path.resolve())
    return files


def verify_manifests(args: argparse.Namespace) -> dict[str, object]:
    artifact_root = args.artifact_root.resolve()
    if not artifact_root.is_dir():
        raise ManifestError(f"artifact root does not exist: {artifact_root}")
    discovered_manifests = sorted(artifact_root.rglob(MANIFEST_NAME))
    manifests = []
    for manifest in discovered_manifests:
        checked_manifest, _ = _relative_artifact(
            artifact_root, manifest.relative_to(artifact_root).as_posix()
        )
        manifests.append(checked_manifest)
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
        containers_to_inspect: list[tuple[Path, str, str]] = []
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
                _verify_container_marker_only(
                    artifact,
                    kind=kind,
                    target=target,
                    sdk_version=args.sdk_version,
                    schema_version=args.schema_version,
                    binding_version=args.binding_version,
                )
                containers_to_inspect.append((artifact, kind, target))
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

        abi_path = artifacts_by_kind["abi-contract"][0]
        abi_contract = _read_abi_contract_bytes(
            abi_path.read_bytes(),
            label=abi_path.name,
            sdk_version=args.sdk_version,
            schema_version=args.schema_version,
        )
        for artifact, kind, target in containers_to_inspect:
            _inspect_container(
                artifact,
                kind=kind,
                target=target,
                sdk_version=args.sdk_version,
                schema_version=args.schema_version,
                binding_version=args.binding_version,
                abi_contract=abi_contract,
            )

        manifest_targets.add(only_target)

    missing = expected_targets - observed_targets
    if missing:
        raise ManifestError(
            "missing expected target(s): " + ", ".join(sorted(missing))
        )
    declared_files = seen_paths | set(manifests)
    actual_files = _closed_world_files(artifact_root)
    unexpected_files = actual_files - declared_files
    if unexpected_files:
        relative = sorted(
            path.relative_to(artifact_root).as_posix()
            for path in unexpected_files
        )
        raise ManifestError(
            "unmanifested payload file(s): " + ", ".join(relative)
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
