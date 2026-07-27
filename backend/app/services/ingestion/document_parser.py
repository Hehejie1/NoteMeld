from __future__ import annotations

from pathlib import Path

from app.services.file_ingest_service import resolve_uploaded_file_path
from app.services.ingestion.errors import IngestionError
from app.services.ingestion.parser_backends import (
    ImageOcrParser,
    OfficeTextFallbackParser,
    PdfFallbackParser,
    TextFallbackParser,
)
from app.services.ingestion.types import IngestionRequest, ParsedDocument


def _extension_of(file_name: str) -> str:
    return Path(file_name or "").suffix.lower().lstrip(".")


class DocumentParser:
    def __init__(self, liteparse_adapter=None):
        self.liteparse_adapter = liteparse_adapter
        self.pdf_parser = PdfFallbackParser()
        self.text_parser = TextFallbackParser()
        self.office_parser = OfficeTextFallbackParser()
        self.image_parser = ImageOcrParser()

    def parse(self, request: IngestionRequest) -> ParsedDocument:
        path = resolve_uploaded_file_path(request.file_url)
        ext = _extension_of(request.file_name)

        try:
            if ext == "pdf":
                parsed = self._try_liteparse(path, request)
                return parsed or self.pdf_parser.parse(path, request)
            if ext in {"txt", "rtf", "md", "markdown"}:
                return self.text_parser.parse(path, request)
            if ext in {"doc", "docx"}:
                parsed = self._try_liteparse(path, request)
                return parsed or self.office_parser.parse(path, request)
            if ext in {"ppt", "pptx"}:
                parsed = self._try_liteparse(path, request)
                return parsed or self.office_parser.parse(path, request)
            if ext in {"png", "jpg", "jpeg", "webp"}:
                return self.image_parser.parse(path, request)
        except IngestionError:
            raise
        except Exception as exc:
            raise IngestionError(
                code="document_parse_failed",
                message=f"文档解析失败：{exc}",
                stage="parsing",
                recoverable=True,
                user_action="请确认文件未损坏，或转换为 PDF 后重试",
            ) from exc

        return self.text_parser.parse(path, request)

    def _try_liteparse(self, path: Path, request: IngestionRequest) -> ParsedDocument | None:
        if self.liteparse_adapter is None:
            return None
        return self.liteparse_adapter.parse(path, request)
