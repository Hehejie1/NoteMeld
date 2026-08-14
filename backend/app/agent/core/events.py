"""10 类 AgentEvent + EventDispatcher。

事件序列（3 turn 典型）::

    agent_start
      turn_start
        message_start(user)                 → message_end
        message_start(assistant)            → message_update* → message_end (tool_calls=[tc1, tc2])
        tool_execution_start(call_id=tc1)   → tool_execution_update? → tool_execution_end
        tool_execution_start(call_id=tc2)   → tool_execution_end
        message_start(toolResult)           → message_end  (每条 toolResult 一对)
      turn_end
      turn_start
        message_start(assistant)            → message_update* → message_end (no tool_calls)
      turn_end
    agent_end

每个事件对应一个构造函数（AgentStartEvent/...），便于订阅者按类型 dispatch。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable

from app.agent.core.tool import ToolResult

logger = logging.getLogger(__name__)


class AgentEventType(str, Enum):
    """P1 验收 §7.1 规定的 10 类事件。"""

    AGENT_START = "agent_start"
    TURN_START = "turn_start"
    MESSAGE_START = "message_start"
    MESSAGE_UPDATE = "message_update"
    MESSAGE_END = "message_end"
    TOOL_EXECUTION_START = "tool_execution_start"
    TOOL_EXECUTION_UPDATE = "tool_execution_update"
    TOOL_EXECUTION_END = "tool_execution_end"
    TURN_END = "turn_end"
    AGENT_END = "agent_end"


@dataclass
class AgentEvent:
    """结构化事件容器。字段根据 ``type`` 含义不同而填充。"""

    type: AgentEventType
    turn: int | None = None
    role: str | None = None
    delta: str | None = None
    tool_call: dict | None = None
    call_id: str | None = None
    tool_name: str | None = None
    details: dict | None = None
    result: ToolResult | dict | None = None
    tool_results: list[ToolResult] | None = None
    error: "AgentError | None" = None
    extra: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.extra is None:
            self.extra = {}


# 便利构造函数 — 每个事件类型一个，方便 loop 里派发。
def AgentStartEvent() -> AgentEvent:  # noqa: N802
    return AgentEvent(type=AgentEventType.AGENT_START)


def TurnStartEvent(turn: int) -> AgentEvent:  # noqa: N802
    return AgentEvent(type=AgentEventType.TURN_START, turn=turn)


def MessageStartEvent(role: str, turn: int | None = None) -> AgentEvent:  # noqa: N802
    return AgentEvent(type=AgentEventType.MESSAGE_START, role=role, turn=turn)


def MessageUpdateEvent(delta: str, turn: int | None = None) -> AgentEvent:  # noqa: N802
    return AgentEvent(type=AgentEventType.MESSAGE_UPDATE, delta=delta, turn=turn)


def MessageEndEvent(  # noqa: N802 - 构造函数
    role: str,
    turn: int | None = None,
    tool_calls: list[dict] | None = None,
    content: str = "",
) -> AgentEvent:
    return AgentEvent(
        type=AgentEventType.MESSAGE_END,
        role=role,
        turn=turn,
        tool_call=tool_calls[0] if tool_calls and len(tool_calls) == 1 else None,
        extra={"tool_calls": tool_calls, "content": content},
    )


def ToolExecutionStartEvent(call_id: str, tool_name: str, turn: int | None = None) -> AgentEvent:  # noqa: N802
    return AgentEvent(
        type=AgentEventType.TOOL_EXECUTION_START,
        call_id=call_id,
        tool_name=tool_name,
        turn=turn,
    )


def ToolExecutionUpdateEvent(call_id: str, details: dict, turn: int | None = None) -> AgentEvent:  # noqa: N802
    return AgentEvent(
        type=AgentEventType.TOOL_EXECUTION_UPDATE,
        call_id=call_id,
        details=details,
        turn=turn,
    )


def ToolExecutionEndEvent(  # noqa: N802
    call_id: str,
    result: ToolResult | dict,
    turn: int | None = None,
) -> AgentEvent:
    return AgentEvent(
        type=AgentEventType.TOOL_EXECUTION_END,
        call_id=call_id,
        result=result,
        turn=turn,
    )


def TurnEndEvent(  # noqa: N802
    turn: int,
    tool_results: list[ToolResult] | None = None,
) -> AgentEvent:
    return AgentEvent(
        type=AgentEventType.TURN_END,
        turn=turn,
        tool_results=tool_results,
    )


def AgentEndEvent(error: "AgentError | None" = None) -> AgentEvent:  # noqa: N802
    return AgentEvent(type=AgentEventType.AGENT_END, error=error)


# ---------------------------------------------------------------------------
# EventDispatcher
# ---------------------------------------------------------------------------

Listener = Callable[[AgentEvent], Awaitable[None]]


class EventDispatcher:
    """派发 AgentEvent 给所有订阅者。

    设计要点：
    - listener 抛异常不中断主循环、不影响其他 listener（验收 §10 边界场景）。
    - 默认同步 await：保证简单场景下事件顺序严格等于派发顺序。
    """

    __slots__ = ("_listeners",)

    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    # ------------------------------------------------------------------ #
    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    @property
    def listener_count(self) -> int:
        return len(self._listeners)

    # ------------------------------------------------------------------ #
    async def emit(self, event: AgentEvent) -> None:
        """派发事件给所有 listener；任何 listener 异常被吞掉并写 error log。"""
        for listener in list(self._listeners):
            try:
                await listener(event)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "agent event listener %s threw %s: %s",
                    getattr(listener, "__qualname__", repr(listener)),
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
