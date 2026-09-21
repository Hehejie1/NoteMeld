"""T10 迁移测试：note.py._get_gpt() → NotemeldGPT 适配器。

验收标准覆盖：
- §7.1 NotemeldGPT.create_chat_completion 走 notemeld-ai Models.complete()，usage 字段等价
- §7.2 非流式每次 attempt 写一条 usage（success/failed）
- §7.5 4 接口 0 差异（通过 payload 字段集合对齐间接验证）

设计：
- patch ``app.gpt.notemeld_gpt.create_models`` 返回注入了 fake AsyncOpenAI 的 Models
- patch ``app.services.usage_tracker.insert_usage_record`` 捕获 notemeld-ai 写入的 payload
- patch ``time.sleep`` 避免重试测试真实等待
- 验证 phase 3 级回退 / retry / OpenAI 形状返回 / summarize 编排继承 / from_config 保留 client
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.catalog import ModelCapabilities  # noqa: E402
from app.ai.models import Model, Models  # noqa: E402
from app.ai.provider import LLMContext, ProviderConfig  # noqa: E402
from app.ai.stream import CompleteResult  # noqa: E402
from app.ai.usage import Usage  # noqa: E402
from app.gpt.notemeld_gpt import NotemeldGPT  # noqa: E402
from app.gpt.universal_gpt import UniversalGPT  # noqa: E402
from app.gpt.provider_runtime import (  # noqa: E402
    ContextLimitExceededError,
    is_context_limit_error,
    normalize_model_error,
)
from app.gpt.token_budget import count_message_images  # noqa: E402
from app.models.gpt_model import GPTSource  # noqa: E402
from app.models.model_config import ModelConfig  # noqa: E402
from app.models.transcriber_model import TranscriptSegment  # noqa: E402


# ── 公共常量 ──────────────────────────────────────────────────

PROVIDER_ID = "prov_note_001"
PROVIDER_NAME = "DeepSeek"
MODEL_NAME = "deepseek-chat"
TASK_ID = "task_note_001"
PLATFORM = "douyin"
VIDEO_ID = "vid_note_001"
VIDEO_TITLE = "T10 迁移测试视频"
PROMPT_TOKENS = 200
COMPLETION_TOKENS = 80
TOTAL_TOKENS = PROMPT_TOKENS + COMPLETION_TOKENS


def make_usage():
    return Usage(
        input_tokens=PROMPT_TOKENS,
        output_tokens=COMPLETION_TOKENS,
        total_tokens=TOTAL_TOKENS,
    )


def make_canned_openai_response(content="这是笔记内容"):
    """构造 OpenAI 形状响应（provider.complete() 内部会转为 CompleteResult）。"""
    usage = SimpleNamespace(
        prompt_tokens=PROMPT_TOKENS,
        completion_tokens=COMPLETION_TOKENS,
        total_tokens=TOTAL_TOKENS,
    )
    message = SimpleNamespace(content=content, tool_calls=None)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice], usage=usage)


def make_fake_models(response=None, *, exc=None):
    """构造 Models 实例，内部 provider 注入 fake AsyncOpenAI client。

    Args:
        response: ``chat.completions.create`` 成功时返回的 OpenAI 形状响应。
        exc: ``chat.completions.create`` 抛出的异常（与 response 互斥）。
    """
    from app.ai.provider import OpenAICompatibleProvider

    config = ProviderConfig(
        provider_id=PROVIDER_ID,
        provider_name=PROVIDER_NAME,
        api_key="sk-test",
        base_url="https://api.deepseek.com/v1",
    )
    provider = OpenAICompatibleProvider(config)

    fake_async_client = MagicMock()
    fake_async_client.chat = MagicMock()
    fake_async_client.chat.completions = MagicMock()
    if exc is not None:
        fake_async_client.chat.completions.create = AsyncMock(side_effect=exc)
    else:
        fake_async_client.chat.completions.create = AsyncMock(return_value=response)
    provider._client = fake_async_client

    models = Models(model_service=MagicMock())
    model = Model(
        provider=provider,
        name=MODEL_NAME,
        capabilities=ModelCapabilities(supports_tool_calling=True),
        provider_id=PROVIDER_ID,
        provider_name=PROVIDER_NAME,
    )
    models.get_model = MagicMock(return_value=model)
    return models, model


def make_usage_context(phase="summarize"):
    """构造 set_usage_context 期望的字典。"""
    return {
        "task_id": TASK_ID,
        "provider_id": PROVIDER_ID,
        "provider_name": PROVIDER_NAME,
        "phase": phase,
        "platform": PLATFORM,
        "video_id": VIDEO_ID,
        "video_title": VIDEO_TITLE,
        "request_meta": {"link": False, "screenshot": False},
    }


def make_gpt(usage_context=None):
    """构造 NotemeldGPT 实例（带 usage_context）。"""
    gpt = NotemeldGPT(
        client=MagicMock(),  # 保留 client 字段，T11 wiki_page_merger 兼容
        model=MODEL_NAME,
        usage_context=usage_context or make_usage_context(),
        provider_id=PROVIDER_ID,
        provider_name=PROVIDER_NAME,
        base_url="https://api.deepseek.com/v1",
    )
    return gpt


# ── from_config：保留 sync OpenAI client ─────────────────────

class FromConfigTest(unittest.TestCase):
    """from_config 与 GPTFactory.from_config 签名一致，保留 self.client。"""

    def test_from_config_creates_notemeld_gpt_with_sync_client(self):
        """from_config 返回 NotemeldGPT 实例，self.client 是同步 OpenAI client。"""
        config = ModelConfig(
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
            model_name=MODEL_NAME,
            provider=PROVIDER_ID,
            name=PROVIDER_NAME,
        )
        gpt = NotemeldGPT.from_config(config)

        self.assertIsInstance(gpt, NotemeldGPT)
        self.assertEqual(gpt.model, MODEL_NAME)
        # self.client 必须存在（T11 wiki_page_merger 直接用 gpt.client.chat.completions.create）
        self.assertIsNotNone(gpt.client)
        self.assertTrue(hasattr(gpt.client, "chat"))
        self.assertTrue(hasattr(gpt.client.chat, "completions"))


# ── create_chat_completion 走 notemeld-ai ────────────────────

class CreateChatCompletionMigrationTest(unittest.TestCase):
    """create_chat_completion override：走 notemeld-ai，不走 self.client。"""

    def test_calls_notemeld_ai_not_self_client(self):
        """create_chat_completion 调 notemeld-ai Models.complete()，不调 self.client。"""
        canned = make_canned_openai_response("笔记内容")
        models, model = make_fake_models(response=canned)
        gpt = make_gpt()

        with patch("app.gpt.notemeld_gpt.create_models", return_value=models):
            response = gpt.create_chat_completion(
                messages=[{"role": "user", "content": "请生成笔记"}],
                phase_label="summarize",
            )

        # notemeld-ai provider 的 AsyncOpenAI client 被调
        model.provider._client.chat.completions.create.assert_called_once()
        # self.client（旧 OpenAI sync client）没被调
        gpt.client.chat.completions.create.assert_not_called()

    def test_returns_openai_shape_response(self):
        """返回 OpenAI 形状 response，兼容 _extract_message_content。"""
        canned = make_canned_openai_response("笔记内容 ABC")
        models, _ = make_fake_models(response=canned)
        gpt = make_gpt()

        with patch("app.gpt.notemeld_gpt.create_models", return_value=models):
            response = gpt.create_chat_completion(
                messages=[{"role": "user", "content": "x"}],
                phase_label="summarize",
            )

        # _extract_message_content 读 choices[0].message.content
        content = gpt._extract_message_content(response, "summarize")
        self.assertEqual(content, "笔记内容 ABC")

        # usage 字段名与 OpenAI 一致（prompt_tokens/completion_tokens/total_tokens）
        self.assertEqual(response.usage.prompt_tokens, PROMPT_TOKENS)
        self.assertEqual(response.usage.completion_tokens, COMPLETION_TOKENS)
        self.assertEqual(response.usage.total_tokens, TOTAL_TOKENS)

    def test_openai_shape_preserves_reasoning_and_finish_reason(self):
        result = CompleteResult(
            content="",
            thinking='BEGIN_JSON\n{"title":"T"}\nEND_JSON',
            finish_reason="length",
        )

        response = NotemeldGPT._to_openai_response(result)

        self.assertIn("BEGIN_JSON", response.choices[0].message.reasoning_content)
        self.assertEqual(response.choices[0].finish_reason, "length")

    def test_openai_shape_keeps_unknown_finish_reason_unknown(self):
        response = NotemeldGPT._to_openai_response(CompleteResult(content="ok"))

        self.assertIsNone(response.choices[0].finish_reason)

    def test_timeout_is_forwarded_to_notemeld_ai_provider(self):
        canned = make_canned_openai_response("笔记内容")
        models, model = make_fake_models(response=canned)
        gpt = make_gpt()

        with patch("app.gpt.notemeld_gpt.create_models", return_value=models):
            gpt.create_chat_completion(
                messages=[{"role": "user", "content": "x"}],
                phase_label="wiki_merge",
                timeout=17.0,
            )

        kwargs = model.provider._client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["timeout"], 17.0)

    def test_writes_one_usage_via_notemeld_ai(self):
        """§7.1 §7.2：成功时 notemeld-ai 写一条 usage，字段等价。"""
        canned = make_canned_openai_response("内容")
        models, _ = make_fake_models(response=canned)
        gpt = make_gpt()

        captured = []
        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append):
            gpt.create_chat_completion(
                messages=[{"role": "user", "content": "x"}],
                phase_label="summarize",
                request_meta={"chunk_index": 0},
            )

        self.assertEqual(len(captured), 1, "成功应只写一条 usage")
        payload = captured[0]
        self.assertEqual(payload["provider_id"], PROVIDER_ID)
        self.assertEqual(payload["provider_name"], PROVIDER_NAME)
        self.assertEqual(payload["model_name"], MODEL_NAME)
        self.assertEqual(payload["phase"], "summarize")
        self.assertEqual(payload["task_id"], TASK_ID)
        self.assertEqual(payload["platform"], PLATFORM)
        self.assertEqual(payload["video_id"], VIDEO_ID)
        self.assertEqual(payload["video_title"], VIDEO_TITLE)
        self.assertEqual(payload["prompt_tokens"], PROMPT_TOKENS)
        self.assertEqual(payload["completion_tokens"], COMPLETION_TOKENS)
        self.assertEqual(payload["total_tokens"], TOTAL_TOKENS)
        self.assertEqual(payload["status"], "success")
        self.assertIsNone(payload["error_message"])

        # request_meta_json 包含合并后的字段
        meta = json.loads(payload["request_meta_json"])
        self.assertEqual(meta["response_format"], "default")
        self.assertEqual(meta["chunk_index"], 0)
        self.assertEqual(meta["link"], False)

    def test_failed_writes_status_failed_usage(self):
        """§7.1：失败时 notemeld-ai 写一条 status=failed usage。"""
        # 用非 retryable 错误，避免重试
        models, _ = make_fake_models(exc=ValueError("non-retryable error"))
        gpt = make_gpt()

        captured = []
        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append):
            with self.assertRaises(ValueError):
                gpt.create_chat_completion(
                    messages=[{"role": "user", "content": "x"}],
                    phase_label="summarize",
                )

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["status"], "failed")
        self.assertIsNone(captured[0]["prompt_tokens"])


# ── phase 3 级回退（与 LegacyPhasePrecedenceTest 对齐） ──────

class PhasePrecedenceTest(unittest.TestCase):
    """phase 3 级回退：request_meta.stage > usage_context.phase > phase_label。"""

    def test_phase_uses_request_meta_stage_when_present(self):
        """request_meta.stage 覆盖 usage_context.phase。"""
        canned = make_canned_openai_response("x")
        models, _ = make_fake_models(response=canned)
        gpt = make_gpt(usage_context={**make_usage_context(), "phase": "summarize"})

        captured = []
        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append):
            gpt.create_chat_completion(
                messages=[{"role": "user", "content": "x"}],
                phase_label="fallback_label",
                request_meta={"stage": "chunk_1"},
            )

        self.assertEqual(captured[0]["phase"], "chunk_1")

    def test_phase_falls_back_to_usage_context_phase(self):
        """request_meta 无 stage 时用 usage_context.phase。"""
        canned = make_canned_openai_response("x")
        models, _ = make_fake_models(response=canned)
        gpt = make_gpt(usage_context={**make_usage_context(), "phase": "summarize"})

        captured = []
        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append):
            gpt.create_chat_completion(
                messages=[{"role": "user", "content": "x"}],
                phase_label="fallback_label",
                request_meta={"chunk_index": 0},  # 无 stage
            )

        self.assertEqual(captured[0]["phase"], "summarize")

    def test_phase_falls_back_to_phase_label(self):
        """request_meta 无 stage 且 usage_context 无 phase 时用 phase_label。"""
        canned = make_canned_openai_response("x")
        models, _ = make_fake_models(response=canned)
        # usage_context 不含 phase
        gpt = make_gpt(usage_context={
            "task_id": TASK_ID,
            "provider_id": PROVIDER_ID,
            "provider_name": PROVIDER_NAME,
            "platform": PLATFORM,
            "video_id": VIDEO_ID,
            "video_title": VIDEO_TITLE,
        })

        captured = []
        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append):
            gpt.create_chat_completion(
                messages=[{"role": "user", "content": "x"}],
                phase_label="merge",
                request_meta={"chunk_index": 0},
            )

        self.assertEqual(captured[0]["phase"], "merge")


# ── retry 逻辑（复用继承的 _is_retryable_error） ────────────

class RetryLogicTest(unittest.TestCase):
    """retry：retryable 错误重试 3 次，non-retryable 立即抛出。"""

    def test_retryable_error_retries_max_attempts(self):
        """retryable 错误重试到 max_retry_attempts 次，每次写一条 failed usage。"""
        # 每次都抛 retryable 错误
        models, _ = make_fake_models(exc=RuntimeError("error code: 429"))
        gpt = make_gpt()

        captured = []
        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append), \
             patch("app.gpt.notemeld_gpt.time.sleep"):  # 避免真实等待
            with self.assertRaises(RuntimeError):
                gpt.create_chat_completion(
                    messages=[{"role": "user", "content": "x"}],
                    phase_label="summarize",
                )

        # 3 次 attempt → 3 条 failed usage
        self.assertEqual(len(captured), 3)
        for payload in captured:
            self.assertEqual(payload["status"], "failed")

    def test_non_retryable_error_raises_immediately(self):
        """non-retryable 错误立即抛出，只写一条 failed usage。"""
        models, _ = make_fake_models(exc=ValueError("invalid input"))
        gpt = make_gpt()

        captured = []
        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append):
            with self.assertRaises(ValueError):
                gpt.create_chat_completion(
                    messages=[{"role": "user", "content": "x"}],
                    phase_label="summarize",
                )

        # 只 1 条 failed usage（不重试）
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["status"], "failed")

    def test_retry_succeeds_on_second_attempt(self):
        """第一次失败（retryable），第二次成功，写 1 failed + 1 success usage。"""
        from app.ai.provider import OpenAICompatibleProvider

        config = ProviderConfig(
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
        )
        provider = OpenAICompatibleProvider(config)

        call_count = [0]

        async def fake_create(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("error code: 503")
            # 第二次返回成功响应（OpenAI 形状）
            from types import SimpleNamespace
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content="成功内容", tool_calls=None),
                    finish_reason="stop",
                )],
                usage=SimpleNamespace(
                    prompt_tokens=PROMPT_TOKENS,
                    completion_tokens=COMPLETION_TOKENS,
                    total_tokens=TOTAL_TOKENS,
                ),
            )

        fake_async_client = MagicMock()
        fake_async_client.chat = MagicMock()
        fake_async_client.chat.completions = MagicMock()
        fake_async_client.chat.completions.create = AsyncMock(side_effect=fake_create)
        provider._client = fake_async_client

        models = Models(model_service=MagicMock())
        model = Model(
            provider=provider,
            name=MODEL_NAME,
            capabilities=ModelCapabilities(supports_tool_calling=True),
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
        )
        models.get_model = MagicMock(return_value=model)

        gpt = make_gpt()

        captured = []
        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record", side_effect=captured.append), \
             patch("app.gpt.notemeld_gpt.time.sleep"):
            response = gpt.create_chat_completion(
                messages=[{"role": "user", "content": "x"}],
                phase_label="summarize",
            )

        # 2 条 usage：1 failed + 1 success
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0]["status"], "failed")
        self.assertEqual(captured[1]["status"], "success")
        # 返回成功内容
        self.assertEqual(response.choices[0].message.content, "成功内容")

    def test_context_error_with_timeout_and_500_is_not_retried_or_logged_raw(self):
        raw = "error code: 500 timeout service unavailable; maximum context window is 4096; request 6492"
        models, model = make_fake_models(exc=RuntimeError(raw))
        gpt = make_gpt()

        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), patch(
            "app.gpt.notemeld_gpt.time.sleep"
        ) as sleep_spy, self.assertLogs("app.gpt.notemeld_gpt", level="ERROR") as logs:
            with self.assertRaises(ContextLimitExceededError) as exc_info:
                gpt.create_chat_completion(
                    messages=[{"role": "user", "content": "x"}],
                    phase_label="summarize",
                )

        self.assertEqual(model.provider._client.chat.completions.create.await_count, 1)
        sleep_spy.assert_not_called()
        self.assertEqual(exc_info.exception.code, "context_limit_exceeded")
        self.assertNotIn("6492", str(exc_info.exception))
        self.assertNotIn("6492", "\n".join(logs.output))

    def test_legacy_universal_context_error_is_not_retried_or_logged_raw(self):
        raw = "error code: 500 timeout; n_prompt_tokens=6492, n_ctx=4096"
        create = MagicMock(side_effect=RuntimeError(raw))
        client = MagicMock()
        client.chat.completions.create = create
        client.with_options.return_value = client
        gpt = UniversalGPT(
            client=client,
            model=MODEL_NAME,
            provider_id=PROVIDER_ID,
            provider_name=PROVIDER_NAME,
            context_window_tokens=4096,
        )

        with patch.object(gpt, "_record_usage"), patch(
            "app.gpt.universal_gpt.time.sleep"
        ) as sleep_spy, self.assertLogs("app.gpt.universal_gpt", level="ERROR") as logs:
            with self.assertRaises(ContextLimitExceededError):
                gpt.create_chat_completion(
                    messages=[{"role": "user", "content": "x"}],
                    phase_label="summarize",
                )

        self.assertEqual(create.call_count, 1)
        sleep_spy.assert_not_called()
        self.assertNotIn("6492", "\n".join(logs.output))


# ── summarize 编排继承（chunking + merge 通过适配器走 notemeld-ai） ──

class SummarizeInheritanceTest(unittest.TestCase):
    """summarize() 编排逻辑继承自 UniversalGPT，内部调 create_chat_completion 走 notemeld-ai。"""

    def test_summarize_single_chunk_calls_create_chat_completion(self):
        """单 chunk 场景：summarize 调 create_chat_completion（走 notemeld-ai）。"""
        canned = make_canned_openai_response("单 chunk 笔记")
        models, _ = make_fake_models(response=canned)
        gpt = make_gpt()

        # spy create_chat_completion 确认走 override
        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record"):
            with patch.object(
                gpt, "create_chat_completion",
                wraps=gpt.create_chat_completion,
            ) as spy:
                source = GPTSource(
                    title="测试视频",
                    segment=[TranscriptSegment(start=0.0, end=5.0, text="这是转写文本")],
                    tags=[],
                    _format=[],
                    style=None,
                    extras=None,
                    video_img_urls=[],
                    screenshot=False,
                    link=False,
                    checkpoint_key=None,
                )
                result = gpt.summarize(source)

        self.assertEqual(result, "单 chunk 笔记")
        spy.assert_called_once()

    def test_summarize_multi_chunk_merges_via_create_chat_completion(self):
        """多 chunk 场景：summarize 调多次 create_chat_completion（chunk + merge）。"""
        canned = make_canned_openai_response("片段")
        models, _ = make_fake_models(response=canned)
        gpt = make_gpt()

        # 动态计算 max_request_bytes：让单 segment 能放下，双 segment 放不下
        seg1 = TranscriptSegment(start=0.0, end=5.0, text="第一段转写文本内容比较长一些用于测试")
        seg2 = TranscriptSegment(start=5.0, end=10.0, text="第二段转写文本内容也比较长用于测试")
        single_bytes = gpt._estimate_messages_bytes(
            gpt.create_messages([seg1], title="测试视频", tags=[], video_img_urls=[],
                                _format=[], style=None, extras=None)
        )
        both_bytes = gpt._estimate_messages_bytes(
            gpt.create_messages([seg1, seg2], title="测试视频", tags=[], video_img_urls=[],
                                _format=[], style=None, extras=None)
        )
        gpt.max_request_bytes = (single_bytes + both_bytes) // 2

        with patch("app.gpt.notemeld_gpt.create_models", return_value=models), \
             patch("app.services.usage_tracker.insert_usage_record"):
            with patch.object(
                gpt, "create_chat_completion",
                wraps=gpt.create_chat_completion,
            ) as spy:
                source = GPTSource(
                    title="测试视频",
                    segment=[seg1, seg2],
                    tags=[],
                    _format=[],
                    style=None,
                    extras=None,
                    video_img_urls=[],
                    screenshot=False,
                    link=False,
                    checkpoint_key=None,
                )
                result = gpt.summarize(source)

        self.assertEqual(result, "片段")
        # 多 chunk + 至少一次 merge → create_chat_completion 被调多次
        self.assertGreater(spy.call_count, 1)

    def test_summarize_splits_on_saved_model_token_budget_below_byte_limit(self):
        gpt = make_gpt()
        gpt.context_window_tokens = 4096
        gpt.max_request_bytes = 45 * 1024 * 1024
        segments = [
            TranscriptSegment(start=0.0, end=5.0, text="a" * 5000),
            TranscriptSegment(start=5.0, end=10.0, text="b" * 5000),
        ]
        source = GPTSource(
            title="测试视频",
            segment=segments,
            tags=[],
            _format=[],
            style=None,
            extras=None,
            video_img_urls=[],
            screenshot=False,
            link=False,
            checkpoint_key=None,
        )

        with patch.object(gpt, "create_chat_completion", return_value=make_canned_openai_response("片段")) as spy:
            gpt.summarize(source)

        self.assertGreater(spy.call_count, 1)

    def test_summarize_rebuilds_text_budget_after_dropping_oversized_images(self):
        gpt = make_gpt()
        gpt.context_window_tokens = 2048
        gpt.max_request_bytes = 45 * 1024 * 1024
        source = GPTSource(
            title="测试视频",
            segment=[TranscriptSegment(start=0.0, end=5.0, text="text transcript")],
            tags=[],
            _format=[],
            style=None,
            extras=None,
            video_img_urls=["data:image/png;base64," + "a" * 100],
            screenshot=True,
            link=False,
            checkpoint_key=None,
        )

        with patch.object(
            gpt,
            "create_chat_completion",
            return_value=make_canned_openai_response("纯文本结果"),
        ) as spy:
            result = gpt.summarize(source)

        self.assertEqual(result, "纯文本结果")
        sent_messages = spy.call_args.kwargs["messages"]
        self.assertIsInstance(sent_messages[0]["content"], str)

    def test_summarize_reserves_images_per_candidate_chunk(self):
        gpt = make_gpt()
        gpt.context_window_tokens = 4096
        gpt.max_request_bytes = 45 * 1024 * 1024
        source = GPTSource(
            title="测试视频",
            segment=[
                TranscriptSegment(start=float(index), end=float(index + 1), text=letter * 1600)
                for index, letter in enumerate(("a", "b", "c", "d"))
            ],
            tags=[],
            _format=[],
            style=None,
            extras=None,
            video_img_urls=[
                "data:image/png;base64," + "a" * 100,
                "data:image/png;base64," + "b" * 100,
            ],
            screenshot=True,
            link=False,
            checkpoint_key=None,
        )

        with patch.object(
            gpt,
            "create_chat_completion",
            return_value=make_canned_openai_response("片段"),
        ) as spy:
            gpt.summarize(source)

        sent_contents = [
            call.kwargs["messages"][0]["content"]
            for call in spy.call_args_list
            if call.kwargs.get("messages")
        ]
        assert any(isinstance(content, list) for content in sent_contents)
        image_calls = [
            call.kwargs["messages"]
            for call in spy.call_args_list
            if isinstance(call.kwargs.get("messages", [{}])[0].get("content"), list)
        ]
        assert image_calls
        for messages in image_calls:
            assert gpt._estimate_messages_bytes(messages) <= gpt.max_request_bytes
            assert gpt._estimate_messages_budget_tokens(messages) <= gpt._input_token_budget()
            assert count_message_images(messages) == 1

    def test_context_limit_6492_4096_rechunks_once_at_seventy_percent(self):
        gpt = make_gpt()
        gpt.context_window_tokens = 4096
        gpt.max_request_bytes = 45 * 1024 * 1024
        gpt._max_retry_attempts = 1
        segments = [
            TranscriptSegment(start=0.0, end=1.0, text="a" * 3500),
            TranscriptSegment(start=1.0, end=2.0, text="b" * 3500),
        ]
        source = GPTSource(
            title="6492/4096 回归",
            segment=segments,
            tags=[],
            _format=[],
            style=None,
            extras=None,
            video_img_urls=[],
            screenshot=False,
            link=False,
            checkpoint_key="context-limit-regression",
        )
        first_error = RuntimeError(
            "exceed_context_size_error: request (6492 tokens) exceeds available context size "
            "(4096 tokens); n_prompt_tokens=6492, n_ctx=4096"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            gpt.checkpoint_dir = pathlib.Path(tmp_dir)
            transcript_cache = gpt.checkpoint_dir / "context-limit-regression_transcript.json"
            frame_cache = gpt.checkpoint_dir / "context-limit-regression_frames_ocr.json"
            transcript_cache.write_text("cached transcript", encoding="utf-8")
            frame_cache.write_text("cached frames", encoding="utf-8")
            with patch.object(
                gpt,
                "create_chat_completion",
                side_effect=[
                    first_error,
                    make_canned_openai_response("分块一"),
                    make_canned_openai_response("分块二"),
                    make_canned_openai_response("合并结果"),
                ],
            ) as spy:
                result = gpt.summarize(source)
            original_checkpoint = gpt._checkpoint_path("context-limit-regression")
            self.assertTrue(original_checkpoint.exists())
            self.assertEqual(transcript_cache.read_text(encoding="utf-8"), "cached transcript")
            self.assertEqual(frame_cache.read_text(encoding="utf-8"), "cached frames")

        self.assertEqual(result, "合并结果")
        self.assertEqual(spy.call_count, 4)
        retried_chunk_messages = spy.call_args_list[1].kwargs["messages"]
        self.assertLessEqual(
            gpt._estimate_messages_budget_tokens(retried_chunk_messages),
            int(gpt._input_token_budget() * 0.7),
        )

    def test_second_context_limit_failure_returns_safe_error_and_keeps_checkpoint(self):
        gpt = make_gpt()
        gpt.context_window_tokens = 4096
        gpt._max_retry_attempts = 1
        source = GPTSource(
            title="重试边界",
            segment=[TranscriptSegment(start=0.0, end=1.0, text="正文")],
            tags=[],
            _format=[],
            style=None,
            extras=None,
            video_img_urls=[],
            screenshot=False,
            link=False,
            checkpoint_key="context-limit-kept",
        )
        raw_error = RuntimeError(
            "maximum context length exceeded; n_prompt_tokens=6492, n_ctx=4096; secret-payload"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            gpt.checkpoint_dir = pathlib.Path(tmp_dir)
            with patch.object(gpt, "create_chat_completion", side_effect=[raw_error, raw_error]):
                with self.assertRaisesRegex(RuntimeError, "模型上下文不足") as exc_info:
                    gpt.summarize(source)
            checkpoint_path = gpt._checkpoint_path("context-limit-kept")
            self.assertTrue(checkpoint_path.exists())

        self.assertNotIn("secret-payload", str(exc_info.exception))


class ContextLimitClassificationTest(unittest.TestCase):
    def test_recognizes_provider_context_limit_variants_and_normalizes_safely(self):
        variants = [
            "exceed_context_size_error",
            "request (6492 tokens) exceeds limit (4096 tokens)",
            "n_prompt_tokens=6492, n_ctx=4096",
            "input exceeds available context size",
            "This model's maximum context length is 4096 tokens",
            "maximum context window is 4096 tokens",
            "maximum context size is 4096 tokens",
        ]

        for raw in variants:
            with self.subTest(raw=raw):
                self.assertTrue(is_context_limit_error(RuntimeError(raw)))
                self.assertEqual(
                    normalize_model_error(RuntimeError(raw + " secret-payload")),
                    "模型上下文不足，请调低输入内容或在模型设置中确认实际上下文长度",
                )

    def test_rejects_unpaired_or_invalid_context_counters(self):
        variants = [
            "n_ctx=4096",
            "n_prompt_tokens=6492",
            "n_prompt_tokens=1000, n_ctx=4096",
            "n_prompt_tokens=oops, n_ctx=4096",
            "n_prompt_tokens=6492, n_ctx=unknown",
            "unknown n_ctx failure",
        ]

        for raw in variants:
            with self.subTest(raw=raw):
                self.assertFalse(is_context_limit_error(RuntimeError(raw)))

    def test_prefers_structured_context_error_code(self):
        class StructuredError(RuntimeError):
            code = "exceed_context_size_error"

        self.assertTrue(is_context_limit_error(StructuredError("opaque provider failure")))

    def test_context_limit_exception_contains_only_safe_fields(self):
        error = ContextLimitExceededError(
            model_name="deepseek-r1:7b",
            context_window_tokens=4096,
        )

        self.assertEqual(error.code, "context_limit_exceeded")
        self.assertEqual(error.model_name, "deepseek-r1:7b")
        self.assertEqual(error.context_window_tokens, 4096)
        self.assertNotIn("payload", str(error).lower())


# ── _get_gpt 返回 NotemeldGPT ────────────────────────────────

class GetGptMigrationTest(unittest.TestCase):
    """note.py._get_gpt() 使用 NotemeldGPT（源码级验证，避免重量级 import 依赖）。"""

    def test_note_py_imports_and_uses_notemeld_gpt(self):
        """note.py 导入 NotemeldGPT 且 _get_gpt 调用 NotemeldGPT.from_config。"""
        note_py = ROOT / "app" / "services" / "note.py"
        src = note_py.read_text(encoding="utf-8")

        # import 存在
        self.assertIn("from app.gpt.notemeld_gpt import NotemeldGPT", src)
        # _get_gpt 用 NotemeldGPT.from_config 替换 GPTFactory
        self.assertIn("NotemeldGPT.from_config(config)", src)
        # GPTFactory import 保留（回滚用）
        self.assertIn("from app.gpt.gpt_factory import GPTFactory", src)


if __name__ == "__main__":
    unittest.main()
