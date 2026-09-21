from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.utils.storage_paths import note_output_dir


class IngestionArtifactError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class IngestionArtifactReader:
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir or note_output_dir())

    def manifest_path(self, task_id: str) -> Path:
        return self.output_dir / f"{task_id}_artifacts.json"

    def read_json(self, path: str | Path, artifact_name: str = "artifact", required: bool = True) -> Any:
        artifact_path = Path(path)
        if not artifact_path.exists():
            if not required:
                return None
            raise IngestionArtifactError(
                code="ingestion_artifact_missing",
                message=f"{artifact_name} artifact missing: {artifact_path}",
            )
        try:
            return json.loads(artifact_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise IngestionArtifactError(
                code="ingestion_artifact_invalid_json",
                message=f"{artifact_name} artifact has invalid JSON: {artifact_path}",
            ) from exc
        except IsADirectoryError as exc:
            raise IngestionArtifactError(
                code="ingestion_artifact_invalid_path",
                message=f"{artifact_name} artifact path is a directory: {artifact_path}",
            ) from exc

    def read_manifest(self, task_id: str) -> dict:
        return self.read_json(self.manifest_path(task_id), artifact_name="manifest")

    def read_parsed_document(self, task_id: str) -> dict:
        manifest = self.read_manifest(task_id)
        return self.read_json(manifest["artifacts"]["parsed_document"], artifact_name="parsed_document")

    def read_evidence(self, task_id: str) -> list:
        manifest = self.read_manifest(task_id)
        return self.read_json(
            manifest["artifacts"]["evidence_anchors"],
            artifact_name="evidence_anchors",
            required=False,
        ) or []

    def read_chunks(self, task_id: str) -> list:
        manifest = self.read_manifest(task_id)
        return self.read_json(
            manifest["artifacts"]["knowledge_chunks"],
            artifact_name="knowledge_chunks",
            required=False,
        ) or []

    def read_materialization(self, task_id: str) -> dict:
        manifest = self.read_manifest(task_id)
        return self.read_json(
            manifest["artifacts"]["materialization"],
            artifact_name="materialization",
            required=False,
        ) or {}

    def build_report(self, task_id: str) -> dict:
        manifest = self.read_manifest(task_id)
        artifacts = manifest.get("artifacts", {})
        parsed = self.read_json(self._required_artifact_path(artifacts, "parsed_document"), artifact_name="parsed_document")
        evidence = self.read_json(artifacts.get("evidence_anchors", ""), "evidence_anchors", required=False) or []
        chunks = self.read_json(artifacts.get("knowledge_chunks", ""), "knowledge_chunks", required=False) or []
        materialization = self.read_json(artifacts.get("materialization", ""), "materialization", required=False) or {}
        warnings = self._page_warnings(parsed)
        warnings.extend(self._missing_optional_warnings(artifacts, manifest))

        return {
            "task_id": task_id,
            "title": parsed.get("title", ""),
            "resource_type": parsed.get("resource_type", ""),
            "parser": manifest.get("parser", {}),
            "page_count": parsed.get("page_count") or len(parsed.get("pages", [])),
            "evidence_count": len(evidence),
            "chunk_count": len(chunks),
            "vector_indexed": bool(materialization.get("vector_indexed")),
            "vector_error": materialization.get("vector_error", ""),
            "quality": parsed.get("quality") or manifest.get("quality", {}),
            "artifacts": artifacts,
            "warnings": warnings,
        }

    def _required_artifact_path(self, artifacts: dict, name: str) -> str:
        path = artifacts.get(name)
        if not path:
            raise IngestionArtifactError(
                code="ingestion_artifact_invalid_schema",
                message=f"required artifact path missing: {name}",
            )
        return path

    def _page_warnings(self, parsed: dict) -> list[str]:
        warnings = []
        for page in parsed.get("pages", []):
            page_number = page.get("page_number")
            for warning in page.get("warnings", []):
                warnings.append(f"page_{page_number}:{warning}")
        return warnings

    def _missing_optional_warnings(self, artifacts: dict, manifest: dict) -> list[str]:
        warnings = []
        for artifact_name in ("evidence_anchors", "knowledge_chunks", "materialization"):
            artifact_path = artifacts.get(artifact_name)
            if not artifact_path or not Path(artifact_path).exists():
                warnings.append(f"missing_optional:{artifact_name}")
        return warnings
