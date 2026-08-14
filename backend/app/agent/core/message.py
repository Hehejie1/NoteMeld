"""AgentMessage：与 LLM Message 解耦的对话消息抽象。

- 上层业务（notemeld-agent / 前端）使用 ``message_type`` 区分 UI-only 消息（如
  note_progress / task_card）。
- 送给 LLM 之前通过 ``convert_to_llm`` 钩子过滤非语义消息，并转换为 OpenAI
  兼容 dict。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentMessage:
    """Agent 内部的消息抽象。

    Attributes:
        role: "user" / "assistant" / "toolResult" / "system"。
        content: 文本内容（当 role != toolResult 时使用）。
        message_type: UI/业务标记，如 "note_progress" / "task_card" / "steer"；
            语义型消息为 None。convert_to_llm 默认根据 role + message_type 过滤。
        tool_call_id: toolResult 消息关联的调用 id；其他 role 为 None。
        is_error: toolResult 是否为错误回传。
        tool_calls: assistant 消息产出的 tool_calls，列表每项为 ToolCall dict。
        meta: 上层业务自由字段，不影响 LLM 输入。
    """

    role: str
    content: str | list[dict] = ""
    message_type: str | None = None
    tool_call_id: str | None = None
    is_error: bool = False
    tool_calls: list[dict] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def UserMessage(content: str, **kwargs) -> AgentMessage:  # noqa: N802 - 工厂函数
    """构造一条 user 消息。"""
    kwargs.pop("role", None)
    return AgentMessage(role="user", content=content, **kwargs)


def AssistantMessage(content: str = "", tool_calls: list[dict] | None = None, **kwargs) -> AgentMessage:  # noqa: N802
    """构造一条 assistant 消息。"""
    kwargs.pop("role", None)
    return AgentMessage(role="assistant", content=content, tool_calls=tool_calls or [], **kwargs)


def ToolResultMessage(  # noqa: N802 - 工厂函数
    call_id: str,
    content: list[dict] | str,
    is_error: bool = False,
    **kwargs,
) -> AgentMessage:
    """构造一条 toolResult 消息。"""
    kwargs.pop("role", None)
    kwargs.pop("tool_call_id", None)
    kwargs.pop("is_error", None)
    text_content = content if isinstance(content, list) else [{"type": "text", "text": content}]
    return AgentMessage(
        role="toolResult",
        content=text_content,
        tool_call_id=call_id,
        is_error=is_error,
        **kwargs,
    )
