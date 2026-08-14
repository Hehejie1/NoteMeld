"""AgentState + AgentError。

纯内存状态机，不读写 SQLite。上层业务通过事件订阅持久化到 conversation_messages。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.agent.core.message import AgentMessage
from app.agent.core.tool import AgentTool

if TYPE_CHECKING:
    from app.ai.models import Model  # pragma: no cover - 仅类型


class AgentError(Exception):
    """Core 层统一错误类型。上层业务可据此区分状态。"""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def __repr__(self) -> str:  # pragma: no cover
        return f"AgentError(code={self.code!r}, message={self.message!r})"


@dataclass
class AgentState:
    """Agent 运行时状态。

    Attributes:
        system_prompt: 每轮循环注入到 LLM 的 system prompt。
        model: P0 notemeld-ai 的 Model 对象；agent_loop 里需要用它选 provider。
        tools: 注册给 LLM 的 AgentTool 列表。
        messages: Agent 内部消息列表，可能混入 UI-only 消息（note_progress 等）。
        is_streaming: 当前是否正处于 LLM streaming 或 tool 执行。
        pending_tool_calls: 本轮 assistant 产出但尚未执行完的 tool_calls。
        error: 最近一次错误；未出错时为 None。
        turn_count: 已执行的 turn 数量。
    """

    system_prompt: str = ""
    model: Any = None  # 延迟引用避免硬依赖
    tools: list[AgentTool] = field(default_factory=list)
    messages: list[AgentMessage] = field(default_factory=list)
    is_streaming: bool = False
    pending_tool_calls: list[dict] = field(default_factory=list)
    error: AgentError | None = None
    turn_count: int = 0
