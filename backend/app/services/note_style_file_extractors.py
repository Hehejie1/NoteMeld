from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import html
import os
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from app.services.note_style_format_adapters import (
    extract_from_docx_adapter,
    extract_from_html_adapter,
    extract_from_markdown_adapter,
    extract_from_pdf_adapter,
)
from app.services.liteparse_style_normalizer import normalize_text_items_to_analysis
from app.services.note_style_followup_prompts import build_followup_prompts
from app.services.note_style_image_vlm_analyzer import (
    analyze_image_with_vlm,
    analyze_typed_semantics_with_vlm,
    validate_rendered_template_with_vlm,
)
from app.services.note_style_intent_router import build_intent_router_result
from app.services.note_style_image_preprocessor import build_image_preprocess_metadata
from app.services.note_style_import_service import extract_template_from_text
from app.services.note_style_schema import NoteStylePayload
from app.utils.storage_paths import upload_dir


TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".csv", ".json", ".xml"}
HTML_EXTENSIONS = {".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx"}
PDF_CONTENT_TYPES = {"application/pdf"}
DOCX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
RESUME_SECTION_HEADINGS = {
    "个人优势",
    "个人简介",
    "个人概况",
    "核心技能",
    "专业技能",
    "工作经历",
    "项目经历",
    "教育经历",
    "自我评价",
    "校园经历",
    "获奖经历",
}
RESUME_SIDEBAR_HEADINGS = {
    "个人优势",
    "个人简介",
    "个人概况",
    "核心技能",
    "专业技能",
    "自我评价",
}
RESUME_TIMELINE_HEADINGS = {
    "工作经历",
    "项目经历",
    "教育经历",
    "校园经历",
    "获奖经历",
}


class _SkeletonHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "iframe"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        allowed_attrs: list[str] = []
        for key, value in attrs:
            if key == "class" or key == "id" or key.startswith("data-") or key in {"role", "aria-label"}:
                escaped = html.escape(value or "", quote=True)
                allowed_attrs.append(f'{key}="{escaped}"')
        attr_text = (" " + " ".join(allowed_attrs)) if allowed_attrs else ""
        self.parts.append(f"<{tag}{attr_text}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "iframe"}:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag not in {"br", "img", "input", "meta", "link"}:
            self.parts.append(f"</{tag}>")


def sanitize_html_to_skeleton(raw_html: str) -> str:
    parser = _SkeletonHTMLParser()
    parser.feed(raw_html or "")
    skeleton = "".join(parser.parts).strip()
    return skeleton or '<article class="imported-note-template"><section class="note-body" data-slot="body"></section></article>'


def _read_text(path: str) -> str:
    data = Path(path).read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _markdown_skeleton(text: str) -> str:
    return extract_template_from_text(text, "imported.md")["skeleton_html"]


def _normalize_resume_lines(text: str) -> list[str]:
    return [line.strip() for line in re.split(r"[\r\n]+", text or "") if line.strip()]


def _safe_resume_class_name(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", raw).strip("-").lower() or "section"


def _looks_like_resume(lines: list[str]) -> bool:
    if not lines:
        return False
    score = 0
    if any(line in RESUME_SECTION_HEADINGS for line in lines):
        score += 2
    if any("@" in line or "电话" in line or "求职意向" in line or "工作经验" in line for line in lines[:5]):
        score += 1
    if any(re.search(r"\d{4}[./-]\d{2}", line) for line in lines):
        score += 1
    return score >= 2


def _is_probable_section_heading(line: str) -> bool:
    if line in RESUME_SECTION_HEADINGS:
        return True
    if len(line) > 12:
        return False
    if any(token in line for token in {"：", ":", "@", "|", "http", "www"}):
        return False
    return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9\s/+-]{2,12}", line))


def _split_resume_blocks(lines: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    header_lines: list[str] = []
    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None

    for line in lines:
        if _is_probable_section_heading(line):
            if current_section:
                sections.append(current_section)
            current_section = {"title": line, "lines": []}
            continue
        if current_section is None:
            header_lines.append(line)
        else:
            current_section["lines"].append(line)

    if current_section:
        sections.append(current_section)

    return header_lines, sections


def _classify_resume_section_region(title: str) -> str:
    if title in RESUME_SIDEBAR_HEADINGS:
        return "sidebar"
    return "main"


def _build_image_ocr_analysis(text: str, ocr_result: dict[str, Any]) -> dict[str, Any]:
    lines = ocr_result.get("lines") or []
    if not lines:
        lines = [
            {
                "id": f"line-{index}",
                "text": line,
                "bbox": None,
                "order": index,
                "page": 1,
                "confidence": None,
            }
            for index, line in enumerate(_normalize_resume_lines(text))
        ]
    return {
        "engine": ocr_result.get("engine") or "unknown",
        "text": text,
        "confidence": ocr_result.get("confidence"),
        "lines": lines,
    }


def _ocr_lines_to_normalizer_items(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text_items: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        text = str(line.get("text") or "").strip()
        if not text:
            continue
        bbox = line.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            x, y, width, height = bbox[:4]
        else:
            x, y, width, height = 0, index * 24, 0, 0
        text_items.append(
            {
                "text": text,
                "page_number": line.get("page") or line.get("page_number") or 1,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "confidence": line.get("confidence"),
            }
        )
    return text_items


def _build_image_preprocess_metadata(file_path: str) -> dict[str, Any]:
    return build_image_preprocess_metadata(file_path)


def _normalize_style_tokens(style_tokens: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "text": (style_tokens or {}).get("text"),
        "muted": (style_tokens or {}).get("muted"),
        "accent": (style_tokens or {}).get("accent"),
        "accent_soft": (style_tokens or {}).get("accent_soft"),
        "line": (style_tokens or {}).get("line"),
        "radius": (style_tokens or {}).get("radius"),
        "shadow": (style_tokens or {}).get("shadow") or "none",
        "spacing_density": (style_tokens or {}).get("spacing_density") or "comfortable",
        "title_style": (style_tokens or {}).get("title_style") or "plain",
    }


def _build_structure_from_vlm(vlm_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_type": vlm_result.get("doc_type") or "mixed",
        "layout": vlm_result.get("layout")
        or {"columns": 1, "layout_type": "single-column", "reading_order": "top-to-bottom"},
        "blocks": vlm_result.get("blocks") or [],
    }


def _select_renderer_profile(doc_type: str) -> str:
    if doc_type == "resume":
        return "resume_professional"
    if doc_type == "note":
        return "note_structured"
    if doc_type == "article":
        return "article_clean"
    if doc_type == "poster":
        return "poster_hero"
    if doc_type == "slide":
        return "slide_brief"
    return "generic_document"


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _build_replication_grade(overall_score: int) -> str:
    if overall_score >= 90:
        return "A"
    if overall_score >= 80:
        return "A-"
    if overall_score >= 70:
        return "B+"
    if overall_score >= 60:
        return "B"
    return "C"


def _unique_warning_messages(*warning_groups: list[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for group in warning_groups:
        for item in group:
            message = str(item).strip()
            if not message or message in seen:
                continue
            seen.add(message)
            items.append(message)
    return items


def _build_replication_score(
    analysis: dict[str, Any], source_warnings: list[str] | None = None
) -> dict[str, Any]:
    structure = analysis.get("structure") or {}
    blocks = structure.get("blocks") or []
    style_tokens = analysis.get("style_tokens") or analysis.get("tokens") or {}
    typed_semantics = analysis.get("typed_semantics") or {}
    preprocess = analysis.get("preprocess") or {}
    visual_validation = analysis.get("visual_validation") or {}
    ocr_analysis = analysis.get("ocr_facts") or analysis.get("ocr") or {}

    block_count = len(blocks)
    style_signal_count = sum(
        1
        for key in ("text", "muted", "accent", "accent_soft", "line", "radius", "shadow", "spacing_density", "title_style")
        if style_tokens.get(key) not in (None, "", "none", "plain")
    )
    semantic_block_count = len(typed_semantics.get("semantic_blocks") or [])
    ocr_text = str(ocr_analysis.get("text") or "").strip()
    validation_warnings = [str(item).strip() for item in (visual_validation.get("warnings") or []) if str(item).strip()]

    layout_score = _clamp_score(
        66
        + min(18, block_count * 4)
        + (4 if (structure.get("layout") or {}).get("layout_type") not in {"", "single-column"} else 0)
        + (4 if preprocess.get("page_bbox") else 0)
        + (2 if preprocess.get("separator_lines") else 0)
        - len(validation_warnings) * 2
    )
    style_score = _clamp_score(
        60
        + style_signal_count * 4
        + (4 if preprocess.get("background") else 0)
        + (2 if visual_validation.get("render_preview_path") else 0)
        - len(validation_warnings) * 2
    )
    structure_score = _clamp_score(
        64
        + min(20, block_count * 3)
        + min(10, semantic_block_count * 2)
        - len(validation_warnings) * 2
    )
    content_block_score = _clamp_score(
        62
        + (12 if ocr_text else 0)
        + min(16, block_count * 3)
        + min(6, len((ocr_analysis.get("lines") or [])) // 3)
        - len(validation_warnings)
    )
    overall_score = _clamp_score(
        layout_score * 0.35
        + style_score * 0.25
        + structure_score * 0.25
        + content_block_score * 0.15
    )
    warnings = _unique_warning_messages(validation_warnings, source_warnings or [])
    return {
        "mode": "overall",
        "overall_score": overall_score,
        "layout_score": layout_score,
        "style_score": style_score,
        "structure_score": structure_score,
        "content_block_score": content_block_score,
        "grade": _build_replication_grade(overall_score),
        "warnings": warnings[:6],
    }


def _detect_source_type(kind: str) -> str:
    if kind == "image_structured":
        return "image"
    if kind in {"markdown", "html", "pdf", "docx"}:
        return kind
    return "document"


def _finalize_source_analysis(source: dict[str, Any]) -> dict[str, Any]:
    analysis = source.get("analysis")
    if not isinstance(analysis, dict):
        return source

    structure = analysis.get("structure") or {}
    doc_type = str(structure.get("doc_type") or analysis.get("doc_type") or "mixed")
    renderer_profile = str(
        ((analysis.get("typed_semantics") or {}).get("renderer_profile"))
        or _select_renderer_profile(doc_type)
    )
    warnings = [str(item).strip() for item in (source.get("warnings") or []) if str(item).strip()]
    source_type = _detect_source_type(str(source.get("kind") or ""))
    analysis["replication_score"] = _build_replication_score(analysis, warnings)
    analysis["router"] = build_intent_router_result(
        source_type=source_type,
        doc_type=doc_type,
        block_count=len(structure.get("blocks") or []),
        warning_count=len(warnings),
        renderer_profile=renderer_profile,
    )
    analysis["recommended_followup_prompts"] = build_followup_prompts(
        analysis["replication_score"],
        analysis["router"],
    )
    return source


def _map_semantic_role(doc_type: str, block_type: str) -> str:
    if doc_type == "resume":
        return {
            "page_title": "profile",
            "heading": "section_heading",
            "bullet_list": "skill_group",
            "paragraph": "experience",
        }.get(block_type, "resume_block")
    if doc_type == "note":
        return {
            "page_title": "title",
            "heading": "notes_section",
            "subheading": "notes_subsection",
            "bullet_list": "checklist",
            "code_block": "code_snippet",
            "paragraph": "summary",
        }.get(block_type, "note_block")
    if doc_type == "article":
        return {
            "page_title": "title",
            "heading": "body_section",
            "paragraph": "body_paragraph",
            "quote": "quote_section",
        }.get(block_type, "article_block")
    return "generic_block"


def _build_typed_semantics(doc_type: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "renderer_profile": _select_renderer_profile(doc_type),
        "semantic_blocks": [
            {
                "block_id": block.get("id"),
                "semantic_role": _map_semantic_role(doc_type, block.get("block_type") or "paragraph"),
                "semantic_hint": block.get("text_summary") or block.get("text") or "",
            }
            for block in blocks
        ],
    }


def _build_document_template_schema(
    structure: dict[str, Any], typed_semantics: dict[str, Any], style_tokens: dict[str, Any]
) -> dict[str, Any]:
    return {
        "version": "v1",
        "doc_type": structure.get("doc_type") or "mixed",
        "renderer_profile": typed_semantics.get("renderer_profile") or "generic_document",
        "layout": structure.get("layout") or {},
        "tokens": style_tokens,
        "blocks": structure.get("blocks") or [],
    }


def _build_semantic_role_map(typed_semantics: dict[str, Any]) -> dict[str, str]:
    role_map: dict[str, str] = {}
    for item in typed_semantics.get("semantic_blocks") or []:
        if not isinstance(item, dict):
            continue
        block_id = str(item.get("block_id") or "").strip()
        if not block_id:
            continue
        role_map[block_id] = str(item.get("semantic_role") or "").strip() or "generic_block"
    return role_map


def _render_note_profile(analysis: dict[str, Any]) -> str:
    structure = analysis.get("structure") or {}
    typed_semantics = analysis.get("typed_semantics") or {}
    style_tokens = analysis.get("style_tokens") or {}
    semantic_map = _build_semantic_role_map(typed_semantics)
    parts: list[str] = []
    for block in structure.get("blocks") or []:
        block_id = str(block.get("id") or "")
        block_type = str(block.get("block_type") or "paragraph")
        semantic_role = html.escape(semantic_map.get(block_id, "generic_block"), quote=True)
        if block_type == "page_title":
            parts.append(f'<header class="note-header" data-semantic-role="{semantic_role}"><h1 class="note-page-title" data-block-type="page_title"></h1></header>')
        elif block_type == "heading":
            parts.append(f'<section class="note-section" data-semantic-role="{semantic_role}"><h2 class="note-heading" data-block-type="heading"></h2></section>')
        elif block_type == "subheading":
            parts.append(f'<section class="note-subsection" data-semantic-role="{semantic_role}"><h3 class="note-subheading" data-block-type="subheading"></h3></section>')
        elif block_type == "quote":
            parts.append(f'<blockquote class="note-quote" data-block-type="quote" data-semantic-role="{semantic_role}"></blockquote>')
        elif block_type == "callout":
            parts.append(f'<aside class="note-callout" data-block-type="callout" data-semantic-role="{semantic_role}"></aside>')
        elif block_type == "code_block":
            parts.append(f'<pre class="note-code" data-block-type="code_block" data-semantic-role="{semantic_role}"><code></code></pre>')
        elif block_type == "bullet_list":
            parts.append(f'<section class="note-list-section" data-semantic-role="{semantic_role}"><ul class="note-bullet-list" data-block-type="bullet_list"><li></li></ul></section>')
        else:
            parts.append(f'<section class="note-block note-block-{html.escape(block_type, quote=True)}" data-block-type="{html.escape(block_type, quote=True)}" data-semantic-role="{semantic_role}"></section>')
    return (
        '<article class="generic-image-template note-structured-template" '
        'data-template-kind="generic-image" '
        'data-renderer-profile="note_structured" '
        f'data-doc-type="{html.escape(structure.get("doc_type") or "note", quote=True)}" '
        f'data-title-style="{html.escape(str(style_tokens.get("title_style") or "plain"), quote=True)}">'
        f"{''.join(parts)}"
        "</article>"
    )


def _render_article_profile(analysis: dict[str, Any]) -> str:
    structure = analysis.get("structure") or {}
    typed_semantics = analysis.get("typed_semantics") or {}
    style_tokens = analysis.get("style_tokens") or {}
    semantic_map = _build_semantic_role_map(typed_semantics)
    parts: list[str] = []
    for block in structure.get("blocks") or []:
        block_id = str(block.get("id") or "")
        block_type = str(block.get("block_type") or "paragraph")
        semantic_role = html.escape(semantic_map.get(block_id, "generic_block"), quote=True)
        if block_type == "page_title":
            parts.append(f'<header class="article-header" data-semantic-role="{semantic_role}"><h1 class="article-title" data-block-type="page_title"></h1></header>')
        elif semantic_role == "lead":
            parts.append(f'<section class="article-lead" data-block-type="{html.escape(block_type, quote=True)}" data-semantic-role="lead"></section>')
        elif semantic_role == "body_section":
            parts.append(f'<section class="article-body-section" data-block-type="{html.escape(block_type, quote=True)}" data-semantic-role="body_section"></section>')
        elif block_type == "quote":
            parts.append(f'<blockquote class="article-quote" data-block-type="quote" data-semantic-role="{semantic_role}"></blockquote>')
        else:
            parts.append(f'<section class="article-block article-block-{html.escape(block_type, quote=True)}" data-block-type="{html.escape(block_type, quote=True)}" data-semantic-role="{semantic_role}"></section>')
    return (
        '<article class="generic-image-template article-clean-template" '
        'data-template-kind="generic-image" '
        'data-renderer-profile="article_clean" '
        f'data-doc-type="{html.escape(structure.get("doc_type") or "article", quote=True)}" '
        f'data-title-style="{html.escape(str(style_tokens.get("title_style") or "plain"), quote=True)}">'
        f"{''.join(parts)}"
        "</article>"
    )


def _render_poster_profile(analysis: dict[str, Any]) -> str:
    structure = analysis.get("structure") or {}
    typed_semantics = analysis.get("typed_semantics") or {}
    semantic_map = _build_semantic_role_map(typed_semantics)
    parts: list[str] = []
    for index, block in enumerate(structure.get("blocks") or []):
        block_id = str(block.get("id") or "")
        semantic_role = html.escape(semantic_map.get(block_id, "generic_block"), quote=True)
        if index == 0:
            parts.append(f'<section class="poster-hero" data-block-type="hero" data-semantic-role="{semantic_role}"></section>')
        else:
            parts.append(f'<section class="poster-panel" data-block-type="{html.escape(str(block.get("block_type") or "paragraph"), quote=True)}" data-semantic-role="{semantic_role}"></section>')
    return (
        '<article class="generic-image-template poster-hero-template" '
        'data-template-kind="generic-image" data-renderer-profile="poster_hero">'
        f"{''.join(parts)}"
        "</article>"
    )


def _render_slide_profile(analysis: dict[str, Any]) -> str:
    structure = analysis.get("structure") or {}
    typed_semantics = analysis.get("typed_semantics") or {}
    semantic_map = _build_semantic_role_map(typed_semantics)
    parts = ['<section class="slide-grid" data-block-type="slide-grid">']
    for block in structure.get("blocks") or []:
        block_id = str(block.get("id") or "")
        semantic_role = html.escape(semantic_map.get(block_id, "generic_block"), quote=True)
        parts.append(
            f'<article class="slide-card" data-block-type="{html.escape(str(block.get("block_type") or "paragraph"), quote=True)}" '
            f'data-semantic-role="{semantic_role}"></article>'
        )
    parts.append("</section>")
    return (
        '<article class="generic-image-template slide-brief-template" '
        'data-template-kind="generic-image" data-renderer-profile="slide_brief">'
        f"{''.join(parts)}"
        "</article>"
    )


def _render_document_analysis_to_html(analysis: dict[str, Any]) -> str:
    structure = analysis.get("structure") or {}
    typed_semantics = analysis.get("typed_semantics") or {}
    style_tokens = analysis.get("style_tokens") or {}
    layout = (structure.get("layout") or {}).get("layout_type") or "single-column"
    renderer_profile = typed_semantics.get("renderer_profile") or "generic_document"
    if renderer_profile == "note_structured":
        return _render_note_profile(analysis)
    if renderer_profile == "article_clean":
        return _render_article_profile(analysis)
    if renderer_profile == "poster_hero":
        return _render_poster_profile(analysis)
    if renderer_profile == "slide_brief":
        return _render_slide_profile(analysis)
    parts: list[str] = []
    for block in structure.get("blocks") or []:
        block_type = html.escape(block.get("block_type") or "paragraph", quote=True)
        if block_type == "page_title":
            parts.append(
                '<h1 class="doc-page-title" data-block-type="page_title" data-slot="page_title"></h1>'
            )
        elif block_type == "heading":
            parts.append('<h2 class="doc-heading" data-block-type="heading" data-slot="heading"></h2>')
        elif block_type == "subheading":
            parts.append('<h3 class="doc-subheading" data-block-type="subheading" data-slot="subheading"></h3>')
        elif block_type == "bullet_list":
            parts.append('<ul class="doc-bullet-list" data-block-type="bullet_list" data-slot="bullet_list"><li></li></ul>')
        elif block_type == "numbered_list":
            parts.append('<ol class="doc-numbered-list" data-block-type="numbered_list" data-slot="numbered_list"><li></li></ol>')
        elif block_type == "checklist":
            parts.append('<ul class="doc-checklist" data-block-type="checklist" data-slot="checklist"><li></li></ul>')
        elif block_type == "quote":
            parts.append('<blockquote class="doc-quote" data-block-type="quote" data-slot="quote"></blockquote>')
        elif block_type == "code_block":
            parts.append('<pre class="doc-code-block" data-block-type="code_block" data-slot="code_block"><code></code></pre>')
        elif block_type == "table":
            parts.append('<div class="doc-table" data-block-type="table" data-slot="table"></div>')
        elif block_type == "callout":
            parts.append('<aside class="doc-callout" data-block-type="callout" data-slot="callout"></aside>')
        elif block_type == "divider":
            parts.append('<hr class="doc-divider" data-block-type="divider" data-slot="divider" />')
        else:
            parts.append(f'<section class="doc-block doc-block-{block_type}" data-block-type="{block_type}" data-slot="{block_type}"></section>')
    return (
        '<article class="generic-image-template generic-document-template" '
        'data-template-kind="generic-image" '
        f'data-renderer-profile="{html.escape(renderer_profile, quote=True)}" '
        f'data-doc-type="{html.escape(structure.get("doc_type") or "mixed", quote=True)}" '
        f'data-layout="{html.escape(layout, quote=True)}" '
        f'data-title-style="{html.escape(str(style_tokens.get("title_style") or "plain"), quote=True)}">'
        f"{''.join(parts)}"
        "</article>"
    )


def _render_document_analysis_preview_image(analysis: dict[str, Any], file_name: str) -> str:
    from PIL import Image, ImageDraw

    style_tokens = analysis.get("style_tokens") or {}
    structure = analysis.get("structure") or {}
    background = style_tokens.get("accent_soft") or "#f8fafc"
    line_color = style_tokens.get("line") or "#d9dfe3"
    text_color = style_tokens.get("text") or "#243042"
    preview = Image.new("RGB", (960, 1280), background)
    draw = ImageDraw.Draw(preview)
    y = 48
    for block in structure.get("blocks") or []:
        block_type = str(block.get("block_type") or "paragraph")
        block_height = {
            "page_title": 72,
            "heading": 56,
            "subheading": 44,
            "bullet_list": 96,
            "numbered_list": 96,
            "checklist": 96,
            "quote": 84,
            "code_block": 110,
            "table": 120,
            "divider": 24,
        }.get(block_type, 88)
        draw.rounded_rectangle((48, y, 912, y + block_height), radius=16, outline=line_color, width=2, fill="#ffffff")
        draw.text((72, y + 18), f"{block_type}: {block.get('text_summary') or block.get('text') or ''}", fill=text_color)
        y += block_height + 24
    preview_path = Path(tempfile.gettempdir()) / f"{Path(file_name).stem}.render-preview.png"
    preview.save(preview_path)
    return str(preview_path)


def _assemble_vlm_image_analysis(
    *,
    file_name: str,
    preprocess: dict[str, Any],
    ocr_facts: dict[str, Any],
    structure: dict[str, Any],
    typed_semantics: dict[str, Any],
    style_tokens: dict[str, Any],
) -> dict[str, Any]:
    template_schema = _build_document_template_schema(structure, typed_semantics, style_tokens)
    return {
        "version": "v1",
        "source": {
            "file_name": file_name,
            "source_type": "image",
            "parser_backend": "ocr_provider",
            "image_size": preprocess.get("image_size"),
            "text_item_count": len(ocr_facts.get("lines") or []),
        },
        "preprocess": {key: value for key, value in preprocess.items() if key != "image_size"},
        "ocr_facts": ocr_facts,
        "structure": structure,
        "typed_semantics": typed_semantics,
        "style_tokens": style_tokens,
        "ocr": ocr_facts,
        "layout": {
            "page": {
                "type": "image",
                "layout": (structure.get("layout") or {}).get("layout_type") or "single-column",
                "reading_order": (structure.get("layout") or {}).get("reading_order") or "top-to-bottom",
            },
            "blocks": structure.get("blocks") or [],
        },
        "tokens": style_tokens,
        "template_schema": template_schema,
    }


def _apply_visual_validation_corrections(
    analysis: dict[str, Any], visual_validation: dict[str, Any]
) -> tuple[dict[str, Any], list[str], list[str]]:
    corrected_analysis = {
        **analysis,
        "structure": {
            **(analysis.get("structure") or {}),
            "layout": dict(((analysis.get("structure") or {}).get("layout") or {})),
            "blocks": [dict(block) for block in (((analysis.get("structure") or {}).get("blocks")) or [])],
        },
        "style_tokens": dict(analysis.get("style_tokens") or {}),
    }
    warnings: list[str] = []
    applied_corrections: list[str] = []
    allowed_layout_types = {"single-column", "two-column", "free-layout", "sidebar-content", "hero-sections"}
    allowed_reading_orders = {"top-to-bottom", "left-to-right", "mixed"}
    allowed_block_types = {
        "page_title",
        "heading",
        "subheading",
        "paragraph",
        "bullet_list",
        "numbered_list",
        "checklist",
        "quote",
        "code_block",
        "table",
        "image",
        "diagram",
        "card",
        "callout",
        "divider",
        "footer_note",
    }

    token_corrections = visual_validation.get("token_corrections") if isinstance(visual_validation.get("token_corrections"), dict) else {}
    if not token_corrections and isinstance(visual_validation.get("style_tokens"), dict):
        token_corrections = visual_validation.get("style_tokens") or {}
    for key, value in token_corrections.items():
        if value in (None, ""):
            continue
        corrected_analysis["style_tokens"][key] = value
        applied_corrections.append(f"style_tokens.{key}")

    layout = corrected_analysis["structure"]["layout"]
    layout_corrections = visual_validation.get("layout_corrections") if isinstance(visual_validation.get("layout_corrections"), dict) else {}
    if "layout_type" in layout_corrections:
        new_layout_type = str(layout_corrections.get("layout_type") or "").strip()
        if new_layout_type in allowed_layout_types:
            layout["layout_type"] = new_layout_type
            applied_corrections.append("structure.layout.layout_type")
        elif new_layout_type:
            warnings.append(f"ignored invalid layout correction: {new_layout_type}")
    if "columns" in layout_corrections:
        try:
            columns = int(layout_corrections.get("columns"))
            layout["columns"] = min(3, max(1, columns))
            applied_corrections.append("structure.layout.columns")
        except (TypeError, ValueError):
            warnings.append(f"ignored invalid column correction: {layout_corrections.get('columns')}")
    if "reading_order" in layout_corrections:
        new_reading_order = str(layout_corrections.get("reading_order") or "").strip()
        if new_reading_order in allowed_reading_orders:
            layout["reading_order"] = new_reading_order
            applied_corrections.append("structure.layout.reading_order")
        elif new_reading_order:
            warnings.append(f"ignored invalid reading order correction: {new_reading_order}")

    block_index = {str(block.get("id")): block for block in corrected_analysis["structure"]["blocks"]}
    for correction in visual_validation.get("block_corrections") or []:
        if not isinstance(correction, dict):
            continue
        block_id = str(correction.get("block_id") or "")
        action = str(correction.get("action") or "").strip()
        value = correction.get("value")
        block = block_index.get(block_id)
        if block is None:
            warnings.append(f"ignored missing block correction: {block_id}")
            continue
        if action == "change_block_type":
            new_block_type = str(value or "").strip()
            if new_block_type in allowed_block_types:
                block["block_type"] = new_block_type
                applied_corrections.append(f"structure.blocks.{block_id}.block_type")
            elif new_block_type:
                warnings.append(f"ignored invalid block type correction: {new_block_type}")
            continue
        if action == "change_hierarchy_level":
            try:
                block["hierarchy_level"] = max(0, int(value))
                applied_corrections.append(f"structure.blocks.{block_id}.hierarchy_level")
            except (TypeError, ValueError):
                warnings.append(f"ignored invalid hierarchy correction: {value}")
            continue
        if action == "change_parent_block_id":
            if value in (None, "") or str(value) in block_index:
                block["parent_block_id"] = value
                applied_corrections.append(f"structure.blocks.{block_id}.parent_block_id")
            else:
                warnings.append(f"ignored invalid parent correction: {value}")
            continue
        if action == "change_reading_order":
            try:
                block["reading_order"] = max(0, int(value))
                applied_corrections.append(f"structure.blocks.{block_id}.reading_order")
            except (TypeError, ValueError):
                warnings.append(f"ignored invalid reading order correction: {value}")
            continue
        if action:
            warnings.append(f"ignored unsupported block correction action: {action}")

    return corrected_analysis, applied_corrections, warnings


def _infer_generic_layout(lines: list[str], sections: list[dict[str, Any]]) -> str:
    if _looks_like_resume(lines) and sections:
        if any(_classify_resume_section_region(section["title"]) == "sidebar" for section in sections):
            return "sidebar-content"
        return "two-column"
    if len(sections) >= 3:
        return "single-column"
    return "hero-sections" if lines else "single-column"


def _guess_block_variant(title: str, body_lines: list[str]) -> str:
    if title in RESUME_TIMELINE_HEADINGS:
        return "timeline-group"
    if any(re.match(r"^\d+[.)、]", line) or line.startswith(("-", "•")) for line in body_lines):
        return "bullet-list"
    return "text-paragraph"


def _build_layout_blocks(lines: list[str], sections: list[dict[str, Any]]) -> dict[str, Any]:
    layout_name = _infer_generic_layout(lines, sections)
    blocks: list[dict[str, Any]] = [
        {
            "id": "block-header",
            "type": "header-card",
            "role": "header",
            "bbox": None,
            "children": ["block-name", "block-meta", "block-target"],
        }
    ]
    for index, section in enumerate(sections):
        blocks.append(
            {
                "id": f"block-section-{index}",
                "type": "section",
                "role": "section",
                "title": section["title"],
                "bbox": None,
                "variant": _guess_block_variant(section["title"], section["lines"]),
                "region": _classify_resume_section_region(section["title"]) if layout_name in {"sidebar-content", "two-column"} else "main",
                "children": [f"block-section-content-{index}"],
            }
        )
    if len(blocks) == 1:
        blocks.append(
            {
                "id": "block-section-0",
                "type": "section",
                "role": "section",
                "title": "内容概览",
                "bbox": None,
                "variant": "text-paragraph",
                "region": "main",
                "children": ["block-section-content-0"],
            }
        )
    return {
        "page": {
            "type": "image",
            "layout": layout_name,
            "reading_order": "top-down",
        },
        "blocks": blocks,
    }


def _build_style_tokens(lines: list[str], layout: dict[str, Any]) -> dict[str, Any]:
    return {
        "theme": "professional" if _looks_like_resume(lines) else "document",
        "density": "comfortable" if len(lines) <= 16 else "compact",
        "title_style": "accent-bar" if len(layout.get("blocks") or []) > 1 else "plain",
        "surface": "flat",
        "accent": None,
        "background": None,
        "radius": "medium",
        "shadow": "none",
    }


def _build_template_schema(
    header_lines: list[str], layout: dict[str, Any], tokens: dict[str, Any]
) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [
        {
            "type": "header-card",
            "slots": {
                "name": header_lines[0] if header_lines else "",
                "meta": header_lines[1] if len(header_lines) > 1 else "",
                "target": header_lines[2] if len(header_lines) > 2 else "",
            },
        }
    ]
    for block in layout.get("blocks", [])[1:]:
        blocks.append(
            {
                "type": block["type"],
                "title": block.get("title", ""),
                "variant": block.get("variant", "text-paragraph"),
                "region": block.get("region", "main"),
            }
        )
    return {
        "version": "v1",
        "page": {"layout": layout["page"]["layout"]},
        "tokens": {
            "theme": tokens["theme"],
            "title_style": tokens["title_style"],
        },
        "blocks": blocks,
    }


def _render_template_schema_to_html(schema: dict[str, Any]) -> str:
    layout = schema.get("page", {}).get("layout", "single-column")
    rendered_blocks: list[str] = []
    for block in schema.get("blocks", []):
        block_type = block.get("type", "section")
        if block_type == "header-card":
            rendered_blocks.append(
                '<section class="image-header-card" data-block-type="header-card" data-slot="header-card">'
                '<div class="image-header-title" data-slot="name"></div>'
                '<div class="image-header-meta" data-slot="meta"></div>'
                '<div class="image-header-target" data-slot="target"></div>'
                "</section>"
            )
            continue
        title = html.escape(block.get("title", ""), quote=True)
        variant = block.get("variant", "text-paragraph")
        rendered_blocks.append(
            f'<section class="image-section image-section-{_safe_resume_class_name(title or block_type)}" '
            f'data-block-type="section" data-section-title="{title}" data-variant="{html.escape(variant, quote=True)}">'
            '<div class="image-section-title" data-block-type="section-title" data-slot="section-title"></div>'
            f'<div class="image-section-content" data-block-type="{html.escape(variant, quote=True)}" data-slot="section-content"></div>'
            "</section>"
        )
    return (
        f'<article class="generic-image-template" data-template-kind="generic-image" data-layout="{html.escape(layout, quote=True)}">'
        f"{''.join(rendered_blocks)}"
        "</article>"
    )


def _build_generic_image_analysis(text: str, ocr_result: dict[str, Any]) -> dict[str, Any]:
    lines = _normalize_resume_lines(text)
    header_lines, sections = _split_resume_blocks(lines)
    ocr = _build_image_ocr_analysis(text, ocr_result)
    normalized = normalize_text_items_to_analysis(
        source_type="image",
        file_name=str(ocr_result.get("file_name") or "image"),
        parser_backend="ocr_provider",
        page_count=1,
        text_items=_ocr_lines_to_normalizer_items(ocr.get("lines") or []),
    )
    layout = _build_layout_blocks(lines, sections)
    tokens = _build_style_tokens(lines, layout)
    template_schema = _build_template_schema(header_lines, layout, tokens)
    return {
        "ocr": ocr,
        "source": normalized["source"],
        "structure": normalized["structure"],
        "typed_semantics": normalized["typed_semantics"],
        "layout": layout,
        "tokens": tokens,
        "template_schema": template_schema,
    }


def _extract_source_from_image(
    file_path: str,
    file_name: str,
    provider_id: str = "",
    model_name: str = "",
    user_instruction: str = "",
) -> dict[str, Any]:
    from app.services.ocr.provider import get_ocr_provider

    if not provider_id or not model_name:
        ocr_result = get_ocr_provider().extract_text(Path(file_path))
        text = (ocr_result.get("text") or "").strip()
        warnings = [f"image OCR extracted via {ocr_result.get('engine') or 'unknown'}"]
        analysis = _build_generic_image_analysis(text, ocr_result)
        skeleton_html = _render_template_schema_to_html(analysis["template_schema"])
        return {
            "kind": "image_structured",
            "text": text,
            "skeleton_hint": skeleton_html,
            "warnings": [*warnings, "image template rendered from OCR facts and generic layout schema"],
            "analysis": analysis,
        }

    preprocess = _build_image_preprocess_metadata(file_path)
    ocr_provider = get_ocr_provider()
    with ThreadPoolExecutor(max_workers=2) as executor:
        ocr_future = executor.submit(ocr_provider.extract_text, Path(file_path))
        vlm_future = executor.submit(
            analyze_image_with_vlm,
            file_path=file_path,
            provider_id=provider_id,
            model_name=model_name,
            user_instruction=user_instruction,
        )
        ocr_result = ocr_future.result()
        vlm_result = vlm_future.result()

    text = (ocr_result.get("text") or "").strip()
    ocr_facts = _build_image_ocr_analysis(text, ocr_result)
    structure = _build_structure_from_vlm(vlm_result)
    typed_semantics_warnings: list[str] = []
    try:
        typed_semantics = analyze_typed_semantics_with_vlm(
            provider_id=provider_id,
            model_name=model_name,
            structure=structure,
            user_instruction=user_instruction,
        )
        typed_semantics_warnings.extend(
            [str(item).strip() for item in (typed_semantics.get("warnings") or []) if str(item).strip()]
        )
    except Exception as exc:
        typed_semantics = _build_typed_semantics(structure["doc_type"], structure["blocks"])
        typed_semantics_warnings.append(f"typed semantics fallback: {exc}")
    style_tokens = _normalize_style_tokens(vlm_result.get("style_tokens"))
    analysis = _assemble_vlm_image_analysis(
        file_name=file_name,
        preprocess=preprocess,
        ocr_facts=ocr_facts,
        structure=structure,
        typed_semantics=typed_semantics,
        style_tokens=style_tokens,
    )
    skeleton_html = _render_document_analysis_to_html(analysis)
    render_preview_path = _render_document_analysis_preview_image(analysis, file_name)
    try:
        visual_validation = validate_rendered_template_with_vlm(
            provider_id=provider_id,
            model_name=model_name,
            original_image_path=file_path,
            render_preview_path=render_preview_path,
            user_instruction=user_instruction,
        )
    except Exception as exc:
        visual_validation = {
            "warnings": [f"render validator unavailable: {exc}"],
            "token_corrections": {},
            "layout_corrections": {},
            "block_corrections": [],
            "applied_corrections": [],
            "render_preview_path": render_preview_path,
        }
    corrected_analysis, correction_records, correction_warnings = _apply_visual_validation_corrections(analysis, visual_validation)
    if correction_records:
        visual_validation["applied_corrections"] = correction_records
    if correction_warnings:
        visual_validation["warnings"] = [
            *[str(item).strip() for item in (visual_validation.get("warnings") or []) if str(item).strip()],
            *correction_warnings,
        ]
    if corrected_analysis != analysis:
        analysis = corrected_analysis
        style_tokens = analysis.get("style_tokens") or style_tokens
        structure = analysis.get("structure") or structure
        analysis = _assemble_vlm_image_analysis(
            file_name=file_name,
            preprocess=preprocess,
            ocr_facts=ocr_facts,
            structure=structure,
            typed_semantics=typed_semantics,
            style_tokens=style_tokens,
        )
        skeleton_html = _render_document_analysis_to_html(analysis)
    analysis["visual_validation"] = visual_validation
    warnings = [
        f"image OCR extracted via {ocr_result.get('engine') or 'unknown'}",
        f"image structure analyzed via VLM model {model_name}",
        *[str(item).strip() for item in (vlm_result.get("warnings") or []) if str(item).strip()],
        *typed_semantics_warnings,
        *[str(item).strip() for item in (visual_validation.get("warnings") or []) if str(item).strip()],
    ]
    return {
        "kind": "image_structured",
        "text": text,
        "skeleton_hint": skeleton_html,
        "warnings": [*warnings, "image template rendered from OCR facts and VLM document schema"],
        "analysis": analysis,
    }


def extract_source_from_file(
    file_path: str,
    file_name: str,
    content_type: str | None = None,
    provider_id: str = "",
    model_name: str = "",
    user_instruction: str = "",
) -> dict[str, Any]:
    ext = Path(file_name or file_path).suffix.lower()
    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if ext in HTML_EXTENSIONS or normalized_content_type.startswith("text/html"):
        return _finalize_source_analysis(extract_from_html_adapter(file_path, file_name))
    if ext in TEXT_EXTENSIONS or normalized_content_type.startswith("text/"):
        return _finalize_source_analysis(extract_from_markdown_adapter(file_path, file_name))
    if ext in IMAGE_EXTENSIONS:
        return _finalize_source_analysis(
            _extract_source_from_image(
                file_path,
                file_name,
                provider_id=provider_id,
                model_name=model_name,
                user_instruction=user_instruction,
            )
        )
    if ext == ".pdf" or normalized_content_type in PDF_CONTENT_TYPES:
        return _finalize_source_analysis(
            extract_from_pdf_adapter(
                file_path,
                file_name,
                provider_id=provider_id,
                model_name=model_name,
                user_instruction=user_instruction,
            )
        )
    if ext == ".docx" or normalized_content_type in DOCX_CONTENT_TYPES:
        return _finalize_source_analysis(extract_from_docx_adapter(file_path, file_name))
    return {
        "kind": "binary",
        "text": "",
        "skeleton_hint": '<article class="imported-note-template"><section class="note-body" data-slot="body"></section></article>',
        "warnings": [f"unsupported extension: {ext or 'unknown'}"],
    }


def chunk_source_text(text: str, chunk_size: int = 6000, overlap: int = 400) -> list[dict[str, Any]]:
    if not text:
        return []
    chunks: list[dict[str, Any]] = []
    start = 0
    index = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append({"index": index, "text": text[start:end], "start": start, "end": end, "status": "pending"})
        if end == len(text):
            break
        start = max(0, end - overlap)
        index += 1
    return chunks


def resolve_uploaded_file_path(file_url: str) -> str:
    if file_url.startswith("file://"):
        return file_url[7:]
    match = re.search(r"/uploads/([a-fA-F0-9]+)", file_url)
    if match:
        upload_id = match.group(1)
        matches = sorted(upload_dir().glob(f"{upload_id}.*"))
        if len(matches) == 1:
            return str(matches[0])
    uploads_root = os.environ.get("UPLOADS_DIR") or str(upload_dir())
    safe_name = os.path.basename(file_url)
    return os.path.join(uploads_root, safe_name)
