from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


STANDARD_ARTICLE_TITLE = "如何把多源内容沉淀为个人知识库"
_RESOURCE_PATH = Path(__file__).resolve().parents[1] / "resources" / "style_preview_standard.md"
_FALLBACK_STANDARD_ARTICLE = """# 如何把多源内容沉淀为个人知识库

真正有价值的内容不应该只被总结一次。网页、视频、语音、文档和 AI 对话都可能包含可复用的观点、证据和行动线索。

知识库的关键不是保存更多文件，而是把分散来源转化为可追溯、可检索、可继续加工的结构化知识。
"""
_DEFAULT_SECTIONS = ["核心结论", "关键发现", "知识整理", "可执行建议", "待追问"]
_SECTION_LIMIT = 6


class _HeadingCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._current_tag = ""
        self._current_parts: list[str] = []
        self.headings: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h2", "h3"}:
            self._current_tag = tag
            self._current_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_tag:
            self._current_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._current_tag:
            text = " ".join("".join(self._current_parts).split())
            if text:
                self.headings.append(text)
            self._current_tag = ""
            self._current_parts = []


def load_standard_article() -> str:
    try:
        return _RESOURCE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _FALLBACK_STANDARD_ARTICLE


def _article_excerpt() -> str:
    text = re.sub(r"^#\s+.+?$", "", load_standard_article(), flags=re.MULTILINE).strip()
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text


def _extract_template_sections(template: dict[str, Any]) -> list[str]:
    rule_global = (template.get("rule_config") or {}).get("global") or {}
    configured = [
        item
        for item in [
            *(rule_global.get("must_include") or []),
            *(rule_global.get("optional_include") or []),
        ]
        if isinstance(item, str) and item.strip()
    ]
    if configured:
        return list(dict.fromkeys(configured))[:_SECTION_LIMIT]

    parser = _HeadingCollector()
    parser.feed(template.get("skeleton_html") or "")
    headings = [item for item in parser.headings if item != template.get("name")]
    return (headings or _DEFAULT_SECTIONS)[:_SECTION_LIMIT]


def _section_content(section: str) -> list[str]:
    if "结论" in section or "摘要" in section or "主旨" in section:
        return [
            "多源内容进入知识库前，需要先完成提炼、归类和证据保留。",
            "标准化模板能降低整理成本，让视频、网页、语音和 AI 对话形成统一的知识资产。",
        ]
    if "发现" in section or "观点" in section:
        return [
            "信息来源分散会增加复用成本，统一结构是长期积累的前提。",
            "逐字保存不等于知识沉淀，关键是保留主张、依据、案例和后续问题。",
            "AI 适合做初步拆解和格式化，但模板需要帮助人快速判断内容价值。",
        ]
    if "行动" in section or "任务" in section or "建议" in section:
        return [
            "为高频内容类型准备默认模板。",
            "对长内容保留证据和引用，对短内容优先保留结论和行动项。",
            "定期把同主题笔记合并成专题，形成可复用的知识网络。",
        ]
    if "追问" in section or "问题" in section:
        return [
            "哪些内容值得进入长期知识库？",
            "不同来源是否需要不同的质量评分标准？",
            "如何在本地优先和隐私保护前提下利用 AI 整理个人知识？",
        ]
    if "证据" in section or "案例" in section or "引用" in section:
        return [
            "视频提供画面语境，网页提供结构化观点，AI 对话保留推理过程。",
            "来源、标题、关键片段和引用线索应随笔记一起保存。",
        ]
    return [
        "这部分基于标准文章生成，用于观察当前模板在真实内容下的组织方式。",
        "内容会围绕多源输入、知识整理、复用价值和后续行动展开。",
    ]


def _global_tone(template: dict[str, Any]) -> str:
    global_style = (template.get("style_constraints") or {}).get("global") or {}
    return str(global_style.get("tone") or "").strip()


def _build_markdown(template: dict[str, Any], sections: list[str]) -> str:
    name = (template.get("name") or "风格模板").strip()
    tone = _global_tone(template)
    lines = [
        f"# {name} · 标准文章预览",
        "",
        f"> 来源：内置标准文章《{STANDARD_ARTICLE_TITLE}》。这是一份基于当前风格模板生成的演示内容。",
    ]
    if tone:
        lines.extend(["", f"> 风格基调：{tone}。"])
    lines.extend(["", "## 标准文章原始内容", "", _article_excerpt()])
    for section in sections:
        lines.extend(["", f"## {section}", ""])
        for item in _section_content(section):
            lines.append(f"- {item}")
    return "\n".join(lines).strip() + "\n"


def _markdown_to_html(markdown: str, template_name: str) -> str:
    parts = [
        f'<article class="notemeld-style-example" data-template-name="{html.escape(template_name, quote=True)}">'
    ]
    in_list = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            if in_list:
                parts.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("> "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        elif line.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{html.escape(line[2:])}</li>")
        else:
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        parts.append("</ul>")
    parts.append("</article>")
    return "".join(parts)


def generate_style_example_content(template: dict[str, Any]) -> dict[str, str]:
    output_formats = template.get("output_formats") or ["markdown"]
    sections = _extract_template_sections(template)
    markdown = _build_markdown(template, sections)
    html_content = _markdown_to_html(markdown, template.get("name") or "风格模板")
    return {
        "markdown": markdown if "markdown" in output_formats else "",
        "html": html_content if "html" in output_formats else "",
    }


def with_standard_example_content(template: dict[str, Any]) -> dict[str, Any]:
    next_template = dict(template)
    next_template["example_content"] = generate_style_example_content(next_template)
    return next_template
