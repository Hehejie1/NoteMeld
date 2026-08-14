import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock
from types import SimpleNamespace


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

sys.modules.setdefault("gmssl", SimpleNamespace(sm3=SimpleNamespace(), func=SimpleNamespace()))
sys.modules.setdefault("kombu", SimpleNamespace(uuid=lambda: "test-uuid"))
sys.modules.setdefault("ffmpeg", SimpleNamespace())
transcriber_provider_module = types.ModuleType("app.transcriber.transcriber_provider")
transcriber_provider_module.get_transcriber = lambda *args, **kwargs: object()
transcriber_provider_module._transcribers = {"fake": object}
sys.modules.setdefault("app.transcriber.transcriber_provider", transcriber_provider_module)

for module_name, class_name in {
    "app.downloaders.bilibili_downloader": "BilibiliDownloader",
    "app.downloaders.douyin_downloader": "DouyinDownloader",
    "app.downloaders.local_downloader": "LocalDownloader",
    "app.downloaders.youtube_downloader": "YoutubeDownloader",
}.items():
    module = types.ModuleType(module_name)
    setattr(module, class_name, type(class_name, (), {}))
    sys.modules.setdefault(module_name, module)

from app.models.multisource_summary import (  # noqa: E402
    CollectorResult,
    FrameContextResult,
    MultiSourceSummaryBundle,
    WebSearchResult,
)
from app.models.audio_model import AudioDownloadResult  # noqa: E402
from app.models.summary_plan import SummaryPlan  # noqa: E402
from app.models.transcriber_model import TranscriptResult, TranscriptSegment  # noqa: E402
from app.renderers.note_renderer import NoteRenderer  # noqa: E402
from app.services.context_normalizer import ContextNormalizer  # noqa: E402
from app.services.summary_refine_engine import SummaryRefineEngine  # noqa: E402

# 其他测试文件（如 test_core_note_task_status_api.py）会用 sys.modules.setdefault
# 注册一个仅含 NoteGenerator/logger 的 app.services.note stub。若不弹出，下面的
# import 会拿到 stub（无 NOTE_OUTPUT_DIR，NoteGenerator 为空类），导致本测试无法
# 执行真实的 generate() 逻辑。这里强制弹出 stub，确保加载真实模块。
sys.modules.pop("app.services.note", None)
from app.services import note as note_service  # noqa: E402


class TestMultiSourceSummaryContracts(unittest.TestCase):
    def test_default_collector_result_is_non_blocking(self):
        result = CollectorResult(source="web_search", status="skipped")

        self.assertEqual(result.source, "web_search")
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.content, "")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.artifacts, {})

    def test_bundle_carries_three_source_results(self):
        bundle = MultiSourceSummaryBundle(
            task_id="task-1",
            source_url="https://example.com/video",
            platform="youtube",
            title="Demo",
            audio_meta=None,
            transcript=None,
            web_search=WebSearchResult(
                source="web_search",
                status="done",
                content="外部资料",
                sources=[{"title": "Source", "url": "https://example.com"}],
            ),
            frame_context=FrameContextResult(
                source="frames",
                status="done",
                content="00:10 画面展示表格",
                mode="ocr",
                frames=[{"timestamp": 10, "text": "表格"}],
                grid_images=["data:image/jpeg;base64,abc"],
            ),
        )

        self.assertEqual(bundle.web_search.sources[0]["title"], "Source")
        self.assertEqual(bundle.frame_context.mode, "ocr")
        self.assertEqual(bundle.frame_context.frames[0]["timestamp"], 10)


class TestMultiSourceContextContracts(unittest.TestCase):
    def test_weighted_pack_includes_search_and_vision_blocks(self):
        audio_meta = AudioDownloadResult(
            file_path="/tmp/audio.mp3",
            title="视频标题",
            duration=60,
            cover_url=None,
            platform="youtube",
            video_id="v1",
            raw_info={"description": "描述"},
        )
        transcript = TranscriptResult(
            language="zh",
            full_text="字幕文本",
            segments=[TranscriptSegment(start=0, end=1, text="字幕文本")],
        )
        summary_input = ContextNormalizer().from_video_task(
            task_id="task-1",
            video_url="https://example.com/video",
            platform="youtube",
            audio_meta=audio_meta,
            transcript=transcript,
            user_options={
                "web_search_context": "搜索资料",
                "frame_context": "画面资料",
            },
        )

        pack = ContextNormalizer().build_weighted_pack(summary_input)

        sources = [block.source_type for block in pack.context_blocks]
        self.assertIn("search", sources)
        self.assertIn("vision", sources)

    def test_note_renderer_labels_search_and_describes_multisource_context(self):
        audio_meta = AudioDownloadResult(
            file_path="/tmp/audio.mp3",
            title="视频标题",
            duration=60,
            cover_url=None,
            platform="youtube",
            video_id="v1",
            raw_info={"description": "描述"},
        )
        transcript = TranscriptResult(
            language="zh",
            full_text="字幕文本",
            segments=[TranscriptSegment(start=0, end=1, text="字幕文本")],
        )
        summary_input = ContextNormalizer().from_video_task(
            task_id="task-1",
            video_url="https://example.com/video",
            platform="youtube",
            audio_meta=audio_meta,
            transcript=transcript,
            user_options={
                "web_search_context": "搜索资料",
                "frame_context": "画面资料",
            },
        )
        pack = ContextNormalizer().build_weighted_pack(summary_input)
        plan = SummaryPlan(
            input_id="task-1",
            output_type="note_markdown",
            strategy="single_pass",
            context_policy={"final": ["search", "vision"]},
        )

        renderer = NoteRenderer()
        final_context = renderer.build_final_context(pack, plan)
        extras = renderer.build_extras_with_context(None, pack, plan)

        self.assertIn("## 网页搜索补充上下文", final_context)
        self.assertIn("搜索资料", final_context)
        self.assertIn("视觉上下文是画面证据", extras)
        self.assertIn("网页搜索只作为外部背景和事实校验", extras)

    def test_refine_map_uses_only_original_user_extras_and_final_gets_auxiliary_context(self):
        audio_meta = AudioDownloadResult(
            file_path="/tmp/audio.mp3",
            title="视频标题",
            duration=60,
            cover_url=None,
            platform="youtube",
            video_id="v1",
            raw_info={},
        )
        transcript = TranscriptResult(
            language="zh",
            full_text="字幕一 字幕二",
            segments=[
                TranscriptSegment(start=0, end=1, text="字幕一"),
                TranscriptSegment(start=1, end=2, text="字幕二"),
            ],
        )
        summary_input = ContextNormalizer().from_video_task(
            task_id="task-map-final",
            video_url="https://example.com/video",
            platform="youtube",
            audio_meta=audio_meta,
            transcript=transcript,
            user_options={
                "extras": "用户原始要求",
                "web_search_context": "搜索大上下文" * 500,
                "frame_context": "画面大上下文" * 500,
            },
        )
        pack = ContextNormalizer().build_weighted_pack(summary_input)
        plan = SummaryPlan(
            input_id="task-map-final",
            output_type="note_markdown",
            strategy="map_reduce",
            chunk_policy={"max_segments_per_chunk": 1},
            context_policy={"final": ["search", "vision"]},
        )

        captured = []

        class FakeGpt:
            def summarize(self, source):
                captured.append(source)
                return "map result" if source.segment else "# final"

        result = SummaryRefineEngine().run(
            task_id="task-map-final",
            title="视频标题",
            segments=transcript.segments,
            gpt=FakeGpt(),
            plan=plan,
            pack=pack,
            extras="用户原始要求",
            video_img_urls=[],
        )

        self.assertEqual(result.markdown, "# final")
        map_sources = [source for source in captured if source.segment]
        final_source = next(source for source in captured if not source.segment)
        self.assertEqual(len(map_sources), 2)
        for source in map_sources:
            self.assertIn("用户原始要求", source.extras)
            self.assertIn("长内容分块摘要阶段", source.extras)
            self.assertNotIn("搜索大上下文", source.extras)
            self.assertNotIn("画面大上下文", source.extras)
        self.assertIn("搜索大上下文", final_source.extras)
        self.assertIn("画面大上下文", final_source.extras)

    def test_empty_frame_context_does_not_create_vision_extra(self):
        generator = note_service.NoteGenerator.__new__(note_service.NoteGenerator)
        bundle = MultiSourceSummaryBundle(
            task_id="task-empty-frame",
            source_url="https://example.com/video",
            platform="youtube",
            title="视频标题",
            audio_meta=None,
            transcript=None,
            web_search=WebSearchResult(source="web_search", status="skipped"),
            frame_context=FrameContextResult(
                source="frames",
                status="done",
                content="",
                mode="ocr",
            ),
        )

        extras = generator._merge_multisource_extras("用户要求", bundle)

        self.assertEqual(extras, "用户要求")
        self.assertNotIn("视频画面补充上下文", extras)


class TestNoteGeneratorMultiSourceIntegration(unittest.TestCase):
    def test_generate_uses_multisource_collector_and_injects_auxiliary_context(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        original_note_output_dir = note_service.NOTE_OUTPUT_DIR
        note_service.NOTE_OUTPUT_DIR = pathlib.Path(temp_dir.name)
        self.addCleanup(lambda: setattr(note_service, "NOTE_OUTPUT_DIR", original_note_output_dir))

        generator = note_service.NoteGenerator.__new__(note_service.NoteGenerator)
        generator.transcriber = object()
        generator.video_path = None
        generator.video_img_urls = []

        transcript = TranscriptResult(
            language="zh",
            full_text="字幕文本",
            segments=[TranscriptSegment(start=0, end=1, text="字幕文本")],
        )
        audio_meta = AudioDownloadResult(
            file_path="/tmp/audio.mp3",
            title="视频标题",
            duration=60,
            cover_url=None,
            platform="youtube",
            video_id="v1",
            raw_info={"webpage_url": "https://example.com/video", "tags": []},
        )
        captured: dict[str, object] = {}

        class FakeCollector:
            def collect(self, **kwargs):
                captured["collector_kwargs"] = kwargs
                return MultiSourceSummaryBundle(
                    task_id=kwargs["task_id"],
                    source_url=kwargs["video_url"],
                    platform=kwargs["platform"],
                    title="视频标题",
                    audio_meta=audio_meta,
                    transcript=transcript,
                    web_search=WebSearchResult(
                        source="web_search",
                        status="done",
                        content="搜索资料",
                    ),
                    frame_context=FrameContextResult(
                        source="frames",
                        status="done",
                        content="画面资料",
                        mode="ocr",
                        artifacts={"video_path": "/tmp/video.mp4"},
                    ),
                )

        def fake_summarize(**kwargs):
            captured["summarize_kwargs"] = kwargs
            return "# 视频标题\n\n正文"

        def fake_post_process(**kwargs):
            captured["post_process_kwargs"] = kwargs
            return kwargs["markdown"] + "\n\npost-processed"

        with mock.patch.object(note_service, "MultiSourceVideoCollector", return_value=FakeCollector(), create=True), \
            mock.patch.object(note_service.NoteGenerator, "_get_downloader", return_value=object()), \
            mock.patch.object(note_service.NoteGenerator, "_get_gpt", return_value=SimpleNamespace(model="demo")), \
            mock.patch.object(note_service.NoteGenerator, "_download_media", return_value=audio_meta), \
            mock.patch.object(note_service.NoteGenerator, "_get_transcript", return_value=transcript), \
            mock.patch.object(note_service.NoteGenerator, "_update_status"), \
            mock.patch.object(note_service.NoteGenerator, "_summarize_text", side_effect=fake_summarize), \
            mock.patch.object(note_service.NoteGenerator, "_post_process_markdown", side_effect=fake_post_process), \
            mock.patch.object(note_service.NoteGenerator, "_save_metadata"), \
            mock.patch.object(note_service.NoteGenerator, "_schedule_summary_sidecars"), \
            mock.patch.object(note_service, "_run_transcript_ingestion_best_effort"), \
            mock.patch.object(
                note_service,
                "localize_remote_markdown_images",
                return_value=SimpleNamespace(markdown=None, assets=[]),
            ), \
            mock.patch.object(note_service, "write_markdown_assets_sidecar"):
            result = generator.generate(
                video_url="https://example.com/video",
                platform="youtube",
                task_id="task-1",
                provider_id="provider-1",
                _format=["screenshot", "link"],
                extras="用户补充",
            )

        collector_kwargs = captured["collector_kwargs"]
        self.assertIs(collector_kwargs["transcriber"], generator.transcriber)
        self.assertEqual(collector_kwargs["video_url"], "https://example.com/video")
        self.assertEqual(collector_kwargs["screenshot"], True)

        summarize_kwargs = captured["summarize_kwargs"]
        self.assertIs(summarize_kwargs["transcript"], transcript)
        self.assertIn("用户补充", summarize_kwargs["extras"])
        self.assertEqual(summarize_kwargs["extras"], "用户补充")
        self.assertEqual(summarize_kwargs["web_search_context"], "搜索资料")
        self.assertEqual(summarize_kwargs["frame_context"], "画面资料")
        self.assertFalse(captured["collector_kwargs"]["allow_vision"])

        post_process_kwargs = captured["post_process_kwargs"]
        self.assertEqual(post_process_kwargs["video_path"], pathlib.Path("/tmp/video.mp4"))
        self.assertEqual(result.transcript.full_text, "字幕文本")
        self.assertIn("post-processed", result.markdown)


if __name__ == "__main__":
    unittest.main()
