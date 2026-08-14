"""transform_context / convert_to_llm / before_tool_call / after_tool_call 钩子。

默认实现保证开箱即用；上层业务在 Agent 构造时传入自己的钩子实现：
- transform_context：裁剪/压缩/注入外部上下文（如研究空间记忆），默认浅拷贝不截断。
- convert_to_llm：过滤 UI-only 消息，并将 AgentMessage 转换为 OpenAI 兼容 dict。
- before_tool_call：权限拒绝时返回 ``{"block": True, "reason": "..."}``。
- after_tool_call：钩子暂未在 core 逻辑中使用，但对外暴露以便上层订阅后做审计。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from app.agent.core.message import AgentMessage
from app.agent.core.signal import AbortSignal


# ---------------------------------------------------------------------------
# 钩子协议签名
# ---------------------------------------------------------------------------

@runtime_checkable
class TransformContextFn(Protocol):
    def __call__(self, messages: list[AgentMessage], signal: AbortSignal) -> list[AgentMessage]:
        ...


@runtime_checkable
class ConvertToLLMFn(Protocol):
    def __call__(self, messages: list[AgentMessage]) -> list[dict]:
        ...


@runtime_checkable
class BeforeToolCallFn(Protocol):
    async def __call__(
        self,
        tool_call: dict,
        arguments: dict,
        context: dict[str, Any],
    ) -> dict | None:
        """返回 ``{"block": True, "reason": "..."}`` 以拒绝执行；None 表示通过。"""
        ...


@runtime_checkable
class AfterToolCallFn(Protocol):
    async def __call__(
        self,
        tool_call: dict,
        result: dict,
        context: dict[str, Any],
    ) -> None:
        ...


# ---------------------------------------------------------------------------
# 默认实现
# ---------------------------------------------------------------------------

def _default_transform_context(
    messages: list[AgentMessage],
    signal: AbortSignal,  # noqa: ARG001 - 默认实现忽略
) -> list[AgentMessage]:
    """默认：浅拷贝一份，不 mutate 原数组（需求 §7.4）。"""
    return list(messages)


def _default_convert_to_llm(messages: list[AgentMessage]) -> list[dict]:
    """默认：过滤 UI-only 消息（note_progress / task_card / parameter_*），
    保留 user / assistant / toolResult / system，并转换为 OpenAI dict。

    原 messages 数组不 mutate。
    """
    out: list[dict] = []
    for msg in messages:
        if msg.message_type in {
            "note_progress",
            "note_result",
            "task_card",
            "task_card_progress",
            "parameter_request",
            "parameter_response",
            "knowledge_board",
        }:
            continue

        if msg.role == "user":
            out.append({"role": "user", "content": msg.content if isinstance(msg.content, str) else _content_to_text(msg.content)})
        elif msg.role == "system":
            out.append({"role": "system", "content": msg.content if isinstance(msg.content, str) else _content_to_text(msg.content)})
        elif msg.role == "assistant":
            entry: dict = {"role": "assistant", "content": msg.content if isinstance(msg.content, str) else _content_to_text(msg.content) or None}
            if msg.tool_calls:
                entry["tool_calls"] = msg.tool_calls
            out.append(entry)
        elif msg.role == "toolResult":
            content = msg.content if isinstance(msg.content, str) else _content_to_text(msg.content)
            if msg.is_error:
                content = f"TOOL_EXECUTION_ERROR: {content}"
            out.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": content,
            })
    return out


def _content_to_text(content: list[dict]) -> str:
    parts: list[str] = []
    for c in content:
        if isinstance(c, dict) and c.get("type") == "text":
            parts.append(str(c.get("text", "")))
    return "\n".join(parts)


async def _default_before_tool_call(
    tool_call: dict,  # noqa: ARG001 - 默认放行
    arguments: dict,  # noqa: ARG001
    context: dict[str, Any],  # noqa: ARG001
) -> dict | None:
    return None


async def _default_after_tool_call(
    tool_call: dict,  # noqa: ARG001
    result: dict,  # noqa: ARG001
    context: dict[str, Any],  # noqa: ARG001
) -> None:
    return None


@dataclass
class Hooks:
    """容器：4 个钩子。未传时使用默认实现。"""

    transform_context: TransformContextFn | None = None
    convert_to_llm: ConvertToLLMFn | None = None
    before_tool_call: BeforeToolCallFn | None = None
    after_tool_call: AfterToolCallFn | None = None

    # ------------------------------------------------------------------ #
    def resolve_transform(self) -> TransformContextFn:
        return self.transform_context or _default_transform_context

    def resolve_convert(self) -> ConvertToLLMFn:
        return self.convert_to_llm or _default_convert_to_llm

    def resolve_before_tool(self) -> BeforeToolCallFn:
        return self.before_tool_call or _default_before_tool_call

    def resolve_after_tool(self) -> AfterToolCallFn:
        return self.after_tool_call or _default_after_tool_call


# Re-export helpers，供上层自定义钩子复用
make_copy = copy.copy  # 预留命名
__all__ = [
    "Hooks",
    "TransformContextFn",
    "ConvertToLLMFn",
    "BeforeToolCallFn",
    "AfterToolCallFn",
]
