"""Stream 事件类型与流式协议。

12 种事件类型覆盖 LLM 流式输出的所有阶段：

    start → text_start → text_delta* → text_end
          → thinking_start → thinking_delta* → thinking_end
          → toolcall_start → toolcall_delta* → toolcall_end
          → done | error

使用方式::

    async for event in provider.stream(model, ctx, signal):
        if event.type == StreamEventType.TEXT_DELTA:
            yield event.delta
        elif event.type == StreamEventType.ERROR:
            raise event.error
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StreamEventType(str, Enum):
    """流式事件类型枚举。"""

    START = "start"
    TEXT_START = "text_start"
    TEXT_DELTA = "text_delta"
    TEXT_END = "text_end"
    THINKING_START = "thinking_start"
    THINKING_DELTA = "thinking_delta"
    THINKING_END = "thinking_end"
    TOOLCALL_START = "toolcall_start"
    TOOLCALL_DELTA = "toolcall_delta"
    TOOLCALL_END = "toolcall_end"
    DONE = "done"
    ERROR = "error"


@dataclass
class StreamEvent:
    """流式事件统一容器。

    每个事件根据 ``type`` 填充不同字段：

    - ``start``: 无额外字段
    - ``text_start``: 无额外字段（标记文本块开始）
    - ``text_delta``: ``delta: str`` 增量文本
    - ``text_end``: 无额外字段
    - ``thinking_start``: 无额外字段
    - ``thinking_delta``: ``delta: str`` 增量思考内容
    - ``thinking_end``: 无额外字段
    - ``toolcall_start``: ``tool_call_id: str``, ``tool_name: str``
    - ``toolcall_delta``: ``tool_call_id: str``, ``arguments_delta: str``
    - ``toolcall_end``: ``tool_call_id: str``, ``tool_name: str``, ``arguments: str``
    - ``done``: ``usage: Usage | None``
    - ``error``: ``error: Exception``
    """

    type: StreamEventType
    delta: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments_delta: str | None = None
    arguments: str | None = None
    usage: Any | None = None  # Usage 类型，延迟引用避免循环
    error: Exception | None = None

    @staticmethod
    def start() -> StreamEvent:
        return StreamEvent(type=StreamEventType.START)

    @staticmethod
    def text_start() -> StreamEvent:
        return StreamEvent(type=StreamEventType.TEXT_START)

    @staticmethod
    def text_delta(delta: str) -> StreamEvent:
        return StreamEvent(type=StreamEventType.TEXT_DELTA, delta=delta)

    @staticmethod
    def text_end() -> StreamEvent:
        return StreamEvent(type=StreamEventType.TEXT_END)

    @staticmethod
    def thinking_start() -> StreamEvent:
        return StreamEvent(type=StreamEventType.THINKING_START)

    @staticmethod
    def thinking_delta(delta: str) -> StreamEvent:
        return StreamEvent(type=StreamEventType.THINKING_DELTA, delta=delta)

    @staticmethod
    def thinking_end() -> StreamEvent:
        return StreamEvent(type=StreamEventType.THINKING_END)

    @staticmethod
    def toolcall_start(tool_call_id: str, tool_name: str) -> StreamEvent:
        return StreamEvent(
            type=StreamEventType.TOOLCALL_START,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )

    @staticmethod
    def toolcall_delta(tool_call_id: str, arguments_delta: str) -> StreamEvent:
        return StreamEvent(
            type=StreamEventType.TOOLCALL_DELTA,
            tool_call_id=tool_call_id,
            arguments_delta=arguments_delta,
        )

    @staticmethod
    def toolcall_end(tool_call_id: str, tool_name: str, arguments: str) -> StreamEvent:
        return StreamEvent(
            type=StreamEventType.TOOLCALL_END,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
        )

    @staticmethod
    def done(usage: Any | None = None) -> StreamEvent:
        return StreamEvent(type=StreamEventType.DONE, usage=usage)

    @staticmethod
    def error(error: Exception) -> StreamEvent:
        return StreamEvent(type=StreamEventType.ERROR, error=error)


@dataclass
class CompleteResult:
    """非流式 ``complete()`` 返回结果。

    Attributes:
        content: 文本内容。
        tool_calls: 工具调用列表，每项为
            ``{"id": str, "name": str, "arguments": str}``。
        usage: Usage 对象（input_tokens/output_tokens/total_tokens/cost）。
        thinking: 思考内容（如果模型支持），否则为 None。
        finish_reason: Provider 返回的真实结束原因，否则为 None。
    """

    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: Any | None = None
    thinking: str | None = None
    finish_reason: str | None = None
