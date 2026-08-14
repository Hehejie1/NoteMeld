import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.note_output_normalizer import normalize_note_output  # noqa: E402
from app.services.note_style_prompt_builder import build_note_style_instruction  # noqa: E402


class TestNoteOutputNormalizer(unittest.TestCase):
    def test_markdown_document_mislabeled_as_html_fence_is_unwrapped(self):
        content = "```html\n# AI 产品经理\n\n## 核心结论\n正文\n```"

        normalized = normalize_note_output(content, ["markdown"])

        self.assertEqual(normalized, "# AI 产品经理\n\n## 核心结论\n正文")

    def test_real_html_is_converted_for_markdown_output(self):
        content = "<article><h1>标题</h1><p>正文</p></article>"

        normalized = normalize_note_output(content, ["markdown"])

        self.assertIn("# 标题", normalized)
        self.assertIn("正文", normalized)
        self.assertNotIn("<article", normalized)

    def test_internal_code_fence_is_preserved(self):
        content = "# 示例\n\n```python\nprint('ok')\n```\n\n解释"

        normalized = normalize_note_output(content, ["markdown"])

        self.assertEqual(normalized, content)

    def test_internal_html_code_fence_does_not_convert_whole_markdown(self):
        content = "# 示例\n\n```html\n<div>demo</div>\n```\n\n解释"

        normalized = normalize_note_output(content, ["markdown"])

        self.assertEqual(normalized, content)

    def test_real_html_can_start_with_anchor_element(self):
        content = '<a href="https://example.com">来源</a>'

        normalized = normalize_note_output(content, ["markdown"])

        self.assertIn("来源", normalized)
        self.assertNotIn("<a ", normalized)

    def test_real_html_can_start_with_semantic_element(self):
        content = "<aside><figure><img src=\"x.png\"><figcaption>图注</figcaption></figure></aside>"

        normalized = normalize_note_output(content, ["markdown"])

        self.assertIn("图注", normalized)
        self.assertNotIn("<aside", normalized)

    def test_inline_html_inside_markdown_does_not_convert_whole_document(self):
        content = "# 标题\n\n<div>局部强调</div>\n\n正文"

        normalized = normalize_note_output(content, ["markdown"])

        self.assertEqual(normalized, content)

    def test_source_attribution_before_document_fence_is_preserved(self):
        content = (
            "> 来源链接：https://example.com/video\n\n"
            "```html\n# 标题\n\n正文\n```"
        )

        normalized = normalize_note_output(content, ["markdown"])

        self.assertEqual(
            normalized,
            "> 来源链接：https://example.com/video\n\n# 标题\n\n正文",
        )

    def test_markdown_only_style_requests_bare_markdown(self):
        instruction = build_note_style_instruction({
            "name": "知识卡片",
            "description": "结构化知识",
            "output_formats": ["markdown"],
            "skeleton_html": "<article><h1>占位标题</h1></article>",
            "style_constraints": {},
            "rule_config": {},
            "example_content": {},
        })

        self.assertIn("直接生成裸 Markdown", instruction)
        self.assertIn("模型只返回 Markdown", instruction)
        self.assertNotIn("模型只返回 HTML", instruction)
        self.assertNotIn("CSS selector 对应", instruction)


if __name__ == "__main__":
    unittest.main()
