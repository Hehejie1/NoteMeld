from __future__ import annotations

import json
from pathlib import Path

from app.services.ingestion.chunker import DocumentChunker


class IngestionArtifactWriter:
    def __init__(self, output_dir: Path, document_chunker: DocumentChunker | None = None):
        self.output_dir = Path(output_dir)
        self.document_chunker = document_chunker or DocumentChunker()

    def write(self, request, parsed, stage_events: list[dict] | None = None):
        from app.services.ingestion.pipeline import IngestionResult

        stage_events = stage_events if stage_events is not None else []
        chunking = self.document_chunker.chunk(parsed, source_asset_id=request.file_url)

        self.output_dir.mkdir(parents=True, exist_ok=True)
        sidecar_path = self.output_dir / f"{request.job_id}_parsed_document.json"
        evidence_path = self.output_dir / f"{request.job_id}_evidence_anchors.json"
        chunks_path = self.output_dir / f"{request.job_id}_knowledge_chunks.json"
        materialization_path = self.output_dir / f"{request.job_id}_materialization.json"
        artifact_manifest_path = self.output_dir / f"{request.job_id}_artifacts.json"

        sidecar_path.write_text(
            json.dumps(parsed.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        evidence_path.write_text(
            json.dumps([anchor.to_dict() for anchor in chunking.anchors], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        chunks_path.write_text(
            json.dumps([chunk.to_dict() for chunk in chunking.chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        artifact_manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "ingestion_artifacts.v1",
                    "job_id": request.job_id,
                    "source": {
                        "file_url": request.file_url,
                        "file_name": request.file_name,
                        "content_type": request.content_type or "",
                        "source_type": request.source_type,
                        "resource_type": parsed.resource_type,
                    },
                    "artifacts": {
                        "parsed_document": str(sidecar_path),
                        "evidence_anchors": str(evidence_path),
                        "knowledge_chunks": str(chunks_path),
                        "materialization": str(materialization_path),
                    },
                    "parser": {
                        "name": parsed.parser_name,
                        "backend": parsed.parser_backend,
                        "version": parsed.parser_version,
                        "fallback_used": parsed.fallback_used,
                    },
                    "quality": parsed.quality,
                    "counts": {
                        "evidence_anchors": len(chunking.anchors),
                        "knowledge_chunks": len(chunking.chunks),
                    },
                    "stage_events": stage_events,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return IngestionResult(
            request=request,
            parsed_document=parsed,
            sidecar_path=str(sidecar_path),
            artifact_manifest_path=str(artifact_manifest_path),
            evidence_path=str(evidence_path),
            chunks_path=str(chunks_path),
            materialization_path=str(materialization_path),
            evidence_anchors=chunking.anchors,
            knowledge_chunks=chunking.chunks,
            stage_events=stage_events,
        )
