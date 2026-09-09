from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional


class IngestionStage(str, Enum):
    INSPECTING = "inspecting"
    COLLECTING = "collecting"
    PARSING = "parsing"
    NORMALIZING = "normalizing"
    CHUNKING = "chunking"
    INDEXING = "indexing"
    SUMMARIZING = "summarizing"
    SAVING = "saving"
    REVIEWING = "reviewing"


class IngestionJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class IngestionRequest:
    job_id: str
    file_url: str
    file_name: str
    content_type: Optional[str] = None
    model_name: Optional[str] = None
    provider_id: Optional[str] = None
    conversation_id: Optional[str] = None
    mode: str = "note"
    source_type: str = "uploaded_file"
    resource_type: str = "document"
    user_options: dict = field(default_factory=dict)


@dataclass
class TextItem:
    text: str
    page_number: int
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    font_name: Optional[str] = None
    font_size: Optional[float] = None
    confidence: float = 1.0
    source: str = "fallback"


@dataclass
class EvidenceAnchor:
    id: str
    job_id: str
    source_type: str
    source_asset_id: Optional[str] = None
    page_number: Optional[int] = None
    bbox: Optional[list[float]] = None
    timestamp_start: Optional[float] = None
    timestamp_end: Optional[float] = None
    web_selector: Optional[str] = None
    text_quote: str = ""
    screenshot_asset_id: Optional[str] = None
    confidence: float = 1.0
    granularity: str = "page"

    @classmethod
    def from_text_item(
        cls,
        job_id: str,
        source_type: str,
        item: TextItem,
        index: int,
        source_asset_id: Optional[str] = None,
        screenshot_asset_id: Optional[str] = None,
    ) -> "EvidenceAnchor":
        has_precise_box = item.x != 0 or item.y != 0 or item.width != 0 or item.height != 0
        return cls(
            id=f"{job_id}_anchor_{index}",
            job_id=job_id,
            source_type=source_type,
            source_asset_id=source_asset_id,
            page_number=item.page_number,
            bbox=[item.x, item.y, item.width, item.height],
            text_quote=item.text,
            screenshot_asset_id=screenshot_asset_id,
            confidence=item.confidence,
            granularity="text_item" if has_precise_box else "page",
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class KnowledgeChunk:
    id: str
    job_id: str
    document_id: str
    chunk_index: int
    content: str
    summary: Optional[str] = None
    anchor_ids: list[str] = field(default_factory=list)
    source_weight: float = 1.0
    confidence: float = 1.0
    embedding_status: str = "pending"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParsedPage:
    page_number: int
    text: str
    width: float = 0
    height: float = 0
    text_items: list[TextItem] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    confidence: float = 1.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    job_id: str
    title: str
    source_type: str
    resource_type: str
    parser_name: str
    pages: list[ParsedPage]
    schema_version: str = "parsed_document.v1"
    parser_version: str = "1"
    parser_backend: str = "fallback"
    fallback_used: bool = False
    language: Optional[str] = None
    quality: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(page.text.strip() for page in self.pages if page.text.strip()).strip()

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["text"] = self.text
        data["page_count"] = self.page_count
        return data
