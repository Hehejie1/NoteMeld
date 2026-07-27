from __future__ import annotations

from html.parser import HTMLParser


class _MarkdownHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0
        self.list_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n" + "#" * int(tag[1]) + " ")
        elif tag == "p":
            self.parts.append("\n\n")
        elif tag in {"ul", "ol"}:
            self.list_stack.append(tag)
            self.parts.append("\n")
        elif tag == "li":
            marker = "1." if self.list_stack and self.list_stack[-1] == "ol" else "-"
            self.parts.append(f"\n{marker} ")
        elif tag == "blockquote":
            self.parts.append("\n> ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "pre":
            self.parts.append("\n\n```text\n")
        elif tag == "code":
            self.parts.append("`")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote"}:
            self.parts.append("\n")
        elif tag in {"ul", "ol"} and self.list_stack:
            self.list_stack.pop()
            self.parts.append("\n")
        elif tag == "pre":
            self.parts.append("\n```\n")
        elif tag == "code":
            self.parts.append("`")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def html_to_markdown(html: str) -> str:
    parser = _MarkdownHTMLParser()
    parser.feed(html or "")
    lines = [line.rstrip() for line in "".join(parser.parts).splitlines()]
    compact: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        compact.append(line)
        previous_blank = blank
    return "\n".join(compact).strip() + "\n"
