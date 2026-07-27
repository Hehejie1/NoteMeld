from __future__ import annotations

from pathlib import Path

from app.services.ingestion.types import IngestionRequest, ParsedDocument, ParsedPage, TextItem


class LiteParseAdapter:
    parser_name = "liteparse"
    parser_backend = "liteparse"

    def parse(self, path: Path, request: IngestionRequest) -> ParsedDocument | None:
        # Runtime integration is intentionally optional for desktop packaging.
        return None

    def from_liteparse_json(self, request: IngestionRequest, data: dict) -> ParsedDocument:
        pages: list[ParsedPage] = []
        text_item_count = 0

        for raw_page in data.get("pages", []):
            page_number = int(raw_page.get("page") or raw_page.get("page_number") or 1)
            text_items = [
                self._text_item(page_number, item)
                for item in raw_page.get("text_items", [])
                if str(item.get("text") or "").strip()
            ]
            text_item_count += len(text_items)
            page_text = str(raw_page.get("text") or "").strip()
            pages.append(
                ParsedPage(
                    page_number=page_number,
                    width=float(raw_page.get("width") or 0),
                    height=float(raw_page.get("height") or 0),
                    text=page_text,
                    text_items=text_items,
                    confidence=self._page_confidence(text_items, page_text),
                    warnings=[] if page_text or text_items else ["empty_page"],
                )
            )

        return ParsedDocument(
            job_id=request.job_id,
            title=Path(request.file_name or "").stem or "未命名文档",
            source_type=request.source_type,
            resource_type=request.resource_type,
            parser_name=self.parser_name,
            parser_backend=self.parser_backend,
            fallback_used=False,
            pages=pages,
            quality={
                "parser": self.parser_name,
                "parser_backend": self.parser_backend,
                "page_count": len(pages),
                "text_item_count": text_item_count,
                "empty_pages": sum(1 for page in pages if not page.text.strip()),
            },
            metadata={"file_name": request.file_name, "content_type": request.content_type or ""},
        )

    def _text_item(self, page_number: int, item: dict) -> TextItem:
        return TextItem(
            text=str(item.get("text") or ""),
            page_number=page_number,
            x=float(item.get("x") or 0),
            y=float(item.get("y") or 0),
            width=float(item.get("width") or 0),
            height=float(item.get("height") or 0),
            font_name=item.get("font_name"),
            font_size=item.get("font_size"),
            confidence=float(item.get("confidence") if item.get("confidence") is not None else 1.0),
            source=self.parser_name,
        )

    def _page_confidence(self, text_items: list[TextItem], text: str) -> float:
        if text_items:
            return round(sum(item.confidence for item in text_items) / len(text_items), 3)
        return 1.0 if text else 0.0
