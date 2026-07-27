from __future__ import annotations

import json
from pathlib import Path

from app.services.ingestion.artifact_writer import IngestionArtifactWriter
from app.services.ingestion.types import EvidenceAnchor, IngestionRequest, KnowledgeChunk, ParsedDocument, ParsedPage
from app.utils.storage_paths import note_output_dir


class TranscriptIngestionAdapter:
    def __init__(self, output_dir: Path | None = None):
        self.output_dir = Path(output_dir or note_output_dir())

    def ingest(self, task_id: str, source_url: str, title: str, segments: list[dict]):
        text = "\n".join(
            f"[{float(segment.get('start') or 0):.0f}s] {segment.get('text', '')}"
            for segment in segments
            if str(segment.get("text") or "").strip()
        )
        request = IngestionRequest(
            job_id=task_id,
            file_url=source_url,
            file_name=title,
            source_type="video",
            resource_type="video",
            content_type="application/json",
        )
        parsed = ParsedDocument(
            job_id=task_id,
            title=title or "视频转录",
            source_type="video",
            resource_type="video",
            parser_name="transcript_segments",
            parser_backend="transcript_segments",
            pages=[
                ParsedPage(
                    page_number=1,
                    text=text,
                    confidence=1.0 if text.strip() else 0.0,
                    warnings=[] if text.strip() else ["empty_transcript"],
                )
            ],
            quality={"segment_count": len(segments), "text_length": len(text)},
            metadata={"source_url": source_url},
        )
        result = IngestionArtifactWriter(output_dir=self.output_dir).write(request, parsed)

        anchors = self._anchors(task_id, source_url, segments)
        chunks = self._chunks(task_id, text, anchors) if text.strip() else []

        Path(result.evidence_path).write_text(
            json.dumps([anchor.to_dict() for anchor in anchors], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        Path(result.chunks_path).write_text(
            json.dumps([chunk.to_dict() for chunk in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._update_manifest_counts(result.artifact_manifest_path, anchors, chunks)
        result.evidence_anchors = anchors
        result.knowledge_chunks = chunks
        return result

    def _anchors(self, task_id: str, source_url: str, segments: list[dict]) -> list[EvidenceAnchor]:
        anchors: list[EvidenceAnchor] = []
        for index, segment in enumerate(segments):
            quote = str(segment.get("text") or "").strip()
            if not quote:
                continue
            start = float(segment.get("start") or 0)
            anchors.append(
                EvidenceAnchor(
                    id=f"{task_id}_anchor_{index}",
                    job_id=task_id,
                    source_type="video",
                    source_asset_id=source_url,
                    timestamp_start=start,
                    timestamp_end=float(segment.get("end") or start),
                    text_quote=quote,
                    confidence=1.0,
                    granularity="transcript_segment",
                )
            )
        return anchors

    def _chunks(self, task_id: str, text: str, anchors: list[EvidenceAnchor]) -> list[KnowledgeChunk]:
        return [
            KnowledgeChunk(
                id=f"{task_id}_chunk_0",
                job_id=task_id,
                document_id=task_id,
                chunk_index=0,
                content=text,
                anchor_ids=[anchor.id for anchor in anchors],
                metadata={
                    "source_type": "document",
                    "resource_type": "video",
                    "parser_name": "transcript_segments",
                    "parser_backend": "transcript_segments",
                },
            )
        ]

    def _update_manifest_counts(self, manifest_path: str, anchors: list[EvidenceAnchor], chunks: list[KnowledgeChunk]) -> None:
        path = Path(manifest_path)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["counts"] = {
            "evidence_anchors": len(anchors),
            "knowledge_chunks": len(chunks),
        }
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
