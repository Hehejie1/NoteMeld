from __future__ import annotations

from typing import Any


def _select_strategy(source_type: str, doc_type: str, complexity_level: str) -> str:
    if source_type == "image":
        if doc_type in {"poster", "slide"} or complexity_level == "complex":
            return "image_visual_specialized"
        return "image_generic_vlm"
    if source_type == "markdown":
        return "deterministic_markdown"
    if source_type == "html":
        return "dom_structured_html"
    if source_type == "pdf":
        return "pdf_structured_parse"
    if source_type == "docx":
        return "ooxml_structured_docx"
    return "generic_document_parse"


def build_intent_router_result(
    source_type: str,
    doc_type: str,
    block_count: int,
    warning_count: int,
    renderer_profile: str,
) -> dict[str, Any]:
    complexity_level = "complex" if block_count >= 8 or warning_count >= 2 else "simple"
    expected_risk = "high" if warning_count >= 3 else "medium" if warning_count else "low"
    confidence = 0.9
    if complexity_level == "complex":
        confidence -= 0.08
    if warning_count:
        confidence -= min(0.2, warning_count * 0.04)

    return {
        "doc_type": doc_type or "mixed",
        "complexity_level": complexity_level,
        "strategy": _select_strategy(source_type, doc_type or "mixed", complexity_level),
        "needs_specialized_path": complexity_level == "complex" or (doc_type or "") in {"poster", "slide"},
        "expected_risk": expected_risk,
        "recommended_renderer_profile": renderer_profile or "generic_document",
        "confidence": round(max(0.55, min(0.98, confidence)), 2),
        "warnings": [],
    }
