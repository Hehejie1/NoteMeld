import pathlib
import sys
import tempfile
import unittest
import types
from types import SimpleNamespace
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

app_stub = types.ModuleType("app")
app_stub.__path__ = [str(ROOT / "desktop" / "backend" / "app")]
sys.modules.setdefault("app", app_stub)

knowledge_extractor_stub = types.ModuleType("app.services.knowledge_extractor")
knowledge_extractor_stub.KnowledgeExtractor = object
sys.modules.setdefault("app.services.knowledge_extractor", knowledge_extractor_stub)

from app.models.audio_model import AudioDownloadResult  # noqa: E402
from app.models.summary_input import MetaContext, SummaryInput  # noqa: E402
from app.models.transcriber_model import TranscriptResult, TranscriptSegment  # noqa: E402
from app.services.web_note import WebNoteGenerator, _WebVideoCollection  # noqa: E402


class _FakeGpt:
    def summarize(self, source):
        return """
<article class="notemeld-note-style" data-template-title="知识卡片">
  <header class="note-summary"><h1>页面标题</h1></header>
  <section class="note-section"><h2>核心结论</h2><p>这是结论。</p></section>
</article>
""".strip()

    def set_usage_context(self, context):
        self.context = context


class TestWebNoteContracts(unittest.TestCase):
    def test_web_note_converts_style_html_to_markdown_before_saving(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = pathlib.Path(tmp_dir)
            summary_input = SummaryInput(
                input_id="task-1",
                input_type="web_video_link",
                source_url="https://www.bilibili.com/video/BV1mT421Y7mE",
                platform="web_link",
                title="页面标题",
                user_goal=None,
                user_options={"enable_wiki": False},
                page_context=None,
                transcript_context=None,
                vision_context=None,
                social_context=None,
                meta_context=MetaContext(resource_type="web_video_link"),
            )
            transcript = TranscriptResult(
                language="zh",
                full_text="这是字幕。",
                segments=[TranscriptSegment(start=0, end=1, text="这是字幕。")],
            )
            audio_meta = AudioDownloadResult(
                file_path="",
                title="页面标题",
                duration=1,
                cover_url=None,
                platform="bilibili",
                video_id="BV1mT421Y7mE",
                raw_info={},
            )
            collection = _WebVideoCollection(
                summary_input=summary_input,
                main_text=transcript.full_text,
                transcript=transcript,
                audio_meta=audio_meta,
                video_url="https://www.bilibili.com/video/BV1mT421Y7mE",
            )

            generator = WebNoteGenerator(gpt_factory=lambda *_: _FakeGpt())
            with patch.object(generator, "_output_dir", return_value=output_dir), patch.object(
                generator, "_collect_web_and_video", return_value=collection
            ), patch.object(
                generator, "_provider_name", return_value="provider-test"
            ), patch.object(generator, "_update_status"), patch.object(
                generator, "_write_sidecars"
            ), patch(
                "app.services.web_note._run_web_ingestion_best_effort"
            ), patch(
                "app.services.web_note.ContextNormalizer"
            ) as normalizer_cls, patch(
                "app.services.web_note.SummaryPlanner"
            ) as planner_cls, patch(
                "app.services.web_note.NoteRenderer"
            ) as renderer_cls:
                normalizer_cls.return_value.build_weighted_pack.return_value = SimpleNamespace()
                planner_cls.return_value.plan.return_value = SimpleNamespace()
                renderer_cls.return_value.build_extras_with_context.return_value = ""

                result = generator.generate(
                    web_url="https://www.bilibili.com/video/BV1mT421Y7mE",
                    task_id="task-1",
                    model_name="gpt-test",
                    provider_id="provider-test",
                    style="knowledge_card",
                )

            self.assertIsNotNone(result)
            self.assertNotIn("<article", result.markdown)
            self.assertIn("# 页面标题", result.markdown)
            self.assertIn("## 核心结论", result.markdown)
            self.assertIn("这是结论。", result.markdown)


if __name__ == "__main__":
    unittest.main()
