from __future__ import annotations

from pathlib import Path

from app.services.ingestion.artifact_writer import IngestionArtifactWriter
from app.services.ingestion.types import IngestionRequest, ParsedDocument, ParsedPage, TextItem
from app.utils.storage_paths import note_output_dir


class WebIngestionAdapter:
    def __init__(self, output_dir: Path | None = None):
        self.output_dir = Path(output_dir or note_output_dir())

    def ingest(self, task_id: str, page_context: dict):
        url = page_context.get("url", "")
        title = page_context.get("title") or url or "网页"
        text = page_context.get("main_text") or page_context.get("main_text_summary") or ""
        headings = page_context.get("headings") or []
        request = IngestionRequest(
            job_id=task_id,
            file_url=url,
            file_name=title,
            source_type="web",
            resource_type="web",
            content_type="text/html",
        )
        parsed = ParsedDocument(
            job_id=task_id,
            title=title,
            source_type="web",
            resource_type="web",
            parser_name="web_context",
            parser_backend="web_context",
            pages=[
                ParsedPage(
                    page_number=1,
                    text=text,
                    text_items=[
                        TextItem(
                            text=text,
                            page_number=1,
                            source="web_context",
                            confidence=1.0 if text.strip() else 0.0,
                        )
                    ]
                    if text.strip()
                    else [],
                    confidence=1.0 if text.strip() else 0.0,
                    warnings=[] if text.strip() else ["empty_web_page"],
                )
            ],
            quality={
                "parser": "web_context",
                "heading_count": len(headings),
                "text_length": len(text),
            },
            metadata={"url": url, "headings": headings},
        )
        return IngestionArtifactWriter(output_dir=self.output_dir).write(request, parsed)
