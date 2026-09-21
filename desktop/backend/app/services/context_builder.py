from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.services.query_intent import QueryIntent


SOURCE_LABELS = {
    "note_meta": "视频信息",
    "note_markdown": "当前笔记",
    "note_transcript": "字幕片段",
    "wiki_entity": "Wiki 实体",
    "wiki_concept": "Wiki 概念",
    "wiki_claim": "Wiki 观点",
    "wiki_evidence": "Wiki 证据",
    "wiki_relation": "Wiki 关系",
}


@dataclass
class ContextBlock:
    block_id: str
    source_type: str
    title: str
    content: str
    score: float
    metadata: dict[str, Any]


@dataclass
class QueryContext:
    context_text: str
    sources: list[dict[str, Any]]
    blocks: list[ContextBlock]


def _stable_id(source_type: str, content: str) -> str:
    digest = hashlib.sha1(f"{source_type}:{content}".encode("utf-8")).hexdigest()[:12]
    return f"{source_type}-{digest}"


def _score_from_distance(distance: Any) -> float:
    if distance is None:
        return 0.5
    try:
        return max(0.0, 1.0 - float(distance))
    except Exception:
        return 0.5


def _note_source_type(raw_type: str) -> str:
    if raw_type == "meta":
        return "note_meta"
    if raw_type == "transcript":
        return "note_transcript"
    return "note_markdown"


def _note_title(source_type: str, metadata: dict[str, Any]) -> str:
    if source_type == "note_meta":
        return "视频信息"
    if source_type == "note_transcript":
        start = metadata.get("start_time")
        end = metadata.get("end_time")
        if start is not None and end is not None:
            return f"字幕片段 {int(float(start))}s-{int(float(end))}s"
        return "字幕片段"
    return str(metadata.get("section_title") or "当前笔记")


def _blocks_from_note_chunks(note_chunks: list[dict[str, Any]]) -> list[ContextBlock]:
    blocks: list[ContextBlock] = []
    for chunk in note_chunks or []:
        content = str(chunk.get("text") or "").strip()
        if not content:
            continue
        metadata = dict(chunk.get("metadata") or {})
        source_type = _note_source_type(str(metadata.get("source_type") or "markdown"))
        blocks.append(ContextBlock(
            block_id=_stable_id(source_type, content),
            source_type=source_type,
            title=_note_title(source_type, metadata),
            content=content,
            score=_score_from_distance(chunk.get("distance")),
            metadata=metadata,
        ))
    return blocks


def _blocks_from_wiki_sources(wiki_sources: list[dict[str, Any]]) -> list[ContextBlock]:
    blocks: list[ContextBlock] = []
    for source in wiki_sources or []:
        source_type = str(source.get("type") or source.get("source_type") or "wiki_claim")
        content = str(source.get("snippet") or source.get("text") or source.get("content") or "").strip()
        if not content:
            continue
        blocks.append(ContextBlock(
            block_id=str(source.get("id") or _stable_id(source_type, content)),
            source_type=source_type,
            title=str(source.get("title") or SOURCE_LABELS.get(source_type, "Wiki 来源")),
            content=content,
            score=float(source.get("score") or 0.0),
            metadata=dict(source.get("metadata") or {}),
        ))
    return blocks


def _dedupe_blocks(blocks: list[ContextBlock]) -> list[ContextBlock]:
    seen: set[str] = set()
    unique: list[ContextBlock] = []
    for block in sorted(blocks, key=lambda item: item.score, reverse=True):
        key = " ".join(block.content.split())[:300]
        if key in seen:
            continue
        seen.add(key)
        unique.append(block)
    return unique


def _format_context(blocks: list[ContextBlock], max_chars: int = 9000) -> str:
    if not blocks:
        return "（未检索到相关上下文）"
    parts: list[str] = []
    used = 0
    for block in blocks:
        label = SOURCE_LABELS.get(block.source_type, "参考来源")
        part = f"[{label} / {block.title} / score={block.score:.2f}]\n{block.content}"
        if used + len(part) > max_chars:
            break
        parts.append(part)
        used += len(part)
    return "\n\n".join(parts) if parts else "（未检索到相关上下文）"


def _to_sources(blocks: list[ContextBlock]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for block in blocks:
        sources.append({
            "id": block.block_id,
            "type": block.source_type,
            "source_type": block.source_type,
            "title": block.title,
            "snippet": block.content[:500],
            "text": block.content[:500],
            "score": block.score,
            "metadata": block.metadata,
        })
    return sources


def build_query_context(
    question: str,
    intent: QueryIntent,
    note_chunks: list[dict[str, Any]],
    wiki_sources: list[dict[str, Any]],
) -> QueryContext:
    blocks = _blocks_from_note_chunks(note_chunks) + _blocks_from_wiki_sources(wiki_sources)
    unique = _dedupe_blocks(blocks)[:12]
    return QueryContext(
        context_text=_format_context(unique),
        sources=_to_sources(unique),
        blocks=unique,
    )
