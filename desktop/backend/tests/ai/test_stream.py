"""notemeld-ai StreamEvent / StreamEventType / CompleteResult 单测。"""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.stream import CompleteResult, StreamEvent, StreamEventType  # noqa: E402


class StreamEventTypeTest(unittest.TestCase):
    def test_event_type_is_str_enum(self):
        """StreamEventType 继承 str，可直接当字符串用于 SSE event 标签。"""
        self.assertEqual(StreamEventType.TEXT_DELTA, "text_delta")
        self.assertEqual(StreamEventType.DONE, "done")
        self.assertEqual(StreamEventType.ERROR, "error")

    def test_all_twelve_event_types_present(self):
        """覆盖 spec 中定义的 12 类事件。"""
        expected = {
            "start", "text_start", "text_delta", "text_end",
            "thinking_start", "thinking_delta", "thinking_end",
            "toolcall_start", "toolcall_delta", "toolcall_end",
            "done", "error",
        }
        actual = {e.value for e in StreamEventType}
        self.assertEqual(actual, expected)


class StreamEventFactoryTest(unittest.TestCase):
    def test_start_event(self):
        ev = StreamEvent.start()
        self.assertEqual(ev.type, StreamEventType.START)
        self.assertIsNone(ev.delta)

    def test_text_lifecycle(self):
        s = StreamEvent.text_start()
        d = StreamEvent.text_delta("hello ")
        d2 = StreamEvent.text_delta("world")
        e = StreamEvent.text_end()
        self.assertEqual(s.type, StreamEventType.TEXT_START)
        self.assertEqual(d.type, StreamEventType.TEXT_DELTA)
        self.assertEqual(d.delta, "hello ")
        self.assertEqual(d2.delta, "world")
        self.assertEqual(e.type, StreamEventType.TEXT_END)

    def test_thinking_lifecycle(self):
        s = StreamEvent.thinking_start()
        d = StreamEvent.thinking_delta("thinking...")
        e = StreamEvent.thinking_end()
        self.assertEqual(s.type, StreamEventType.THINKING_START)
        self.assertEqual(d.delta, "thinking...")
        self.assertEqual(e.type, StreamEventType.THINKING_END)

    def test_toolcall_lifecycle(self):
        s = StreamEvent.toolcall_start("call_1", "lookup_transcript")
        d = StreamEvent.toolcall_delta("call_1", '{"task_id":"t1",')
        d2 = StreamEvent.toolcall_delta("call_1", '"keyword":"ai"}')
        e = StreamEvent.toolcall_end("call_1", "lookup_transcript", '{"task_id":"t1","keyword":"ai"}')
        self.assertEqual(s.type, StreamEventType.TOOLCALL_START)
        self.assertEqual(s.tool_call_id, "call_1")
        self.assertEqual(s.tool_name, "lookup_transcript")
        self.assertEqual(d.type, StreamEventType.TOOLCALL_DELTA)
        self.assertEqual(d.tool_call_id, "call_1")
        self.assertEqual(d.arguments_delta, '{"task_id":"t1",')
        self.assertEqual(e.type, StreamEventType.TOOLCALL_END)
        self.assertEqual(e.arguments, '{"task_id":"t1","keyword":"ai"}')

    def test_done_event_with_usage(self):
        usage = object()  # Usage 对象，类型为 Any
        ev = StreamEvent.done(usage=usage)
        self.assertEqual(ev.type, StreamEventType.DONE)
        self.assertIs(ev.usage, usage)

    def test_done_event_without_usage(self):
        ev = StreamEvent.done()
        self.assertIsNone(ev.usage)

    def test_error_event(self):
        err = RuntimeError("boom")
        ev = StreamEvent.error(err)
        self.assertEqual(ev.type, StreamEventType.ERROR)
        self.assertIs(ev.error, err)


class CompleteResultTest(unittest.TestCase):
    def test_default_values(self):
        r = CompleteResult()
        self.assertEqual(r.content, "")
        self.assertEqual(r.tool_calls, [])
        self.assertIsNone(r.usage)
        self.assertIsNone(r.thinking)

    def test_with_fields(self):
        usage = object()
        r = CompleteResult(
            content="hello",
            tool_calls=[{"id": "c1", "name": "fn", "arguments": "{}"}],
            usage=usage,
            thinking="thought",
        )
        self.assertEqual(r.content, "hello")
        self.assertEqual(len(r.tool_calls), 1)
        self.assertIs(r.usage, usage)
        self.assertEqual(r.thinking, "thought")

    def test_tool_calls_default_factory_isolated(self):
        """每个 CompleteResult 应有独立的 tool_calls 列表（不共享默认值）。"""
        a = CompleteResult()
        b = CompleteResult()
        a.tool_calls.append({"id": "x"})
        self.assertEqual(b.tool_calls, [])


if __name__ == "__main__":
    unittest.main()
