from __future__ import annotations

import html
import re
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from app.services.liteparse_style_normalizer import normalize_text_items_to_analysis
from app.services.note_style_import_service import extract_template_from_text


NOISE_TAGS = {"script", "style", "noscript", "iframe"}
NOISE_ATTR_KEYWORDS = (
    " ad",
    "ad-",
    "ads",
    "advert",
    "banner",
    "promo",
    "tracking",
    "track",
    "analytics",
    "cookie",
    "subscribe",
    "share",
)


def _attrs_to_text(attrs: list[tuple[str, str | None]]) -> str:
    parts: list[str] = []
    for key, value in attrs:
        parts.append(f"{key}={value or ''}".lower())
    return " ".join(parts)


def _is_noise_node(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
    if tag in NOISE_TAGS:
        return True
    attr_text = f" {_attrs_to_text(attrs)} "
    return any(keyword in attr_text for keyword in NOISE_ATTR_KEYWORDS)


def _extract_main_dom_fragment(raw_html: str) -> str:
    for pattern in (
        r"<main\b[\s\S]*?</main>",
        r"<article\b[\s\S]*?</article>",
        r"<body\b[\s\S]*?</body>",
    ):
        match = re.search(pattern, raw_html, re.IGNORECASE)
        if match:
            return match.group(0)
    return raw_html


class _SkeletonHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if _is_noise_node(tag, attrs):
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
        if tag in NOISE_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag not in {"br", "img", "input", "meta", "link"}:
            self.parts.append(f"</{tag}>")


class _HTMLBlockParser(HTMLParser):
    BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "blockquote", "pre", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.block_index = 0
        self.blocks: list[dict[str, Any]] = []
        self.block_stack: list[dict[str, Any]] = []
        self.has_article_root = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if _is_noise_node(tag, attrs):
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"article", "main"}:
            self.has_article_root = True
        if tag == "img":
            self._append_block("image", self._get_attr(attrs, "alt") or "image")
            return
        if tag == "hr":
            self._append_block("divider", "divider")
            return
        if tag in self.BLOCK_TAGS:
            self.block_stack.append({"tag": tag, "text_parts": [], "item_count": 0})
            return
        if tag == "li":
            list_block = self._active_list_block()
            if list_block is not None:
                list_block["item_count"] += 1
                if list_block["text_parts"]:
                    list_block["text_parts"].append(" | ")
            return
        if tag == "br" and self.block_stack:
            self.block_stack[-1]["text_parts"].append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in NOISE_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag in self.BLOCK_TAGS and self.block_stack:
            block = self.block_stack.pop()
            if block["tag"] != tag:
                return
            self._close_block(block)

    def handle_data(self, data: str) -> None:
        if self.skip_depth or not self.block_stack:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.block_stack[-1]["text_parts"].append(text)

    def _active_list_block(self) -> dict[str, Any] | None:
        for block in reversed(self.block_stack):
            if block["tag"] in {"ul", "ol"}:
                return block
        return None

    def _get_attr(self, attrs: list[tuple[str, str | None]], name: str) -> str:
        for key, value in attrs:
            if key == name:
                return value or ""
        return ""

    def _close_block(self, block: dict[str, Any]) -> None:
        tag = str(block["tag"])
        summary = "".join(block["text_parts"]).strip() or tag
        if tag == "h1":
            self._append_block("page_title", summary, heading_level=1)
        elif tag == "h2":
            self._append_block("heading", summary, heading_level=2)
        elif tag in {"h3", "h4", "h5", "h6"}:
            self._append_block("subheading", summary, heading_level=int(tag[1]))
        elif tag == "p":
            self._append_block("paragraph", summary)
        elif tag == "ul":
            self._append_block(
                "bullet_list",
                summary,
                item_count=max(1, int(block.get("item_count") or 0)),
            )
        elif tag == "ol":
            self._append_block(
                "numbered_list",
                summary,
                item_count=max(1, int(block.get("item_count") or 0)),
            )
        elif tag == "blockquote":
            self._append_block("quote", summary)
        elif tag == "pre":
            self._append_block("code_block", summary)
        elif tag == "table":
            self._append_block("table", summary)

    def _append_block(self, block_type: str, summary: str, **extra: Any) -> None:
        self.block_index += 1
        block = {
            "id": f"html-block-{self.block_index}",
            "block_type": block_type,
            "text_summary": summary,
        }
        block.update(extra)
        self.blocks.append(block)


def build_adapter_result(
    kind: str,
    text: str,
    skeleton_hint: str,
    warnings: list[str] | None = None,
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "kind": kind,
        "text": text,
        "skeleton_hint": skeleton_hint,
        "warnings": warnings or [],
    }
    if analysis is not None:
        result["analysis"] = analysis
    return result


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


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}, text
    frontmatter: dict[str, str] = {}
    end_index = -1
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
        key, separator, value = lines[index].partition(":")
        if separator and key.strip():
            frontmatter[key.strip()] = value.strip()
    if end_index == -1:
        return {}, text
    body = "\n".join(lines[end_index + 1 :]).lstrip("\n")
    return frontmatter, body


def _parse_markdown_blocks(text: str) -> dict[str, Any]:
    frontmatter, body = _parse_frontmatter(text)
    lines = body.splitlines()
    blocks: list[dict[str, Any]] = []
    index = 0
    block_index = 0

    def _new_block(block_type: str, summary: str, **extra: Any) -> dict[str, Any]:
        nonlocal block_index
        block_index += 1
        block = {
            "id": f"md-block-{block_index}",
            "block_type": block_type,
            "text_summary": summary,
        }
        block.update(extra)
        return block

    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("```"):
            fence = stripped[:3]
            language = stripped[3:].strip()
            content: list[str] = []
            index += 1
            while index < len(lines) and lines[index].strip() != fence:
                content.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            blocks.append(
                _new_block(
                    "code_block",
                    language or "code block",
                    language=language,
                    line_count=len(content),
                )
            )
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            blocks.append(
                _new_block(
                    "page_title" if level == 1 and not any(block["block_type"] == "page_title" for block in blocks) else ("heading" if level <= 2 else "subheading"),
                    title,
                    heading_level=level,
                )
            )
            index += 1
            continue
        if re.match(r"^([-*+])\s+.+$", stripped):
            items: list[str] = []
            while index < len(lines) and re.match(r"^([-*+])\s+.+$", lines[index].strip()):
                items.append(re.sub(r"^([-*+])\s+", "", lines[index].strip()))
                index += 1
            blocks.append(_new_block("bullet_list", items[0] if items else "bullet list", item_count=len(items)))
            continue
        if re.match(r"^\d+[.)]\s+.+$", stripped):
            items = []
            while index < len(lines) and re.match(r"^\d+[.)]\s+.+$", lines[index].strip()):
                items.append(re.sub(r"^\d+[.)]\s+", "", lines[index].strip()))
                index += 1
            blocks.append(
                _new_block("numbered_list", items[0] if items else "numbered list", item_count=len(items))
            )
            continue
        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip().lstrip(">").strip())
                index += 1
            blocks.append(_new_block("quote", quote_lines[0] if quote_lines else "quote"))
            continue
        if "|" in stripped and index + 1 < len(lines) and re.match(r"^\s*\|?[\s:-]+\|[\s|:-]*$", lines[index + 1]):
            table_lines = 1
            index += 2
            while index < len(lines) and "|" in lines[index]:
                table_lines += 1
                index += 1
            blocks.append(_new_block("table", "table", line_count=table_lines))
            continue
        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            next_line = lines[index].strip()
            if not next_line:
                index += 1
                break
            if (
                next_line.startswith("```")
                or re.match(r"^(#{1,6})\s+.+$", next_line)
                or re.match(r"^([-*+])\s+.+$", next_line)
                or re.match(r"^\d+[.)]\s+.+$", next_line)
                or next_line.startswith(">")
            ):
                break
            paragraph_lines.append(next_line)
            index += 1
        blocks.append(_new_block("paragraph", paragraph_lines[0]))

    structure = {
        "doc_type": "note",
        "layout": {"columns": 1, "layout_type": "single-column", "reading_order": "top-to-bottom"},
        "blocks": blocks,
    }
    return {
        "frontmatter": frontmatter,
        "structure": structure,
        "typed_semantics": {
            "renderer_profile": "note_structured",
            "semantic_blocks": [
                {
                    "block_id": block["id"],
                    "semantic_role": (
                        "title"
                        if block["block_type"] == "page_title"
                        else "notes_section"
                        if block["block_type"] in {"heading", "subheading"}
                        else "code_snippet"
                        if block["block_type"] == "code_block"
                        else "reference"
                        if block["block_type"] == "quote"
                        else "content"
                    ),
                    "semantic_hint": block["text_summary"],
                }
                for block in blocks
            ],
        },
        "template_schema": {
            "version": "v1",
            "renderer_profile": "note_structured",
            "frontmatter": frontmatter,
            "blocks": [{"type": block["block_type"]} for block in blocks],
        },
    }


def _render_markdown_analysis_to_html(analysis: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in (analysis.get("structure") or {}).get("blocks") or []:
        block_type = html.escape(str(block.get("block_type") or "paragraph"), quote=True)
        if block_type == "page_title":
            parts.append('<header class="md-header"><h1 class="md-page-title" data-block-type="page_title"></h1></header>')
        elif block_type == "heading":
            parts.append('<section class="md-section"><h2 class="md-heading" data-block-type="heading"></h2></section>')
        elif block_type == "subheading":
            parts.append('<section class="md-subsection"><h3 class="md-subheading" data-block-type="subheading"></h3></section>')
        elif block_type == "bullet_list":
            parts.append('<section class="md-list"><ul data-block-type="bullet_list"><li></li></ul></section>')
        elif block_type == "numbered_list":
            parts.append('<section class="md-list"><ol data-block-type="numbered_list"><li></li></ol></section>')
        elif block_type == "quote":
            parts.append('<blockquote class="md-quote" data-block-type="quote"></blockquote>')
        elif block_type == "code_block":
            parts.append('<pre class="md-code" data-block-type="code_block"><code></code></pre>')
        elif block_type == "table":
            parts.append('<div class="md-table" data-block-type="table"></div>')
        else:
            parts.append(f'<section class="md-block md-block-{block_type}" data-block-type="{block_type}"></section>')
    body = "".join(parts) or _markdown_skeleton("")
    return (
        '<article class="markdown-adapter-template" '
        'data-template-kind="markdown" '
        'data-renderer-profile="note_structured">'
        f"{body}"
        "</article>"
    )


def _sanitize_html_to_skeleton(raw_html: str) -> str:
    parser = _SkeletonHTMLParser()
    parser.feed(_extract_main_dom_fragment(raw_html or ""))
    skeleton = "".join(parser.parts).strip()
    return skeleton or '<article class="imported-note-template"><section class="note-body" data-slot="body"></section></article>'


def _extract_html_text(raw_html: str) -> str:
    parsed = _parse_html_blocks(raw_html)
    text_parts = [str(block.get("text_summary") or "").strip() for block in (parsed.get("structure") or {}).get("blocks") or []]
    return re.sub(r"\s+", " ", " ".join(part for part in text_parts if part)).strip()


def _parse_html_blocks(raw_html: str) -> dict[str, Any]:
    parser = _HTMLBlockParser()
    parser.feed(_extract_main_dom_fragment(raw_html or ""))
    blocks: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for block in parser.blocks:
        key = (str(block.get("block_type") or ""), str(block.get("text_summary") or ""))
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        blocks.append(block)
    renderer_profile = "article_clean" if parser.has_article_root else "generic_document"
    return {
        "structure": {
            "doc_type": "article" if parser.has_article_root else "document",
            "layout": {"columns": 1, "layout_type": "single-column", "reading_order": "top-to-bottom"},
            "blocks": blocks,
        },
        "typed_semantics": {
            "renderer_profile": renderer_profile,
            "semantic_blocks": [
                {
                    "block_id": block["id"],
                    "semantic_role": (
                        "title"
                        if block["block_type"] == "page_title"
                        else "body_section"
                        if block["block_type"] in {"heading", "subheading"}
                        else "quote_section"
                        if block["block_type"] == "quote"
                        else "code_snippet"
                        if block["block_type"] == "code_block"
                        else "content"
                    ),
                    "semantic_hint": block["text_summary"],
                }
                for block in blocks
            ],
        },
        "template_schema": {
            "version": "v1",
            "renderer_profile": renderer_profile,
            "blocks": [{"type": block["block_type"]} for block in blocks],
        },
    }


def extract_from_markdown_adapter(file_path: str, file_name: str) -> dict[str, Any]:
    text = _read_text(file_path)
    ext = Path(file_name or file_path).suffix.lower()
    analysis = _parse_markdown_blocks(text)
    return build_adapter_result(
        "markdown" if ext in {".md", ".markdown"} else "text",
        text,
        _render_markdown_analysis_to_html(analysis),
        ["markdown structure parsed via deterministic adapter"],
        analysis=analysis,
    )


def extract_from_html_adapter(file_path: str, file_name: str) -> dict[str, Any]:
    raw = _read_text(file_path)
    return build_adapter_result(
        "html",
        _extract_html_text(raw),
        _sanitize_html_to_skeleton(raw),
        ["html structure parsed via deterministic adapter"],
        analysis=_parse_html_blocks(raw),
    )


def _looks_like_plain_heading(line: str, next_line: str | None = None) -> bool:
    stripped = line.strip().rstrip(":")
    if not stripped or re.match(r"^([-*+])\s+.+$", stripped) or re.match(r"^\d+[.)]\s+.+$", stripped):
        return False
    if len(stripped) > 80:
        return False
    if line.strip().endswith(":"):
        return True
    if next_line and (
        re.match(r"^([-*+])\s+.+$", next_line.strip()) or re.match(r"^\d+[.)]\s+.+$", next_line.strip())
    ):
        return True
    word_count = len(re.findall(r"[A-Za-z0-9_]+", stripped))
    return 0 < word_count <= 8 and not re.search(r"[.!?]$", stripped)


def _parse_plain_text_document(text: str, block_prefix: str) -> dict[str, Any]:
    lines = text.splitlines()
    blocks: list[dict[str, Any]] = []
    block_index = 0
    index = 0
    seen_title = False

    def _new_block(block_type: str, summary: str, **extra: Any) -> dict[str, Any]:
        nonlocal block_index
        block_index += 1
        block = {
            "id": f"{block_prefix}-block-{block_index}",
            "block_type": block_type,
            "text_summary": summary,
        }
        block.update(extra)
        return block

    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if re.match(r"^([-*+])\s+.+$", stripped):
            items: list[str] = []
            while index < len(lines) and re.match(r"^([-*+])\s+.+$", lines[index].strip()):
                items.append(re.sub(r"^([-*+])\s+", "", lines[index].strip()))
                index += 1
            blocks.append(_new_block("bullet_list", items[0] if items else "bullet list", item_count=len(items)))
            continue
        if re.match(r"^\d+[.)]\s+.+$", stripped):
            items = []
            while index < len(lines) and re.match(r"^\d+[.)]\s+.+$", lines[index].strip()):
                items.append(re.sub(r"^\d+[.)]\s+", "", lines[index].strip()))
                index += 1
            blocks.append(
                _new_block("numbered_list", items[0] if items else "numbered list", item_count=len(items))
            )
            continue
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else None
        if not seen_title:
            blocks.append(_new_block("page_title", stripped, heading_level=1))
            seen_title = True
            index += 1
            continue
        if _looks_like_plain_heading(stripped, next_line):
            blocks.append(_new_block("heading", stripped, heading_level=2))
            index += 1
            continue
        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            next_paragraph_line = lines[index].strip()
            if not next_paragraph_line:
                index += 1
                break
            upcoming = lines[index + 1].strip() if index + 1 < len(lines) else None
            if (
                re.match(r"^([-*+])\s+.+$", next_paragraph_line)
                or re.match(r"^\d+[.)]\s+.+$", next_paragraph_line)
                or _looks_like_plain_heading(next_paragraph_line, upcoming)
            ):
                break
            paragraph_lines.append(next_paragraph_line)
            index += 1
        blocks.append(_new_block("paragraph", paragraph_lines[0]))

    doc_type = "note" if any(block["block_type"] in {"heading", "bullet_list", "numbered_list"} for block in blocks) else "document"
    renderer_profile = "note_structured" if doc_type == "note" else "generic_document"
    return {
        "structure": {
            "doc_type": doc_type,
            "layout": {"columns": 1, "layout_type": "single-column", "reading_order": "top-to-bottom"},
            "blocks": blocks,
        },
        "typed_semantics": {
            "renderer_profile": renderer_profile,
            "semantic_blocks": [
                {
                    "block_id": block["id"],
                    "semantic_role": (
                        "title"
                        if block["block_type"] == "page_title"
                        else "notes_section"
                        if block["block_type"] == "heading"
                        else "content"
                    ),
                    "semantic_hint": block["text_summary"],
                }
                for block in blocks
            ],
        },
        "template_schema": {
            "version": "v1",
            "renderer_profile": renderer_profile,
            "blocks": [{"type": block["block_type"]} for block in blocks],
        },
    }


def _render_plain_document_analysis_to_html(analysis: dict[str, Any], template_kind: str = "pdf") -> str:
    renderer_profile = (
        ((analysis.get("typed_semantics") or {}).get("renderer_profile")) or "generic_document"
    )
    if renderer_profile == "note_structured":
        return _render_markdown_analysis_to_html(analysis)
    parts: list[str] = []
    for block in (analysis.get("structure") or {}).get("blocks") or []:
        block_type = html.escape(str(block.get("block_type") or "paragraph"), quote=True)
        if block_type == "page_title":
            parts.append('<header class="doc-header"><h1 data-block-type="page_title"></h1></header>')
        elif block_type == "heading":
            parts.append('<section class="doc-section"><h2 data-block-type="heading"></h2></section>')
        elif block_type == "bullet_list":
            parts.append('<section class="doc-list"><ul data-block-type="bullet_list"><li></li></ul></section>')
        elif block_type == "numbered_list":
            parts.append('<section class="doc-list"><ol data-block-type="numbered_list"><li></li></ol></section>')
        else:
            parts.append(
                f'<section class="doc-block doc-block-{block_type}" data-block-type="{block_type}"></section>'
            )
    return (
        '<article class="document-adapter-template" '
        f'data-template-kind="{html.escape(template_kind, quote=True)}" '
        f'data-renderer-profile="{html.escape(renderer_profile, quote=True)}">'
        f"{''.join(parts)}"
        "</article>"
    )


def _extract_digital_text_from_pdf(file_path: str) -> dict[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    pages: list[dict[str, Any]] = []
    texts: list[str] = []
    for page_index, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        pages.append({"page": page_index, "text": page_text})
        if page_text:
            texts.append(page_text)
    return {
        "text": "\n\n".join(texts).strip(),
        "page_count": len(reader.pages),
        "pages": pages,
    }


def _extract_pymupdf_layout_from_pdf(file_path: str) -> dict[str, Any]:
    import fitz  # type: ignore

    texts: list[str] = []
    pages: list[dict[str, Any]] = []
    page_sizes: list[dict[str, Any]] = []
    text_items: list[dict[str, Any]] = []
    with fitz.open(file_path) as document:
        for page_index, page in enumerate(document, start=1):
            rect = page.rect
            page_sizes.append(
                {
                    "page_number": page_index,
                    "width": float(rect.width),
                    "height": float(rect.height),
                }
            )
            page_text_parts: list[str] = []
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks") or []:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines") or []:
                    spans = [
                        span
                        for span in (line.get("spans") or [])
                        if str(span.get("text") or "").strip()
                    ]
                    if not spans:
                        continue
                    line_text = "".join(str(span.get("text") or "") for span in spans).strip()
                    if not line_text:
                        continue
                    x0, y0, x1, y1 = line.get("bbox") or block.get("bbox") or [0, 0, 0, 0]
                    font_sizes = [float(span.get("size") or 0) for span in spans]
                    font_names = [str(span.get("font") or "") for span in spans if span.get("font")]
                    text_items.append(
                        {
                            "text": line_text,
                            "page_number": page_index,
                            "x": float(x0),
                            "y": float(y0),
                            "width": max(0.0, float(x1) - float(x0)),
                            "height": max(0.0, float(y1) - float(y0)),
                            "font_size": max(font_sizes) if font_sizes else None,
                            "font_name": font_names[0] if font_names else None,
                        }
                    )
                    page_text_parts.append(line_text)
            page_text = "\n".join(page_text_parts).strip()
            pages.append({"page": page_index, "text": page_text})
            if page_text:
                texts.append(page_text)
    return {
        "text": "\n\n".join(texts).strip(),
        "page_count": len(pages),
        "pages": pages,
        "page_sizes": page_sizes,
        "text_items": text_items,
    }


def _render_pdf_pages_to_images(file_path: str) -> list[str]:
    stem = Path(file_path).stem
    try:
        import fitz  # type: ignore

        image_paths: list[str] = []
        with fitz.open(file_path) as document:
            for page_index, page in enumerate(document, start=1):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image_path = Path(tempfile.gettempdir()) / f"{stem}-page-{page_index}.png"
                pixmap.save(str(image_path))
                image_paths.append(str(image_path))
        return image_paths
    except Exception:
        pass

    try:
        from pypdf import PdfReader

        image_paths = []
        reader = PdfReader(file_path)
        for page_index, page in enumerate(reader.pages, start=1):
            page_images = list(getattr(page, "images", []) or [])
            if not page_images:
                continue
            image = page_images[0]
            suffix = Path(str(getattr(image, "name", ""))).suffix.lower() or ".png"
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                suffix = ".png"
            image_path = Path(tempfile.gettempdir()) / f"{stem}-page-{page_index}{suffix}"
            image_path.write_bytes(image.data)
            image_paths.append(str(image_path))
        return image_paths
    except Exception:
        return []


def _ocr_image_sequence(image_paths: list[str]) -> dict[str, Any]:
    from app.services.ocr.provider import get_ocr_provider

    provider = get_ocr_provider()
    texts: list[str] = []
    pages: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    line_order = 0
    engine = getattr(provider, "engine", "unknown")
    confidence: float | None = None

    for page_index, image_path in enumerate(image_paths, start=1):
        ocr_result = provider.extract_text(Path(image_path))
        engine = str(ocr_result.get("engine") or engine)
        confidence = ocr_result.get("confidence")
        page_text = str(ocr_result.get("text") or "").strip()
        if page_text:
            texts.append(page_text)
        pages.append(
            {
                "page": page_index,
                "text": page_text,
                "confidence": ocr_result.get("confidence"),
            }
        )
        if ocr_result.get("lines"):
            for raw_line in ocr_result.get("lines") or []:
                normalized_line = dict(raw_line)
                normalized_line["page"] = page_index
                normalized_line["order"] = line_order
                lines.append(normalized_line)
                line_order += 1
            continue
        for line_text in [item for item in page_text.splitlines() if item.strip()]:
            lines.append(
                {
                    "id": f"line-{line_order}",
                    "text": line_text,
                    "bbox": None,
                    "order": line_order,
                    "page": page_index,
                    "confidence": None,
                }
            )
            line_order += 1

    return {
        "text": "\n\n".join(texts).strip(),
        "engine": engine,
        "confidence": confidence,
        "pages": pages,
        "lines": lines,
    }


def _ocr_lines_to_text_items(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def extract_from_pdf_adapter(
    file_path: str,
    file_name: str,
    provider_id: str = "",
    model_name: str = "",
    user_instruction: str = "",
) -> dict[str, Any]:
    layout_result = _extract_pymupdf_layout_from_pdf(file_path)
    layout_text = str(layout_result.get("text") or "").strip()
    if layout_text:
        analysis = normalize_text_items_to_analysis(
            source_type="pdf",
            file_name=file_name,
            parser_backend="pymupdf_layout",
            page_count=layout_result.get("page_count") or len(layout_result.get("pages") or []),
            page_sizes=layout_result.get("page_sizes") or [],
            text_items=layout_result.get("text_items") or [],
        )
        return build_adapter_result(
            "pdf",
            analysis["text"],
            _render_plain_document_analysis_to_html(analysis),
            ["pdf structure parsed via PyMuPDF layout extraction"],
            analysis=analysis,
        )

    image_paths = _render_pdf_pages_to_images(file_path)
    warnings: list[str]
    if image_paths:
        ocr_result = _ocr_image_sequence(image_paths)
        warnings = [f"pdf image fallback extracted via {ocr_result.get('engine') or 'unknown'} OCR"]
    else:
        from app.services.ocr.provider import get_ocr_provider

        ocr_result = get_ocr_provider().extract_text(Path(file_path))
        warnings = [
            "pdf image fallback used direct OCR on source document because no page renderer was available",
        ]
    text = str(ocr_result.get("text") or "").strip()
    analysis = normalize_text_items_to_analysis(
        source_type="pdf",
        file_name=file_name,
        parser_backend="ocr_provider",
        page_count=max(1, len(ocr_result.get("pages") or [])),
        text_items=_ocr_lines_to_text_items(ocr_result.get("lines") or []),
    )
    analysis["ocr"] = {
        "engine": ocr_result.get("engine") or "unknown",
        "confidence": ocr_result.get("confidence"),
        "lines": ocr_result.get("lines") or [],
    }
    return build_adapter_result(
        "pdf",
        text,
        _render_plain_document_analysis_to_html(analysis),
        warnings,
        analysis=analysis,
    )


_DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _normalize_docx_style_name(style_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", style_name.lower())


def _docx_element_text(element: ET.Element) -> str:
    texts = [
        "".join(text.itertext()).strip()
        for text in element.findall(".//w:t", _DOCX_NS)
        if "".join(text.itertext()).strip()
    ]
    return "".join(texts).strip()


def _docx_paragraph_style(paragraph: ET.Element) -> str:
    style = paragraph.find("./w:pPr/w:pStyle", _DOCX_NS)
    if style is None:
        return ""
    return style.attrib.get(f"{{{_DOCX_NS['w']}}}val", "")


def _docx_paragraph_block_type(paragraph: ET.Element, style_name: str, seen_title: bool) -> tuple[str, dict[str, Any]]:
    normalized_style = _normalize_docx_style_name(style_name)
    metadata: dict[str, Any] = {"style_name": style_name or "Normal"}
    if normalized_style in {"heading1", "title"}:
        metadata["heading_level"] = 1
        return ("page_title" if not seen_title else "heading"), metadata
    if normalized_style.startswith("heading") and normalized_style[-1:].isdigit():
        level = int(normalized_style[-1])
        metadata["heading_level"] = level
        return ("heading" if level <= 2 else "subheading"), metadata
    if paragraph.find("./w:pPr/w:numPr", _DOCX_NS) is not None:
        metadata["item_count"] = 1
        return "bullet_list", metadata
    if normalized_style in {"listbullet", "listparagraph", "listcontinue", "listbullet2", "listbullet3"}:
        metadata["item_count"] = 1
        return "bullet_list", metadata
    if normalized_style in {"listnumber", "listnumber2", "listnumber3"}:
        metadata["item_count"] = 1
        return "numbered_list", metadata
    return "paragraph", metadata


def _extract_docx_facts(file_path: str) -> dict[str, Any] | None:
    try:
        with zipfile.ZipFile(file_path) as archive:
            document_xml = archive.read("word/document.xml")
    except (FileNotFoundError, KeyError, zipfile.BadZipFile):
        return None

    root = ET.fromstring(document_xml)
    body = root.find("./w:body", _DOCX_NS)
    if body is None:
        return None

    blocks: list[dict[str, Any]] = []
    text_parts: list[str] = []
    block_index = 0
    seen_title = False

    def _append_block(block_type: str, summary: str, **extra: Any) -> None:
        nonlocal block_index, seen_title
        summary = summary.strip()
        if not summary:
            return
        if block_type == "page_title":
            seen_title = True
        if block_type in {"bullet_list", "numbered_list"} and blocks and blocks[-1]["block_type"] == block_type:
            blocks[-1]["text_summary"] = f'{blocks[-1]["text_summary"]} | {summary}'
            blocks[-1]["item_count"] = int(blocks[-1].get("item_count") or 1) + int(extra.get("item_count") or 1)
            text_parts.append(summary)
            return
        block_index += 1
        block = {
            "id": f"docx-block-{block_index}",
            "block_type": block_type,
            "text_summary": summary,
        }
        block.update(extra)
        blocks.append(block)
        text_parts.append(summary)

    for child in body:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = _docx_element_text(child)
            if not text:
                continue
            style_name = _docx_paragraph_style(child)
            block_type, metadata = _docx_paragraph_block_type(child, style_name, seen_title)
            _append_block(block_type, text, **metadata)
            continue
        if tag != "tbl":
            continue
        rows: list[list[str]] = []
        for row in child.findall("./w:tr", _DOCX_NS):
            cells = [
                _docx_element_text(cell)
                for cell in row.findall("./w:tc", _DOCX_NS)
                if _docx_element_text(cell)
            ]
            if cells:
                rows.append(cells)
        if not rows:
            continue
        table_text = "\n".join(" | ".join(row) for row in rows).strip()
        _append_block(
            "table",
            table_text,
            row_count=len(rows),
            column_count=max(len(row) for row in rows),
            style_name="Table",
        )

    if not blocks:
        return None
    return {
        "text": "\n".join(text_parts).strip(),
        "blocks": blocks,
        "warnings": ["docx structure parsed via minimal OOXML adapter"],
    }


def extract_from_docx_adapter(file_path: str, file_name: str) -> dict[str, Any]:
    facts = _extract_docx_facts(file_path)
    if not facts:
        analysis = _parse_plain_text_document("", "docx")
        analysis["source"] = {
            "file_name": file_name,
            "strategy": "ooxml_fallback",
        }
        return build_adapter_result(
            "docx",
            "",
            _render_plain_document_analysis_to_html(analysis, template_kind="docx"),
            ["docx structure extraction degraded"],
            analysis=analysis,
        )

    blocks = list(facts.get("blocks") or [])
    doc_type = "note" if any(block["block_type"] in {"page_title", "heading", "subheading", "bullet_list", "numbered_list"} for block in blocks) else "document"
    renderer_profile = "note_structured" if doc_type == "note" else "generic_document"
    analysis = {
        "structure": {
            "doc_type": doc_type,
            "layout": {"columns": 1, "layout_type": "single-column", "reading_order": "top-to-bottom"},
            "blocks": blocks,
        },
        "typed_semantics": {
            "renderer_profile": renderer_profile,
            "semantic_blocks": [
                {
                    "block_id": block["id"],
                    "semantic_role": (
                        "title"
                        if block["block_type"] == "page_title"
                        else "notes_section"
                        if block["block_type"] in {"heading", "subheading"}
                        else "reference"
                        if block["block_type"] == "table"
                        else "content"
                    ),
                    "semantic_hint": block["text_summary"],
                }
                for block in blocks
            ],
        },
        "template_schema": {
            "version": "v1",
            "renderer_profile": renderer_profile,
            "blocks": [{"type": block["block_type"]} for block in blocks],
        },
        "source": {
            "file_name": file_name,
            "strategy": "ooxml",
        },
    }
    return build_adapter_result(
        "docx",
        str(facts.get("text") or "").strip(),
        _render_plain_document_analysis_to_html(analysis, template_kind="docx"),
        list(facts.get("warnings") or []),
        analysis=analysis,
    )
