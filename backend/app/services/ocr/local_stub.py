from __future__ import annotations

from pathlib import Path

from app.services.ocr.base import OcrResult


class LocalStubOcrProvider:
    engine = "stub"

    def extract_text(self, file_path: Path) -> OcrResult:
        sidecar = file_path.with_suffix(f"{file_path.suffix}.ocr.txt")
        if sidecar.exists():
            text = sidecar.read_text(encoding="utf-8", errors="ignore").strip()
            lines = [
                {
                    "id": f"line-{index}",
                    "text": line,
                    "bbox": None,
                    "order": index,
                    "page": 1,
                    "confidence": 1.0,
                }
                for index, line in enumerate(item for item in text.splitlines() if item.strip())
            ]
            return {
                "text": text,
                "engine": self.engine,
                "confidence": None,
                "pages": [{"page": 1, "text": text, "confidence": 1.0}] if text else [],
                "lines": lines,
            }
        raise ValueError("当前环境未启用 OCR 引擎，请先配置 OCR provider")
