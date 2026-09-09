from __future__ import annotations

import re
from collections.abc import Sequence

from app.services.html_to_markdown import html_to_markdown


_DOCUMENT_FENCE = re.compile(
    r"\A```(?:html|markdown|md)?[ \t]*\r?\n([\s\S]*?)\r?\n```[ \t]*\Z",
    re.IGNORECASE,
)
_SOURCE_PREFIXED_DOCUMENT_FENCE = re.compile(
    r"\A(>\s*来源链接：[^\r\n]+\r?\n\r?\n)"
    r"```(?:html|markdown|md)?[ \t]*\r?\n([\s\S]*?)\r?\n```[ \t]*\Z",
    re.IGNORECASE,
)
_HTML_DOCUMENT_START = re.compile(
    r"\A\s*(?:<!doctype\s+html\s*>\s*)?(?:<!--[\s\S]*?-->\s*)*<[a-z][a-z0-9:-]*\b",
    re.IGNORECASE,
)
_ANY_FENCE = re.compile(r"```|~~~")
_MARKDOWN_BLOCK = re.compile(r"(?m)^\s{0,3}(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|>\s)")


def strip_single_document_fence(content: str) -> str:
    """Remove a model-added fence only when it encloses the complete document."""
    stripped = (content or "").strip()
    source_match = _SOURCE_PREFIXED_DOCUMENT_FENCE.fullmatch(stripped)
    if source_match:
        return f"{source_match.group(1)}{source_match.group(2).strip()}"
    match = _DOCUMENT_FENCE.fullmatch(stripped)
    return match.group(1).strip() if match else content


def looks_like_html(content: str) -> bool:
    value = (content or "").strip()
    if not value or _ANY_FENCE.search(value) or _MARKDOWN_BLOCK.search(value):
        return False
    return bool(_HTML_DOCUMENT_START.search(value))


def normalize_note_output(content: str, output_formats: Sequence[str] | None) -> str:
    """Normalize model output to the style's persistence contract."""
    normalized = strip_single_document_fence(content)
    formats = [str(item).strip().lower() for item in (output_formats or ["markdown"])]
    needs_markdown = "markdown" in formats
    needs_html = "html" in formats

    if needs_markdown and looks_like_html(normalized):
        markdown = html_to_markdown(normalized)
    else:
        markdown = normalized

    if needs_markdown and needs_html and looks_like_html(normalized):
        return (
            "<!-- HTML_OUTPUT_START -->\n"
            f"{normalized}\n"
            "<!-- HTML_OUTPUT_END -->\n\n"
            "<!-- MARKDOWN_OUTPUT_START -->\n"
            f"{markdown}"
            "<!-- MARKDOWN_OUTPUT_END -->"
        )
    if needs_markdown:
        return markdown
    return normalized
