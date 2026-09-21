from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Protocol

from app.enmus.note_enums import DownloadQuality
from app.models.audio_model import AudioDownloadResult
from app.models.multisource_summary import TranscriptContextResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.utils.storage_paths import note_output_dir


class TranscriptDownloader(Protocol):
    def download_subtitles(self, video_url: str, output_dir: str | None = None, langs: list | None = None) -> TranscriptResult | None:
        ...

    def download(
        self,
        video_url: str,
        output_dir: str | None = None,
        quality: DownloadQuality | str = "fast",
        need_video: bool = False,
        skip_download: bool = False,
    ) -> AudioDownloadResult:
        ...


class TranscriptTranscriber(Protocol):
    def transcript(self, file_path: str) -> TranscriptResult:
        ...


class TranscriptCollector:
    def __init__(self, *, output_dir: Path | None = None):
        self.output_dir = output_dir or note_output_dir()

    def collect(
        self,
        *,
        task_id: str,
        video_url: str,
        downloader: TranscriptDownloader,
        transcriber: TranscriptTranscriber | None = None,
        quality: DownloadQuality | str = "fast",
        output_path: str | None = None,
    ) -> TranscriptContextResult:
        transcript_cache = self.output_dir / f"{task_id}_transcript.json"
        audio_cache = self.output_dir / f"{task_id}_audio.json"

        cached_transcript = self._read_transcript_cache(transcript_cache)
        if cached_transcript is not None:
            audio_meta = self._load_or_download_audio(
                cache_path=audio_cache,
                downloader=downloader,
                video_url=video_url,
                quality=quality,
                output_path=output_path,
                skip_download=True,
            )
            return self._build_result(mode="cache", transcript=cached_transcript, audio_meta=audio_meta)

        subtitle = self._load_subtitle(video_url=video_url, downloader=downloader)
        if subtitle is not None:
            self._write_json(transcript_cache, asdict(subtitle))
            audio_meta = self._load_or_download_audio(
                cache_path=audio_cache,
                downloader=downloader,
                video_url=video_url,
                quality=quality,
                output_path=output_path,
                skip_download=True,
            )
            return self._build_result(mode="subtitle", transcript=subtitle, audio_meta=audio_meta)

        audio_meta = self._load_or_download_audio(
            cache_path=audio_cache,
            downloader=downloader,
            video_url=video_url,
            quality=quality,
            output_path=output_path,
            skip_download=False,
        )
        if transcriber is None:
            return TranscriptContextResult(
                source="transcript",
                status="failed",
                mode="audio",
                error="transcriber is not configured",
                audio_meta=audio_meta,
            )
        try:
            transcript = self._normalize_transcript(transcriber.transcript(audio_meta.file_path))
        except Exception as exc:
            return TranscriptContextResult(source="transcript", status="failed", mode="audio", error=str(exc), audio_meta=audio_meta)
        if transcript is None:
            return TranscriptContextResult(
                source="transcript",
                status="failed",
                mode="audio",
                error="transcript result is empty",
                audio_meta=audio_meta,
            )
        self._write_json(transcript_cache, asdict(transcript))
        return self._build_result(mode="audio", transcript=transcript, audio_meta=audio_meta)

    def _load_subtitle(self, *, video_url: str, downloader: TranscriptDownloader) -> TranscriptResult | None:
        try:
            return self._normalize_transcript(downloader.download_subtitles(video_url))
        except Exception:
            return None

    def _load_or_download_audio(
        self,
        *,
        cache_path: Path,
        downloader: TranscriptDownloader,
        video_url: str,
        quality: DownloadQuality | str,
        output_path: str | None,
        skip_download: bool,
    ) -> AudioDownloadResult:
        cached = self._read_audio_cache(cache_path)
        if cached is not None:
            return cached
        audio = downloader.download(
            video_url=video_url,
            output_dir=output_path,
            quality=quality,
            need_video=False,
            skip_download=skip_download,
        )
        self._write_json(cache_path, asdict(audio))
        return audio

    def _build_result(
        self,
        *,
        mode: str,
        transcript: TranscriptResult,
        audio_meta: AudioDownloadResult | None,
    ) -> TranscriptContextResult:
        segment_count = len(transcript.segments or [])
        return TranscriptContextResult(
            source="transcript",
            status="done",
            content=transcript.full_text,
            confidence=0.9 if mode in {"cache", "subtitle"} else 0.8,
            mode=mode,
            transcript=transcript,
            audio_meta=audio_meta,
            artifacts={
                "language": transcript.language,
                "segment_count": segment_count,
                "has_audio_meta": audio_meta is not None,
            },
        )

    def _read_transcript_cache(self, cache_path: Path) -> TranscriptResult | None:
        if not cache_path.exists():
            return None
        try:
            return self._normalize_transcript(json.loads(cache_path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def _read_audio_cache(self, cache_path: Path) -> AudioDownloadResult | None:
        if not cache_path.exists():
            return None
        try:
            return AudioDownloadResult(**json.loads(cache_path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def _normalize_transcript(self, transcript: TranscriptResult | dict[str, Any] | None) -> TranscriptResult | None:
        if transcript is None:
            return None
        payload = asdict(transcript) if is_dataclass(transcript) else dict(transcript)
        full_text = str(payload.get("full_text") or "").strip()
        segments = []
        for item in payload.get("segments") or []:
            segment = asdict(item) if is_dataclass(item) else dict(item)
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                TranscriptSegment(
                    start=float(segment.get("start") or 0),
                    end=float(segment.get("end") or 0),
                    text=text,
                )
            )
        if not segments and full_text:
            segments.append(TranscriptSegment(start=0, end=0, text=full_text))
        if not segments:
            return None
        return TranscriptResult(
            language=payload.get("language"),
            full_text=full_text or " ".join(segment.text for segment in segments),
            segments=segments,
            raw=payload.get("raw"),
        )

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
