from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CollectorResult:
    source: str
    status: str
    content: str = ""
    confidence: float = 0.0
    error: Optional[str] = None
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class WebSearchResult(CollectorResult):
    sources: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FrameContextResult(CollectorResult):
    mode: str = "disabled"
    frames: list[dict[str, Any]] = field(default_factory=list)
    grid_images: list[str] = field(default_factory=list)


@dataclass
class TranscriptContextResult(CollectorResult):
    mode: str = "disabled"
    transcript: Any | None = None
    audio_meta: Any | None = None


@dataclass
class MultiSourceSummaryBundle:
    task_id: str
    source_url: str
    platform: str
    title: str
    audio_meta: Any | None
    transcript: Any | None
    web_search: WebSearchResult
    frame_context: FrameContextResult
