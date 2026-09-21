#!/usr/bin/env python3
"""Generate an immutable Cloud/macOS x64/Android RC manifest from a PASS ledger."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


REQUIRED_ARTIFACTS = {
    "cloud-image",
    "macos-x86_64-dmg",
    "android-apk",
    "sdk-aar",
    "sdk-wheel-x86_64",
    "ui-web",
    "android-ui-core",
}


class ManifestError(RuntimeError):
    pass


def _load_ledger_tool():
    path = Path(__file__).with_name("verify-release-ledger.py")
    spec = importlib.util.spec_from_file_location("verify_release_ledger", path)
    if spec is None or spec.loader is None:
        raise ManifestError("release ledger verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_artifact(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or not raw_path or name in result:
            raise ManifestError("artifacts must use unique NAME=PATH arguments")
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise ManifestError(f"artifact {name} is not a file: {path}")
        result[name] = path
    missing = sorted(REQUIRED_ARTIFACTS - set(result))
    if missing:
        raise ManifestError(f"required RC artifacts are missing: {missing}")
    return result


def generate_manifest(
    ledger_path: Path,
    output: Path,
    artifacts: list[str],
    *,
    sdk_commit: str,
    abi_version: str,
    schema_version: str,
    protocol_version: str,
    config_sync_version: str,
    ui_contract_version: str,
) -> dict[str, Any]:
    ledger_tool = _load_ledger_tool()
    try:
        ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
        approval = ledger_tool.verify(ledger_data, ledger_path.parent)
    except (OSError, json.JSONDecodeError, ledger_tool.LedgerError) as exc:
        raise ManifestError(f"56-gate release ledger is not approved: {exc}") from exc
    artifact_paths = _parse_artifact(artifacts)
    if not isinstance(sdk_commit, str) or len(sdk_commit) != 40 or any(c not in "0123456789abcdef" for c in sdk_commit):
        raise ManifestError("SDK commit must be a lowercase full SHA")
    records = {
        name: {"filename": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path)}
        for name, path in sorted(artifact_paths.items())
    }
    manifest = {
        "manifest_schema": "notemeld.release-manifest.v1",
        "rc_version": approval["rc_version"],
        "rc_commit": approval["rc_commit"],
        "sdk_commit": sdk_commit,
        "versions": {
            "abi": abi_version,
            "schema": schema_version,
            "protocol": protocol_version,
            "config_sync": config_sync_version,
            "ui_contract": ui_contract_version,
        },
        "ledger": {
            "schema": approval["verification_schema"],
            "gate_count": approval["required"],
            "sha256": _sha256(ledger_path),
        },
        "artifacts": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--sdk-commit", required=True)
    parser.add_argument("--abi-version", required=True)
    parser.add_argument("--schema-version", required=True)
    parser.add_argument("--protocol-version", required=True)
    parser.add_argument("--config-sync-version", required=True)
    parser.add_argument("--ui-contract-version", required=True)
    args = parser.parse_args()
    try:
        manifest = generate_manifest(
            args.ledger,
            args.output,
            args.artifact,
            sdk_commit=args.sdk_commit,
            abi_version=args.abi_version,
            schema_version=args.schema_version,
            protocol_version=args.protocol_version,
            config_sync_version=args.config_sync_version,
            ui_contract_version=args.ui_contract_version,
        )
    except (ManifestError, OSError):
        parser.error("unable to generate a verified release manifest")
    print(json.dumps({"manifest_schema": manifest["manifest_schema"], "rc_version": manifest["rc_version"], "rc_commit": manifest["rc_commit"], "artifacts": len(manifest["artifacts"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
