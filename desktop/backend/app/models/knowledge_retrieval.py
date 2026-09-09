from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SCHEMA_VERSION = "knowledge_result.v1"
INDEX_VERSION = "knowledge_index.v1"

CAPABILITY_IDS = (
    "knowledge:article_lookup",
    "knowledge:evidence_search",
    "knowledge:profile_search",
    "knowledge:semantic_search",
)


class KnowledgeQueryError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class KnowledgeLocation:
    page_from: int | None = None
    page_to: int | None = None
    section_path: str | None = None
    time_from: float | None = None
    time_to: float | None = None


@dataclass
class KnowledgeResult:
    layer: str
    article_id: str
    result_id: str
    title: str = ""
    text: str = ""
    location: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float | None] = field(default_factory=dict)
    source_ref: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "article_id": self.article_id,
            "result_id": self.result_id,
            "title": self.title,
            "text": self.text,
            "location": self.location,
            "scores": self.scores,
            "source_ref": self.source_ref,
            "metadata": self.metadata,
        }


def validate_article_ids(article_ids: list[str] | None) -> list[str] | None:
    if article_ids is None:
        return None
    if not isinstance(article_ids, list):
        raise KnowledgeQueryError("invalid_arguments", "article_ids must be an array")
    normalized = list(dict.fromkeys(str(item).strip() for item in article_ids if str(item).strip()))
    if not normalized:
        raise KnowledgeQueryError("invalid_arguments", "article_ids must not be empty")
    return normalized


def bounded_top_k(value: Any, default: int = 10, maximum: int = 50) -> int:
    try:
        top_k = int(value if value is not None else default)
    except (TypeError, ValueError) as exc:
        raise KnowledgeQueryError("invalid_arguments", "top_k must be an integer") from exc
    if top_k < 1 or top_k > maximum:
        raise KnowledgeQueryError("invalid_arguments", f"top_k must be between 1 and {maximum}")
    return top_k


def result_envelope(capability_id: str, results: list[KnowledgeResult | dict[str, Any]], warnings: list[str] | None = None) -> dict[str, Any]:
    serialized = [item.to_dict() if isinstance(item, KnowledgeResult) else item for item in results]
    return {
        "schema_version": SCHEMA_VERSION,
        "capability_id": capability_id,
        "total": len(serialized),
        "results": serialized,
        "warnings": list(warnings or []),
    }
