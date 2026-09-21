from __future__ import annotations

import os

from app.services.ocr.base import OcrProvider
from app.services.ocr.local_stub import LocalStubOcrProvider
from app.services.ocr.rapid_ocr import RapidOcrProvider


def get_ocr_provider() -> OcrProvider:
    provider_name = (os.getenv("NOTEMELD_OCR_PROVIDER", "rapidocr") or "rapidocr").strip().lower()
    if provider_name in {"stub", "local_stub"}:
        return LocalStubOcrProvider()
    if provider_name in {"rapidocr", "rapid_ocr"}:
        return RapidOcrProvider()
    raise ValueError(f"不支持的 OCR provider: {provider_name}")
