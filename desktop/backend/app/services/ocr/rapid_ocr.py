from __future__ import annotations

from pathlib import Path

from app.services.ocr.base import OcrLineResult, OcrPageResult, OcrResult


class RapidOcrProvider:
    engine = "rapidocr"

    def __init__(self):
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise ValueError(
                "当前环境未安装 rapidocr-onnxruntime，请先安装依赖并设置 NOTEMELD_OCR_PROVIDER=rapidocr"
            ) from exc
        self._client = RapidOCR()

    def extract_text(self, file_path: Path) -> OcrResult:
        result, _ = self._client(str(file_path))
        pages: list[OcrPageResult] = []
        lines: list[OcrLineResult] = []
        parts: list[str] = []
        confidences: list[float] = []

        for index, item in enumerate(result or []):
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            points = item[0] if item else None
            text_info = item[1]
            if not isinstance(text_info, (list, tuple)) or not text_info:
                continue
            text = str(text_info[0] or "").strip()
            if not text:
                continue
            confidence = None
            if len(text_info) > 1:
                try:
                    confidence = float(text_info[1])
                    confidences.append(confidence)
                except (TypeError, ValueError):
                    confidence = None
            parts.append(text)
            page_payload: OcrPageResult = {"page": 1, "text": text}
            if confidence is not None:
                page_payload["confidence"] = confidence
            pages.append(page_payload)
            bbox = None
            if isinstance(points, (list, tuple)) and len(points) >= 4:
                try:
                    xs = [float(point[0]) for point in points]
                    ys = [float(point[1]) for point in points]
                    bbox = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
                except (TypeError, ValueError, IndexError):
                    bbox = None
            lines.append(
                {
                    "id": f"line-{index}",
                    "text": text,
                    "bbox": bbox,
                    "order": index,
                    "page": 1,
                    "confidence": confidence,
                }
            )

        merged_text = "\n".join(parts).strip()
        return {
            "text": merged_text,
            "engine": self.engine,
            "confidence": (sum(confidences) / len(confidences)) if confidences else None,
            "pages": pages,
            "lines": lines,
        }
