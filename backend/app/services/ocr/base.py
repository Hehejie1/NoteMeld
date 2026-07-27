from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, TypedDict


class OcrPageResult(TypedDict, total=False):
    page: int
    text: str
    confidence: float


class OcrLineResult(TypedDict, total=False):
    id: str
    text: str
    bbox: list[float] | None
    order: int
    page: int
    confidence: float | None


class OcrResult(TypedDict):
    text: str
    engine: str
    confidence: Optional[float]
    pages: list[OcrPageResult]
    lines: list[OcrLineResult]


class OcrProvider(Protocol):
    def extract_text(self, file_path: Path) -> OcrResult:
        ...
