"""notemeld-ai Usage / UsageContext / UsageWriter 单测。

§7.1/§7.2 验收标准：
- UsageWriter.write() 调用现有 ``record_usage()``，不绕过
- 通过 ``SimpleNamespace`` 适配 token 字段名（input_tokens → prompt_tokens）
- 字段语义与旧 GPTFactory 路径 100% 一致
"""
from __future__ import annotations

import json
import pathlib
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.usage import Usage, UsageContext, UsageCost, UsageWriter  # noqa: E402


class UsageTest(unittest.TestCase):
    def test_default_usage_is_empty(self):
        u = Usage()
        self.assertIsNone(u.input_tokens)
        self.assertIsNone(u.output_tokens)
        self.assertIsNone(u.total_tokens)
        self.assertIsInstance(u.cost, UsageCost)

    def test_from_openai_usage_extracts_prompt_tokens(self):
        """从 OpenAI SDK usage 对象提取 token 数（非流式 response.usage）。"""
        sdk_usage = SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        u = Usage.from_openai_usage(sdk_usage)
        self.assertEqual(u.input_tokens, 100)
        self.assertEqual(u.output_tokens, 50)
        self.assertEqual(u.total_tokens, 150)

    def test_from_openai_usage_handles_none(self):
        u = Usage.from_openai_usage(None)
        self.assertIsNone(u.input_tokens)
        self.assertIsNone(u.output_tokens)
        self.assertIsNone(u.total_tokens)

    def test_from_openai_usage_handles_missing_attrs(self):
        """某些 provider 不返回 total_tokens，应容错为 None。"""
        sdk_usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        u = Usage.from_openai_usage(sdk_usage)
        self.assertEqual(u.input_tokens, 10)
        self.assertEqual(u.output_tokens, 5)
        self.assertIsNone(u.total_tokens)


class UsageContextTest(unittest.TestCase):
    def test_defaults(self):
        ctx = UsageContext(provider_id="p1", provider_name="DeepSeek", model_name="deepseek-chat")
        self.assertEqual(ctx.phase, "chat")
        self.assertIsNone(ctx.task_id)
        self.assertIsNone(ctx.platform)
        self.assertIsNone(ctx.video_id)
        self.assertIsNone(ctx.video_title)
        self.assertIsNone(ctx.request_meta)
        self.assertIsNone(ctx.started_at)
        self.assertIsNone(ctx.finished_at)

    def test_full_fields(self):
        started = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        finished = datetime(2026, 8, 1, 12, 0, 1, tzinfo=timezone.utc)
        ctx = UsageContext(
            provider_id="p1",
            provider_name="DeepSeek",
            model_name="deepseek-chat",
            phase="summarize",
            task_id="t1",
            platform="douyin",
            video_id="v1",
            video_title="标题",
            request_meta={"stage": "merge"},
            started_at=started,
            finished_at=finished,
        )
        self.assertEqual(ctx.phase, "summarize")
        self.assertEqual(ctx.task_id, "t1")
        self.assertEqual(ctx.platform, "douyin")
        self.assertEqual(ctx.request_meta, {"stage": "merge"})


class UsageWriterTest(unittest.TestCase):
    """§7.1 关键：UsageWriter 必须复用 record_usage()，字段 100% 兼容。"""

    def test_write_success_calls_record_usage_with_correct_payload(self):
        """成功路径：token 数通过 SimpleNamespace 适配为 prompt_tokens/completion_tokens/total_tokens。"""
        captured = {}

        def fake_record_usage(**kwargs):
            captured.update(kwargs)

        usage = Usage(input_tokens=100, output_tokens=50, total_tokens=150)
        ctx = UsageContext(
            provider_id="prov_1",
            provider_name="DeepSeek",
            model_name="deepseek-chat",
            phase="summarize",
            task_id="task_123",
            platform="douyin",
            video_id="vid_456",
            video_title="测试视频",
            request_meta={"stage": "chunk_1"},
        )

        with patch("app.ai.usage.record_usage", side_effect=fake_record_usage):
            UsageWriter.write(usage, ctx, status="success")

        # 验证 record_usage 被调用，且参数完整传递
        self.assertEqual(captured["provider_id"], "prov_1")
        self.assertEqual(captured["provider_name"], "DeepSeek")
        self.assertEqual(captured["model_name"], "deepseek-chat")
        self.assertEqual(captured["phase"], "summarize")
        self.assertEqual(captured["task_id"], "task_123")
        self.assertEqual(captured["platform"], "douyin")
        self.assertEqual(captured["video_id"], "vid_456")
        self.assertEqual(captured["video_title"], "测试视频")
        self.assertEqual(captured["status"], "success")
        self.assertIsNone(captured["error_message"])
        self.assertEqual(captured["request_meta"], {"stage": "chunk_1"})

        # 关键：token 字段通过 SimpleNamespace 适配
        response_usage = captured["response_usage"]
        self.assertEqual(response_usage.prompt_tokens, 100)
        self.assertEqual(response_usage.completion_tokens, 50)
        self.assertEqual(response_usage.total_tokens, 150)

        # 时间戳：未指定时使用 now()，但 started_at 应早于等于 finished_at
        self.assertIsInstance(captured["started_at"], datetime)
        self.assertIsInstance(captured["finished_at"], datetime)
        self.assertLessEqual(captured["started_at"], captured["finished_at"])

    def test_write_failed_with_error_message(self):
        """失败路径：status=failed + error_message，token 为 None。"""
        captured = {}

        def fake_record_usage(**kwargs):
            captured.update(kwargs)

        ctx = UsageContext(
            provider_id="p1",
            provider_name="DeepSeek",
            model_name="deepseek-chat",
            phase="chat",
        )

        with patch("app.ai.usage.record_usage", side_effect=fake_record_usage):
            UsageWriter.write(
                Usage(),
                ctx,
                status="failed",
                error_message="connection reset",
            )

        self.assertEqual(captured["status"], "failed")
        self.assertEqual(captured["error_message"], "connection reset")
        # token 字段为 None
        self.assertIsNone(captured["response_usage"].prompt_tokens)
        self.assertIsNone(captured["response_usage"].completion_tokens)
        self.assertIsNone(captured["response_usage"].total_tokens)

    def test_write_uses_provided_timestamps_when_present(self):
        """UsageContext 显式传入 started_at/finished_at 时应被使用，不被 now() 覆盖。"""
        captured = {}

        def fake_record_usage(**kwargs):
            captured.update(kwargs)

        started = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
        finished = datetime(2026, 8, 1, 10, 0, 5, tzinfo=timezone.utc)
        ctx = UsageContext(
            provider_id="p1",
            provider_name="P",
            model_name="m",
            started_at=started,
            finished_at=finished,
        )

        with patch("app.ai.usage.record_usage", side_effect=fake_record_usage):
            UsageWriter.write(Usage(), ctx)

        self.assertEqual(captured["started_at"], started)
        self.assertEqual(captured["finished_at"], finished)

    def test_write_swallows_record_usage_exceptions(self):
        """§7.1：record_usage 抛错时 UsageWriter 不能阻塞主流程，只 log warning。"""
        ctx = UsageContext(provider_id="p1", provider_name="P", model_name="m")

        with patch("app.ai.usage.record_usage", side_effect=RuntimeError("db down")):
            # 不应抛出
            UsageWriter.write(Usage(input_tokens=1), ctx)


if __name__ == "__main__":
    unittest.main()
