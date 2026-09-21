from __future__ import annotations

from dataclasses import dataclass, field

from app.services.ingestion.types import EvidenceAnchor, KnowledgeChunk, ParsedDocument, TextItem


@dataclass
class ChunkingResult:
    anchors: list[EvidenceAnchor] = field(default_factory=list)
    chunks: list[KnowledgeChunk] = field(default_factory=list)


class DocumentChunker:
    def __init__(self, max_chunk_chars: int = 1800):
        self.max_chunk_chars = max_chunk_chars

    def chunk(self, parsed: ParsedDocument, source_asset_id: str | None = None) -> ChunkingResult:
        anchors: list[EvidenceAnchor] = []
        chunks: list[KnowledgeChunk] = []
        anchor_index = 0

        for page in parsed.pages:
            page_anchor_ids: list[str] = []
            text_items = page.text_items or [
                TextItem(
                    text=page.text,
                    page_number=page.page_number,
                    width=page.width,
                    height=page.height,
                    confidence=page.confidence,
                    source=parsed.parser_name,
                )
            ]
            for item in text_items:
                if not item.text.strip():
                    continue
                anchor = EvidenceAnchor.from_text_item(
                    job_id=parsed.job_id,
                    source_type=parsed.resource_type,
                    source_asset_id=source_asset_id,
                    item=item,
                    index=anchor_index,
                )
                anchors.append(anchor)
                page_anchor_ids.append(anchor.id)
                anchor_index += 1

            if not page.text.strip():
                continue
            for chunk_text in self._split_page_text(page.text):
                chunk_index = len(chunks)
                chunks.append(
                    KnowledgeChunk(
                        id=f"{parsed.job_id}_chunk_{chunk_index}",
                        job_id=parsed.job_id,
                        document_id=parsed.job_id,
                        chunk_index=chunk_index,
                        content=chunk_text,
                        anchor_ids=page_anchor_ids,
                        source_weight=1.0,
                        confidence=page.confidence,
                        metadata={
                            "source_type": "document",
                            "resource_type": parsed.resource_type,
                            "page_number": page.page_number,
                            "parser_name": parsed.parser_name,
                            "parser_backend": parsed.parser_backend,
                        },
                    )
                )

        return ChunkingResult(anchors=anchors, chunks=chunks)

    def _split_page_text(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        if len(text) <= self.max_chunk_chars:
            return [text]

        chunks: list[str] = []
        current = ""
        paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
        for paragraph in paragraphs:
            if not current:
                current = paragraph
                continue
            candidate = f"{current}\n\n{paragraph}"
            if len(candidate) <= self.max_chunk_chars:
                current = candidate
            else:
                chunks.append(current)
                current = paragraph
        if current:
            chunks.append(current)
        return chunks or [text]
