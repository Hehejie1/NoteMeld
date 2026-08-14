from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol

from app.models.multisource_summary import FrameContextResult
from app.utils.storage_paths import note_output_dir


class FrameExtractor(Protocol):
    def extract(
        self,
        video_path: str,
        timestamps: list[float] | None = None,
        include_grid_images: bool = True,
    ) -> dict[str, Any]:
        ...


class VisionAnalyzer(Protocol):
    def analyze(self, image_path: str) -> dict[str, Any]:
        ...


class OcrProvider(Protocol):
    def extract_text(self, file_path: Path) -> dict[str, Any]:
        ...


class VideoReaderFrameExtractor:
    def __init__(
        self,
        *,
        grid_size: tuple[int, int] = (3, 3),
        frame_interval: int = 2,
        dedupe_enabled: bool = True,
    ):
        self.grid_size = grid_size
        self.frame_interval = frame_interval
        self.dedupe_enabled = dedupe_enabled

    def extract(
        self,
        video_path: str,
        timestamps: list[float] | None = None,
        include_grid_images: bool = True,
    ) -> dict[str, Any]:
        from app.utils.video_reader import VideoReader

        reader = VideoReader(
            video_path=video_path,
            grid_size=self.grid_size,
            frame_interval=self.frame_interval,
            dedupe_enabled=self.dedupe_enabled,
            frame_timestamps=timestamps,
        )
        frame_paths = reader.extract_frames()
        grid_paths = []
        grid_images = []
        if include_grid_images:
            for index, group in enumerate(reader.group_images(), start=1):
                if len(group) < reader.grid_size[0] * reader.grid_size[1]:
                    continue
                grid_paths.append(reader.concat_images(group, f"grid_{index}"))
            grid_images = reader.encode_images_to_base64(grid_paths)
        return {
            "frames": [
                {
                    "timestamp": reader.extract_time_from_filename(os.path.basename(path)),
                    "image_path": path,
                }
                for path in frame_paths
            ],
            "grid_images": grid_images,
        }


class VideoFrameCollector:
    def __init__(
        self,
        *,
        frame_extractor: FrameExtractor | None = None,
        vision_analyzer: VisionAnalyzer | None = None,
        ocr_provider: OcrProvider | None = None,
        output_dir: Path | None = None,
    ):
        self.frame_extractor = frame_extractor or VideoReaderFrameExtractor()
        self.vision_analyzer = vision_analyzer
        self.ocr_provider = ocr_provider
        self.output_dir = output_dir or note_output_dir()

    def collect(
        self,
        *,
        task_id: str,
        screenshot: bool,
        video_path: str | None = None,
        video_url: str | None = None,
        downloader=None,
        gpt=None,
        grid_size: list[int] | None = None,
        frame_timestamps: list[float] | None = None,
        timestamps: list[float] | None = None,
        allow_vision: bool = True,
    ) -> FrameContextResult:
        if not screenshot:
            return FrameContextResult(
                source="frames",
                status="skipped",
                mode="disabled",
                error="screenshot disabled",
            )

        cache_suffix = "frames_vision" if allow_vision else "frames_ocr"
        cache_path = self.output_dir / f"{task_id}_{cache_suffix}.json"
        cached = self._read_cache(cache_path)
        if cached:
            return cached

        resolved_timestamps = frame_timestamps if frame_timestamps is not None else timestamps
        try:
            resolved_video_path = self._resolve_video_path(video_path=video_path, video_url=video_url, downloader=downloader)
            extracted = self.frame_extractor.extract(
                resolved_video_path,
                timestamps=resolved_timestamps,
                include_grid_images=allow_vision,
            )
        except Exception as exc:
            return FrameContextResult(source="frames", status="failed", mode="disabled", error=str(exc))

        frame_records = []
        modes: set[str] = set()
        for raw_frame in extracted.get("frames") or []:
            frame = self._analyze_frame(raw_frame, allow_vision=allow_vision)
            frame_records.append(frame)
            modes.add(str(frame.get("mode") or "unknown"))

        mode = self._resolve_mode(modes)
        content = self._format_content(frame_records)
        result = FrameContextResult(
            source="frames",
            status="done" if frame_records else "skipped",
            content=content,
            confidence=self._average_confidence(frame_records),
            mode=mode,
            frames=frame_records,
            grid_images=list(extracted.get("grid_images") or []) if allow_vision else [],
            artifacts={"frame_count": len(frame_records), "video_path": resolved_video_path},
        )
        # Direct OCR and successful vision are stable cache modes. A temporary
        # vision failure that fell back to OCR must not suppress the next
        # analyzer attempt.
        if not allow_vision or mode == "vision":
            self._write_cache(cache_path, result)
        return result

    def _analyze_frame(self, raw_frame: dict[str, Any], *, allow_vision: bool) -> dict[str, Any]:
        image_path = str(raw_frame.get("image_path") or "")
        timestamp = float(raw_frame.get("timestamp") or 0.0)
        if allow_vision and self.vision_analyzer is not None:
            try:
                return self._normalize_vision_result(timestamp, image_path, self.vision_analyzer.analyze(image_path))
            except Exception as exc:
                return self._analyze_frame_with_ocr(timestamp, image_path, vision_error=str(exc))
        vision_error = "vision analyzer not configured" if allow_vision else "vision disabled by model capability"
        return self._analyze_frame_with_ocr(timestamp, image_path, vision_error=vision_error)

    def _normalize_vision_result(self, timestamp: float, image_path: str, result: dict[str, Any]) -> dict[str, Any]:
        text = str(result.get("detected_text") or result.get("text") or "").strip()
        summary = str(result.get("summary") or result.get("description") or text or "视觉模型完成画面识别").strip()
        return {
            "timestamp": timestamp,
            "image_path": image_path,
            "mode": "vision",
            "summary": summary,
            "text": text,
            "detected_text": text,
            "visual_type": result.get("visual_type") or "unknown",
            "confidence": float(result.get("confidence") or 0.7),
        }

    def _analyze_frame_with_ocr(self, timestamp: float, image_path: str, *, vision_error: str) -> dict[str, Any]:
        provider = self._get_ocr_provider()
        ocr_result = provider.extract_text(Path(image_path))
        text = str(ocr_result.get("text") or "").strip()
        confidence = ocr_result.get("confidence")
        return {
            "timestamp": timestamp,
            "image_path": image_path,
            "mode": "ocr",
            "fallback": "ocr",
            "summary": text,
            "text": text,
            "detected_text": text,
            "visual_type": "ocr_text",
            "confidence": float(confidence) if confidence is not None else (0.6 if text else 0.0),
            "ocr_engine": ocr_result.get("engine") or getattr(provider, "engine", "unknown"),
            "ocr_lines": list(ocr_result.get("lines") or []),
            "vision_error": vision_error,
        }

    def _get_ocr_provider(self) -> OcrProvider:
        if self.ocr_provider is not None:
            return self.ocr_provider
        from app.services.ocr.provider import get_ocr_provider

        self.ocr_provider = get_ocr_provider()
        return self.ocr_provider

    def _resolve_mode(self, modes: set[str]) -> str:
        if not modes:
            return "disabled"
        if modes == {"vision"}:
            return "vision"
        if modes == {"ocr"}:
            return "ocr"
        return "mixed"

    def _format_content(self, frames: list[dict[str, Any]]) -> str:
        lines = []
        for frame in frames:
            timestamp = float(frame.get("timestamp") or 0.0)
            mm = int(timestamp // 60)
            ss = int(timestamp % 60)
            summary = str(frame.get("summary") or frame.get("text") or "").strip()
            if summary:
                lines.append(f"{mm:02d}:{ss:02d} [{frame.get('mode')}] {summary}")
        return "\n".join(lines)

    def _average_confidence(self, frames: list[dict[str, Any]]) -> float:
        values = [float(frame.get("confidence") or 0.0) for frame in frames]
        return sum(values) / len(values) if values else 0.0

    def _read_cache(self, cache_path: Path) -> FrameContextResult | None:
        if not cache_path.exists():
            return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return FrameContextResult(**payload)
        except Exception:
            return None

    def _write_cache(self, cache_path: Path, result: FrameContextResult) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")

    def _resolve_video_path(self, *, video_path: str | None, video_url: str | None, downloader) -> str:
        if video_path:
            return str(video_path)
        if downloader is None or not video_url:
            raise ValueError("video_path 或 video_url + downloader 至少提供一组")
        return str(downloader.download_video(video_url))
