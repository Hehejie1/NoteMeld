from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.models.summary_input import DocumentContext
from app.services.ingestion.artifact_writer import IngestionArtifactWriter
from app.services.ingestion.chunker import DocumentChunker
from app.services.ingestion.document_parser import DocumentParser
from app.services.ingestion.job_store import IngestionJobStore
from app.services.ingestion.types import EvidenceAnchor, IngestionRequest, IngestionStage, KnowledgeChunk, ParsedDocument
from app.utils.storage_paths import note_output_dir


@dataclass
class IngestionResult:
    request: IngestionRequest
    parsed_document: ParsedDocument
    sidecar_path: str
    artifact_manifest_path: str
    evidence_path: str
    chunks_path: str
    materialization_path: str
    evidence_anchors: list[EvidenceAnchor] = field(default_factory=list)
    knowledge_chunks: list[KnowledgeChunk] = field(default_factory=list)
    stage_events: list[dict] = field(default_factory=list)

    def to_document_context(self) -> DocumentContext:
        return DocumentContext(
            title=self.parsed_document.title,
            parser_name=self.parsed_document.parser_name,
            parser_backend=self.parsed_document.parser_backend,
            fallback_used=self.parsed_document.fallback_used,
            page_count=self.parsed_document.page_count,
            text=self.parsed_document.text,
            resource_type=self.parsed_document.resource_type,
            source_url=self.request.file_url,
            evidence_count=len(self.evidence_anchors),
            chunk_count=len(self.knowledge_chunks),
            raw_json_path=self.sidecar_path,
            quality=self.parsed_document.quality,
            pages=[
                {
                    "page_number": page.page_number,
                    "text": page.text,
                    "confidence": page.confidence,
                    "warnings": page.warnings,
                }
                for page in self.parsed_document.pages
            ],
        )


class IngestionPipeline:
    def __init__(
        self,
        document_parser: Optional[DocumentParser] = None,
        output_dir: Optional[Path] = None,
        document_chunker: Optional[DocumentChunker] = None,
    ):
        self.document_parser = document_parser or DocumentParser()
        self.output_dir = Path(output_dir or note_output_dir())
        self.document_chunker = document_chunker or DocumentChunker()
        self.job_store = IngestionJobStore(output_dir=self.output_dir)

    def run_document(self, request: IngestionRequest) -> IngestionResult:
        stage_events: list[dict] = []

        try:
            self._record(stage_events, request.job_id, IngestionStage.INSPECTING, 5, "识别文档来源")
            self._record(stage_events, request.job_id, IngestionStage.COLLECTING, 15, "读取上传文件")
            self._record(stage_events, request.job_id, IngestionStage.PARSING, 45, "解析文档内容")
            parsed = self.document_parser.parse(request)
            self._record(stage_events, request.job_id, IngestionStage.NORMALIZING, 65, "生成标准文档结构")
            self._record(stage_events, request.job_id, IngestionStage.CHUNKING, 72, "生成证据锚点与知识块")
            result = IngestionArtifactWriter(
                output_dir=self.output_dir,
                document_chunker=self.document_chunker,
            ).write(request, parsed, stage_events)
            self._record(stage_events, request.job_id, IngestionStage.SAVING, 90, "保存解析结果")
            self.job_store.mark_completed(request.job_id)

            return result
        except Exception as exc:
            self.job_store.mark_failed(request.job_id, str(exc))
            raise

    def _record(self, events: list[dict], job_id: str, stage: IngestionStage, progress: int, message: str):
        events.append({"stage": stage.value, "progress": progress, "message": message})
        self.job_store.write_event(job_id, stage.value, progress, message)
