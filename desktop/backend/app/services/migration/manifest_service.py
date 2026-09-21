from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MigrationManifestError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class MigrationManifestService:
    SCHEMA_VERSION = "migration_manifest.v1"

    def manifest_path(self, package_dir: str | Path) -> Path:
        return Path(package_dir) / "manifest.json"

    def build_manifest(
        self,
        package_id: str,
        operation: str,
        app_version: str,
        counts: dict[str, int] | None = None,
        includes: dict[str, bool] | None = None,
        warnings: list[str] | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        if not package_id:
            raise MigrationManifestError(
                code="migration_manifest_invalid_schema",
                message="package_id is required",
            )
        if not operation:
            raise MigrationManifestError(
                code="migration_manifest_invalid_schema",
                message="operation is required",
            )

        return {
            "schema_version": self.SCHEMA_VERSION,
            "package_id": package_id,
            "operation": operation,
            "app_version": app_version or "",
            "created_at": created_at or self._now(),
            "counts": dict(counts or {}),
            "includes": dict(includes or {}),
            "warnings": list(warnings or []),
        }

    def write_manifest(self, package_dir: str | Path, manifest: dict[str, Any]) -> Path:
        payload = self.validate_manifest(manifest)
        manifest_path = self.manifest_path(package_dir)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write_json(manifest_path, payload)
        return manifest_path

    def read_manifest(self, package_dir: str | Path) -> dict[str, Any]:
        manifest_path = self.manifest_path(package_dir)
        if not manifest_path.exists():
            raise MigrationManifestError(
                code="migration_manifest_missing",
                message=f"manifest missing: {manifest_path}",
            )
        return self._load_json(manifest_path)

    def validate_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(manifest, dict):
            raise MigrationManifestError(
                code="migration_manifest_invalid_schema",
                message="manifest payload must be a JSON object",
            )

        schema_version = str(manifest.get("schema_version") or "")
        if schema_version != self.SCHEMA_VERSION:
            raise MigrationManifestError(
                code="migration_manifest_unsupported_schema",
                message=f"unsupported manifest schema: {schema_version or '<empty>'}",
            )

        package_id = str(manifest.get("package_id") or "").strip()
        operation = str(manifest.get("operation") or "").strip()
        created_at = str(manifest.get("created_at") or "").strip()
        if not package_id or not operation or not created_at:
            raise MigrationManifestError(
                code="migration_manifest_invalid_schema",
                message="manifest missing required fields",
            )

        counts = manifest.get("counts") or {}
        includes = manifest.get("includes") or {}
        warnings = manifest.get("warnings") or []
        if not isinstance(counts, dict) or not isinstance(includes, dict) or not isinstance(warnings, list):
            raise MigrationManifestError(
                code="migration_manifest_invalid_schema",
                message="counts/includes/warnings must use dict/dict/list types",
            )

        return {
            "schema_version": self.SCHEMA_VERSION,
            "package_id": package_id,
            "operation": operation,
            "app_version": str(manifest.get("app_version") or ""),
            "created_at": created_at,
            "counts": counts,
            "includes": includes,
            "warnings": [str(item) for item in warnings],
        }

    def _load_json(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise MigrationManifestError(
                code="migration_manifest_invalid_json",
                message=f"manifest contains invalid JSON: {path}",
            ) from exc

        if not isinstance(payload, dict):
            raise MigrationManifestError(
                code="migration_manifest_invalid_schema",
                message="manifest payload must be a JSON object",
            )
        return payload

    def _atomic_write_json(self, path: Path, payload: dict[str, Any]) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
