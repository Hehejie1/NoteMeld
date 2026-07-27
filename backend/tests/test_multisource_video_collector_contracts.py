from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import asdict


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.models.audio_model import AudioDownloadResult  # noqa: E402
from app.models.multisource_summary import (  # noqa: E402
    FrameContextResult,
    MultiSourceSummaryBundle,
    TranscriptContextResult,
    WebSearchResult,
)
from app.models.transcriber_model import TranscriptResult, TranscriptSegment  # noqa: E402
from app.services.multisource_video_collector import MultiSourceVideoCollector  # noqa: E402
from app.services import web_search  # noqa: E402
from app.services.transcript_collector import TranscriptCollector  # noqa: E402
from app.services.video_frame_collector import VideoFrameCollector  # noqa: E402


class _FakeProvider:
    def search(self, query: str, limit: int = 5):
        return [
            {
                "title": "视频背景资料",
                "url": "https://example.com/a",
                "snippet": f"query={query}",
                "published_at": "2026-06-01",
                "confidence": 0.8,
            }
        ]


class _FakeFrameExtractor:
    def __init__(self):
        self.calls = 0

    def extract(self, video_path: str, timestamps=None):
        self.calls += 1
        return {
            "frames": [
                {"timestamp": 3.0, "image_path": "/tmp/frame_00_03.jpg"},
                {"timestamp": 8.0, "image_path": "/tmp/frame_00_08.jpg"},
            ],
            "grid_images": ["data:image/jpeg;base64,grid"],
        }


class _FakeVideoDownloader:
    def __init__(self):
        self.calls = []

    def download_video(self, video_url):
        self.calls.append(video_url)
        return "/tmp/downloaded-demo.mp4"


class _FakeTranscriptDownloader:
    def __init__(self, subtitle: TranscriptResult | None = None, audio_path: str = "/tmp/audio.m4a"):
        self.subtitle = subtitle
        self.audio_path = audio_path
        self.subtitle_calls = []
        self.download_calls = []

    def download_subtitles(self, video_url, output_dir=None, langs=None):
        self.subtitle_calls.append((video_url, output_dir, langs))
        return self.subtitle

    def download(self, video_url, output_dir=None, quality="fast", need_video=False, skip_download=False):
        self.download_calls.append(
            {
                "video_url": video_url,
                "output_dir": output_dir,
                "quality": quality,
                "need_video": need_video,
                "skip_download": skip_download,
            }
        )
        return AudioDownloadResult(
            file_path=self.audio_path,
            title="Demo",
            duration=12.0,
            cover_url=None,
            platform="youtube",
            video_id="demo",
            raw_info={"skip_download": skip_download},
        )


class _FakeTranscriber:
    def __init__(self, transcript: TranscriptResult):
        self.transcript_result = transcript
        self.calls = []

    def transcript(self, file_path: str):
        self.calls.append(file_path)
        return self.transcript_result


class _FailingVisionAnalyzer:
    def analyze(self, image_path: str):
        raise RuntimeError(f"vision failed for {image_path}")


class _FakeOcrProvider:
    engine = "fake-ocr"

    def __init__(self):
        self.calls = []

    def extract_text(self, file_path):
        self.calls.append(str(file_path))
        return {
            "text": f"OCR text from {file_path}",
            "engine": self.engine,
            "confidence": 0.82,
            "pages": [],
            "lines": [{"text": "OCR text", "confidence": 0.82}],
        }


class _ConcurrentWebCollector:
    def __init__(self, barrier: threading.Barrier):
        self.barrier = barrier
        self.calls = []

    def collect(self, **kwargs):
        self.calls.append(kwargs)
        self.barrier.wait(timeout=1)
        return WebSearchResult(source="web_search", status="done", content="搜索资料")


class _ConcurrentTranscriptCollector:
    def __init__(self, barrier: threading.Barrier):
        self.barrier = barrier
        self.calls = []

    def collect(self, **kwargs):
        self.calls.append(kwargs)
        self.barrier.wait(timeout=1)
        time.sleep(0.05)
        return TranscriptContextResult(
            source="transcript",
            status="done",
            content="字幕文本",
            mode="subtitle",
            transcript=TranscriptResult(
                language="zh",
                full_text="字幕文本",
                segments=[TranscriptSegment(start=0, end=1, text="字幕文本")],
            ),
            audio_meta=AudioDownloadResult(
                file_path="/tmp/audio.mp3",
                title="视频标题",
                duration=60,
                cover_url=None,
                platform="youtube",
                video_id="v1",
                raw_info={"description": "描述"},
            ),
        )


class _ConcurrentFrameCollector:
    def __init__(self, barrier: threading.Barrier):
        self.barrier = barrier
        self.calls = []

    def collect(self, **kwargs):
        self.calls.append(kwargs)
        self.barrier.wait(timeout=1)
        return FrameContextResult(source="frames", status="done", content="画面资料", mode="ocr")


class _FailingStatusReporter:
    def running(self, *args, **kwargs):
        raise FileNotFoundError("status tmp missing")

    def done(self, *args, **kwargs):
        raise FileNotFoundError("status tmp missing")

    def failed(self, *args, **kwargs):
        raise FileNotFoundError("status tmp missing")

    def skipped(self, *args, **kwargs):
        raise FileNotFoundError("status tmp missing")


class TestWebSearchCollectorContracts(unittest.TestCase):
    def test_web_search_collector_uses_provider_and_writes_cache(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            collector = web_search.WebSearchCollector(provider=_FakeProvider(), output_dir=output_dir)

            result = collector.collect(
                task_id="task-1",
                source_url="https://example.com/video",
                title="视频标题",
                platform="youtube",
                description="视频描述",
            )

            cache_path = output_dir / "task-1_web_search.json"
            self.assertTrue(cache_path.exists())

        self.assertIsInstance(result, WebSearchResult)
        self.assertEqual(result.status, "done")
        self.assertIn("视频背景资料", result.content)

    def test_web_search_collector_skips_when_provider_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            collector = web_search.WebSearchCollector(provider=None, output_dir=output_dir)

            result = collector.collect(
                task_id="task-1",
                source_url="https://example.com/video",
                title="视频标题",
                platform="youtube",
                description=None,
            )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.content, "")


class TestTranscriptCollectorContracts(unittest.TestCase):
    def test_transcript_collector_uses_cached_transcript_before_subtitles_or_audio(self):
        cached_transcript = TranscriptResult(
            language="zh",
            full_text="缓存字幕",
            segments=[TranscriptSegment(start=0, end=1, text="缓存字幕")],
            raw={"source": "cache"},
        )
        audio_transcript = TranscriptResult(
            language="zh",
            full_text="音频转写",
            segments=[TranscriptSegment(start=0, end=1, text="音频转写")],
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            (output_dir / "task-1_transcript.json").write_text(
                json.dumps(asdict(cached_transcript), ensure_ascii=False),
                encoding="utf-8",
            )
            downloader = _FakeTranscriptDownloader(
                subtitle=TranscriptResult(
                    language="zh",
                    full_text="平台字幕",
                    segments=[TranscriptSegment(start=0, end=1, text="平台字幕")],
                )
            )
            transcriber = _FakeTranscriber(audio_transcript)
            collector = TranscriptCollector(output_dir=output_dir)

            result = collector.collect(
                task_id="task-1",
                video_url="https://example.com/video",
                downloader=downloader,
            )

        self.assertIsInstance(result, TranscriptContextResult)
        self.assertEqual(result.status, "done")
        self.assertEqual(result.mode, "cache")
        self.assertEqual(result.transcript.full_text, "缓存字幕")
        self.assertEqual(result.audio_meta.title, "Demo")
        self.assertEqual(downloader.subtitle_calls, [])
        self.assertEqual(downloader.download_calls[0]["skip_download"], True)
        self.assertEqual(transcriber.calls, [])

    def test_transcript_collector_prefers_subtitles_and_caches_metadata_without_audio_download(self):
        subtitle = TranscriptResult(
            language="zh",
            full_text="平台字幕文本",
            segments=[TranscriptSegment(start=0, end=2, text="平台字幕文本")],
            raw={"source": "subtitle"},
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            downloader = _FakeTranscriptDownloader(subtitle=subtitle)
            transcriber = _FakeTranscriber(
                TranscriptResult(
                    language="zh",
                    full_text="不应调用",
                    segments=[TranscriptSegment(start=0, end=1, text="不应调用")],
                )
            )
            collector = TranscriptCollector(output_dir=output_dir)

            result = collector.collect(
                task_id="task-1",
                video_url="https://example.com/video",
                downloader=downloader,
                transcriber=transcriber,
                quality="medium",
                output_path="/tmp/out",
            )

            transcript_cache = output_dir / "task-1_transcript.json"
            audio_cache = output_dir / "task-1_audio.json"
            transcript_cache_exists = transcript_cache.exists()
            audio_cache_exists = audio_cache.exists()

        self.assertEqual(result.status, "done")
        self.assertEqual(result.mode, "subtitle")
        self.assertEqual(result.transcript.full_text, "平台字幕文本")
        self.assertEqual(result.audio_meta.title, "Demo")
        self.assertTrue(transcript_cache_exists)
        self.assertTrue(audio_cache_exists)
        self.assertEqual(downloader.download_calls[0]["skip_download"], True)
        self.assertEqual(downloader.download_calls[0]["quality"], "medium")
        self.assertEqual(transcriber.calls, [])

    def test_transcript_collector_uses_audio_cache_before_downloading_then_transcribes(self):
        audio_transcript = TranscriptResult(
            language="zh",
            full_text="音频转写文本",
            segments=[TranscriptSegment(start=0, end=3, text="音频转写文本")],
        )
        cached_audio = AudioDownloadResult(
            file_path="/tmp/cached-audio.m4a",
            title="Cached",
            duration=30.0,
            cover_url=None,
            platform="youtube",
            video_id="cached",
            raw_info={},
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            (output_dir / "task-1_audio.json").write_text(
                json.dumps(asdict(cached_audio), ensure_ascii=False),
                encoding="utf-8",
            )
            downloader = _FakeTranscriptDownloader(subtitle=None)
            transcriber = _FakeTranscriber(audio_transcript)
            collector = TranscriptCollector(output_dir=output_dir)

            result = collector.collect(
                task_id="task-1",
                video_url="https://example.com/video",
                downloader=downloader,
                transcriber=transcriber,
            )

            transcript_cache = output_dir / "task-1_transcript.json"
            transcript_cache_exists = transcript_cache.exists()

        self.assertEqual(result.status, "done")
        self.assertEqual(result.mode, "audio")
        self.assertEqual(result.audio_meta.file_path, "/tmp/cached-audio.m4a")
        self.assertEqual(result.transcript.full_text, "音频转写文本")
        self.assertTrue(transcript_cache_exists)
        self.assertEqual(downloader.download_calls, [])
        self.assertEqual(transcriber.calls, ["/tmp/cached-audio.m4a"])

    def test_transcript_collector_is_not_wired_into_note_generator_main_flow(self):
        note_service = (ROOT / "backend" / "app" / "services" / "note.py").read_text(encoding="utf-8")

        self.assertNotIn("TranscriptCollector", note_service)


class TestVideoFrameCollectorContracts(unittest.TestCase):
    def test_video_frame_collector_skips_when_screenshot_disabled(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            extractor = _FakeFrameExtractor()
            collector = VideoFrameCollector(frame_extractor=extractor, output_dir=pathlib.Path(tmp_dir))

            result = collector.collect(
                task_id="task-1",
                video_path="/tmp/demo.mp4",
                screenshot=False,
            )

        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.mode, "disabled")
        self.assertEqual(result.frames, [])
        self.assertEqual(extractor.calls, 0)

    def test_video_frame_collector_falls_back_to_ocr_when_vision_llm_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ocr_provider = _FakeOcrProvider()
            collector = VideoFrameCollector(
                frame_extractor=_FakeFrameExtractor(),
                vision_analyzer=_FailingVisionAnalyzer(),
                ocr_provider=ocr_provider,
                output_dir=pathlib.Path(tmp_dir),
            )

            result = collector.collect(
                task_id="task-1",
                video_path="/tmp/demo.mp4",
                screenshot=True,
            )

        self.assertEqual(result.status, "done")
        self.assertEqual(result.mode, "ocr")
        self.assertEqual(len(result.frames), 2)
        self.assertIn("OCR text from /tmp/frame_00_03.jpg", result.content)
        self.assertEqual(result.frames[0]["fallback"], "ocr")
        self.assertEqual(result.grid_images, ["data:image/jpeg;base64,grid"])
        self.assertEqual(ocr_provider.calls, ["/tmp/frame_00_03.jpg", "/tmp/frame_00_08.jpg"])

    def test_video_frame_collector_returns_cached_result_without_reprocessing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            extractor = _FakeFrameExtractor()
            collector = VideoFrameCollector(
                frame_extractor=extractor,
                vision_analyzer=_FailingVisionAnalyzer(),
                ocr_provider=_FakeOcrProvider(),
                output_dir=output_dir,
            )

            first = collector.collect(task_id="task-1", video_path="/tmp/demo.mp4", screenshot=True)
            second = collector.collect(task_id="task-1", video_path="/tmp/demo.mp4", screenshot=True)

        self.assertEqual(first.status, "done")
        self.assertEqual(second.status, "done")
        self.assertEqual(second.frames, first.frames)
        self.assertEqual(extractor.calls, 1)

    def test_video_frame_collector_accepts_downloader_video_url_contract(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            downloader = _FakeVideoDownloader()
            collector = VideoFrameCollector(
                frame_extractor=_FakeFrameExtractor(),
                vision_analyzer=_FailingVisionAnalyzer(),
                ocr_provider=_FakeOcrProvider(),
                output_dir=pathlib.Path(tmp_dir),
            )

            result = collector.collect(
                task_id="task-1",
                video_url="https://example.com/video",
                downloader=downloader,
                gpt=object(),
                screenshot=True,
                grid_size=[2, 2],
                frame_timestamps=[3, 8],
            )

        self.assertEqual(result.status, "done")
        self.assertEqual(result.mode, "ocr")
        self.assertEqual(downloader.calls, ["https://example.com/video"])


class TestMultiSourceVideoCollectorContracts(unittest.TestCase):
    def test_multisource_collector_parallelizes_three_sources_and_returns_bundle(self):
        barrier = threading.Barrier(3)
        web_collector = _ConcurrentWebCollector(barrier)
        transcript_collector = _ConcurrentTranscriptCollector(barrier)
        frame_collector = _ConcurrentFrameCollector(barrier)
        downloader = object()
        gpt = object()
        transcriber = object()
        collector = MultiSourceVideoCollector(
            web_search_collector=web_collector,
            transcript_collector=transcript_collector,
            frame_collector=frame_collector,
            max_workers=3,
            status_reporter=None,
        )

        bundle = collector.collect(
            task_id="task-1",
            video_url="https://example.com/video",
            platform="youtube",
            downloader=downloader,
            gpt=gpt,
            transcriber=transcriber,
            quality="medium",
            output_path="/tmp/out",
            screenshot=True,
            grid_size=[2, 2],
            frame_timestamps=[3, 8],
        )

        self.assertIsInstance(bundle, MultiSourceSummaryBundle)
        self.assertEqual(bundle.web_search.content, "搜索资料")
        self.assertEqual(bundle.transcript.full_text, "字幕文本")
        self.assertEqual(bundle.frame_context.content, "画面资料")
        self.assertEqual(bundle.audio_meta.title, "视频标题")
        self.assertEqual(web_collector.calls[0]["title"], "")
        self.assertIsNone(web_collector.calls[0]["description"])
        self.assertEqual(transcript_collector.calls[0]["downloader"], downloader)
        self.assertEqual(transcript_collector.calls[0]["transcriber"], transcriber)
        self.assertEqual(transcript_collector.calls[0]["quality"], "medium")
        self.assertEqual(frame_collector.calls[0]["video_url"], "https://example.com/video")
        self.assertEqual(frame_collector.calls[0]["downloader"], downloader)
        self.assertEqual(frame_collector.calls[0]["gpt"], gpt)
        self.assertTrue(frame_collector.calls[0]["screenshot"])
        self.assertEqual(frame_collector.calls[0]["grid_size"], [2, 2])
        self.assertEqual(frame_collector.calls[0]["frame_timestamps"], [3, 8])

    def test_status_reporter_failure_does_not_fail_collection(self):
        barrier = threading.Barrier(3)
        collector = MultiSourceVideoCollector(
            web_search_collector=_ConcurrentWebCollector(barrier),
            transcript_collector=_ConcurrentTranscriptCollector(barrier),
            frame_collector=_ConcurrentFrameCollector(barrier),
            max_workers=3,
            status_reporter=_FailingStatusReporter(),
        )

        bundle = collector.collect(
            task_id="task-1",
            video_url="https://example.com/video",
            platform="youtube",
            downloader=object(),
            gpt=object(),
            transcriber=object(),
            quality="medium",
            output_path="/tmp/out",
            screenshot=True,
            grid_size=[2, 2],
            frame_timestamps=[3, 8],
        )

        self.assertEqual(bundle.web_search.status, "done")
        self.assertEqual(bundle.transcript.full_text, "字幕文本")
        self.assertEqual(bundle.frame_context.status, "done")


if __name__ == "__main__":
    unittest.main()
