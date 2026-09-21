from app.services.ocr.base import OcrProvider, OcrResult
from app.services.ocr.provider import get_ocr_provider
from app.services.ocr.rapid_ocr import RapidOcrProvider

__all__ = ["OcrProvider", "OcrResult", "RapidOcrProvider", "get_ocr_provider"]
