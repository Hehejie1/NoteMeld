"""N01 product-side seam for the SDK Note contract.

This module intentionally contains no SDK imports and no persistence writes.
N02 owns the concrete adapter; this file freezes the product mapping only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, NewType, Protocol, Sequence

NoteId = NewType("NoteId", str)


def note_id_from_task_id(task_id: str) -> NoteId:
    value = str(task_id or "").strip()
    if not value:
        raise ValueError("NoteId requires note_documents.task_id")
    return NoteId(value)


@dataclass(frozen=True)
class NoteAuthority:
    authority_table: str = "note_documents"
    authority_id_column: str = "task_id"
    content_columns: tuple[str, ...] = ("title", "content", "source_url", "platform", "status")
    projections: tuple[str, ...] = (
        "note_results", "conversation_messages", "wiki", "chroma"
    )


@dataclass(frozen=True)
class SdkNoteDto:
    """Stable DTO seam; the Rust SDK remains the canonical domain model."""

    note_id: NoteId
    title: str
    content: str
    content_format: str = "markdown"
    source_url: str = ""
    platform: str = ""
    version: int = 1

    @classmethod
    def from_note_document(cls, document: Mapping[str, object]) -> "SdkNoteDto":
        task_id = document.get("task_id", document.get("taskId", ""))
        return cls(
            note_id=note_id_from_task_id(str(task_id)),
            title=str(document.get("title") or ""),
            content=str(document.get("content") or ""),
            content_format=str(document.get("content_format") or "markdown"),
            source_url=str(document.get("source_url", document.get("sourceUrl", "")) or ""),
            platform=str(document.get("platform") or ""),
            version=int(document.get("version") or 1),
        )


class NoteSdkAdapter(Protocol):
    """N02 adapter surface; implementations must delegate to the fixed SDK."""

    def read(self, note_id: NoteId) -> SdkNoteDto | None: ...
    def search(self, query: str, limit: int = 10) -> Sequence[SdkNoteDto]: ...
    def create(self, note: SdkNoteDto, request_id: str) -> SdkNoteDto: ...
    def update(self, note: SdkNoteDto, request_id: str, expected_version: int) -> SdkNoteDto: ...
    def link(self, source: NoteId, target: NoteId, request_id: str) -> object: ...
