"""notemeld-agent-core：Agent 运行时（工具循环、状态机、事件流）。

纯内存运行时，不依赖 FastAPI / SQLite / 上层业务。上层业务（notemeld-agent）
订阅事件后将进度、结果写入 conversation_messages 等。

使用方式::

    from app.agent.core import Agent, AgentState, AgentTool

    agent = Agent(
        initial_state=AgentState(
            system_prompt="...",
            model=model,            # 来自 notemeld-ai 的 Model 对象
            tools=[...],            # list[AgentTool]
            messages=[],
        ),
        max_turns=10,
        tool_execution="parallel",
        models=models,              # 来自 create_models()，单测可传 mock
    )
    agent.subscribe(on_event)
    await agent.prompt("Hello")
    await agent.wait_for_idle()
"""

from app.agent.core.signal import AbortSignal
from app.agent.core.message import (
    AgentMessage,
    UserMessage,
    AssistantMessage,
    ToolResultMessage,
)
from app.agent.core.tool import AgentTool, ToolCall, ToolResult
from app.agent.core.events import (
    AgentEventType,
    AgentEvent,
    EventDispatcher,
    AgentStartEvent,
    TurnStartEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    MessageEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    ToolExecutionEndEvent,
    TurnEndEvent,
    AgentEndEvent,
)
from app.agent.core.hooks import (
    Hooks,
    TransformContextFn,
    ConvertToLLMFn,
    BeforeToolCallFn,
    AfterToolCallFn,
)
from app.agent.core.state import AgentState, AgentError
from app.agent.core.loop import agent_loop
from app.agent.core.agent import Agent

__all__ = [
    # signal
    "AbortSignal",
    # message
    "AgentMessage",
    "UserMessage",
    "AssistantMessage",
    "ToolResultMessage",
    # tool
    "AgentTool",
    "ToolCall",
    "ToolResult",
    # events
    "AgentEventType",
    "AgentEvent",
    "EventDispatcher",
    "AgentStartEvent",
    "TurnStartEvent",
    "MessageStartEvent",
    "MessageUpdateEvent",
    "MessageEndEvent",
    "ToolExecutionStartEvent",
    "ToolExecutionUpdateEvent",
    "ToolExecutionEndEvent",
    "TurnEndEvent",
    "AgentEndEvent",
    # hooks
    "Hooks",
    "TransformContextFn",
    "ConvertToLLMFn",
    "BeforeToolCallFn",
    "AfterToolCallFn",
    # state
    "AgentState",
    "AgentError",
    # loop
    "agent_loop",
    # agent
    "Agent",
]
