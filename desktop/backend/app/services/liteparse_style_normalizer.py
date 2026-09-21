from __future__ import annotations

import re
from typing import Any


def normalize_text_items_to_analysis(
    *,
    source_type: str,
    file_name: str,
    text_items: list[dict[str, Any]],
    page_count: int = 1,
    page_sizes: list[dict[str, Any]] | None = None,
    preprocess: dict[str, Any] | None = None,
    parser_backend: str,
) -> dict[str, Any]:
    normalized_items = [_normalize_item(item) for item in text_items if str(item.get("text") or "").strip()]
    ordered_items = sorted(
        normalized_items,
        key=lambda item: (
            item["page_number"],
            _column_bucket(item),
            item["y"],
            item["x"],
        ),
    )
    blocks = [_item_to_block(item, index, source_type) for index, item in enumerate(ordered_items)]
    text = "\n\n".join(block["text"] for block in blocks if block.get("text")).strip()
    doc_type = _infer_doc_type(blocks)
    renderer_profile = _select_renderer_profile(doc_type)

    return {
        "text": text,
        "structure": {
            "doc_type": doc_type,
            "layout": _build_layout(ordered_items, page_sizes or []),
            "blocks": blocks,
        },
        "typed_semantics": {
            "renderer_profile": renderer_profile,
            "semantic_blocks": [
                {
                    "block_id": block["id"],
                    "semantic_role": _semantic_role(doc_type, block["block_type"]),
                    "semantic_hint": block.get("text_summary") or block.get("text") or "",
                }
                for block in blocks
            ],
        },
        "template_schema": {
            "version": "v1",
            "doc_type": doc_type,
            "renderer_profile": renderer_profile,
            "layout": _build_layout(ordered_items, page_sizes or []),
            "blocks": [{"type": block["block_type"]} for block in blocks],
        },
        "source": {
            "file_name": file_name,
            "source_type": source_type,
            "parser_backend": parser_backend,
            "page_count": page_count,
            "page_sizes": page_sizes or [],
            "text_item_count": len(ordered_items),
        },
        "preprocess": preprocess or {},
    }


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    bbox = item.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        x = _to_float(bbox[0])
        y = _to_float(bbox[1])
        width = _to_float(bbox[2])
        height = _to_float(bbox[3])
    else:
        x = _to_float(item.get("x"))
        y = _to_float(item.get("y"))
        width = _to_float(item.get("width"))
        height = _to_float(item.get("height"))
    page_number = int(item.get("page_number") or item.get("page") or 1)
    return {
        "text": str(item.get("text") or "").strip(),
        "page_number": page_number,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "bbox": [x, y, width, height],
        "font_size": _to_float(item.get("font_size")),
        "confidence": item.get("confidence"),
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
    }


def _item_to_block(item: dict[str, Any], index: int, source_type: str) -> dict[str, Any]:
    block_type = _classify_block(item, index)
    text = item["text"]
    return {
        "id": f"{source_type}-p{item['page_number']}-b{index + 1}",
        "block_type": block_type,
        "text": text,
        "text_summary": text[:120],
        "bbox": item["bbox"],
        "page_number": item["page_number"],
        "reading_order": index,
        "confidence": item["confidence"] if item["confidence"] is not None else 1.0,
        "metadata": {
            **item["metadata"],
            "font_size": item["font_size"] or None,
        },
    }


def _classify_block(item: dict[str, Any], index: int) -> str:
    text = item["text"]
    if index == 0:
        return "page_title"
    if re.match(r"^([-*+•])\s+.+$", text) or re.match(r"^\d+[.)]\s+.+$", text):
        return "bullet_list"
    font_size = float(item.get("font_size") or 0)
    if font_size >= 15 and len(text) <= 80:
        return "heading"
    if "\t" in text or re.search(r"\s{3,}", text):
        return "table"
    return "paragraph"


def _build_layout(items: list[dict[str, Any]], page_sizes: list[dict[str, Any]]) -> dict[str, Any]:
    columns = _estimate_columns(items, page_sizes)
    layout_type = "two-column" if columns >= 2 else "single-column"
    return {
        "columns": columns,
        "layout_type": layout_type,
        "reading_order": "top-to-bottom",
    }


def _estimate_columns(items: list[dict[str, Any]], page_sizes: list[dict[str, Any]]) -> int:
    if len(items) < 4:
        return 1
    first_page_width = _to_float((page_sizes[0] or {}).get("width")) if page_sizes else 0
    if first_page_width <= 0:
        return 1
    left_count = sum(1 for item in items if item["x"] < first_page_width * 0.45)
    right_count = sum(1 for item in items if item["x"] > first_page_width * 0.55)
    return 2 if left_count >= 2 and right_count >= 2 else 1


def _column_bucket(item: dict[str, Any]) -> int:
    return 0 if item["x"] < 360 else 1


def _infer_doc_type(blocks: list[dict[str, Any]]) -> str:
    if any(block["block_type"] in {"heading", "bullet_list"} for block in blocks):
        return "note"
    return "document"


def _select_renderer_profile(doc_type: str) -> str:
    return "note_structured" if doc_type == "note" else "generic_document"


def _semantic_role(doc_type: str, block_type: str) -> str:
    if block_type == "page_title":
        return "title"
    if block_type == "heading":
        return "notes_section" if doc_type == "note" else "section_heading"
    if block_type == "bullet_list":
        return "checklist" if doc_type == "note" else "list"
    return "content"


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
