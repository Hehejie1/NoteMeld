from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.services.ingestion.artifact_reader import IngestionArtifactReader
from app.utils.storage_paths import note_output_dir


class IngestionSourceAssetReader:
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir or note_output_dir())
        self.artifacts = IngestionArtifactReader(output_dir=self.output_dir)

    def read_source(self, task_id: str) -> dict:
        manifest = self.artifacts.read_manifest(task_id)
        source = manifest.get("source", {})
        return {
            "task_id": task_id,
            "file_url": source.get("file_url", ""),
            "file_name": source.get("file_name", ""),
            "content_type": source.get("content_type", ""),
            "resource_type": source.get("resource_type", ""),
        }
