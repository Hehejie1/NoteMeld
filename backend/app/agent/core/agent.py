"""Agent 类：对外暴露的一等公民接口。

典型使用::

    agent = Agent(
        initial_state=AgentState(system_prompt=..., model=model, tools=tools),
        max_turns=10,
        tool_execution="parallel",
        models=models,          # create_models() 实例
    )
    agent.subscribe(listener_fn)
    await agent.prompt("帮我查 xxx")
    await agent.wait_for_idle()
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from app.agent.core.events import AgentEvent, EventDispatcher
from app.agent.core.hooks import Hooks
from app.agent.core.loop import agent_loop
from app.agent.core.message import AgentMessage, UserMessage
from app.agent.core.signal import AbortSignal
from app.agent.core.state import AgentError, AgentState

Listener = Callable[[AgentEvent], Awaitable[None]]


class Agent:
    """Agent 运行时包装器。

    为上游业务提供友好的控制面：prompt / continue / abort / steer / follow_up /
    wait_for_idle / subscribe。实际多轮循环由 ``agent_loop`` 实现，此为薄封装。
    """

    def __init__(
        self,
        *,
        initial_state: AgentState,
        max_turns: int = 10,
        tool_execution: str = "parallel",
        models: Any = None,
        usage_context: dict | None = None,
        # 钩子
        transform_context: Callable | None = None,
        convert_to_llm: Callable | None = None,
        before_tool_call: Callable | None = None,
        after_tool_call: Callable | None = None,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        if tool_execution not in {"parallel", "serial"}:
            raise ValueError("tool_execution must be 'parallel' or 'serial'")

        self._state = initial_state
        self._max_turns = int(max_turns)
        self._tool_execution = tool_execution
        self._models = models
        self._usage_context = usage_context or {}

        self._hooks = Hooks(
            transform_context=transform_context,
            convert_to_llm=convert_to_llm,
            before_tool_call=before_tool_call,
            after_tool_call=after_tool_call,
        )
        self._dispatcher = EventDispatcher()
        self._signal = AbortSignal()
        # _idle 初始为 set：还没跑任何循环即处于空闲
        self._idle = asyncio.Event()
        self._idle.set()
        self._running = False

    # ------------------------------------------------------------------ #
    # 事件订阅
    # ------------------------------------------------------------------ #
    def subscribe(self, listener: Listener) -> None:
        self._dispatcher.subscribe(listener)

    def unsubscribe(self, listener: Listener) -> None:
        self._dispatcher.unsubscribe(listener)

    # ------------------------------------------------------------------ #
    # 状态访问（只读）
    # ------------------------------------------------------------------ #
    @property
    def state(self) -> AgentState:
        """当前状态快照引用。上层不应直接 mutate，但可读取 messages/error。"""
        return self._state

    @property
    def messages(self) -> list[AgentMessage]:
        return self._state.messages

    @property
    def error(self) -> AgentError | None:
        return self._state.error

    @property
    def is_streaming(self) -> bool:
        return self._state.is_streaming

    @property
    def turn_count(self) -> int:
        return self._state.turn_count

    # ------------------------------------------------------------------ #
    # 控制面
    # ------------------------------------------------------------------ #
    async def prompt(self, text: str) -> None:
        """追加一条 user 消息并开始新的 agent 循环。

        Raises:
            ValueError: 空 prompt。
            RuntimeError: 正在运行中（应 follow_up / steer 代替）。
        """
        if not isinstance(text, str) or not text.strip():
            raise ValueError("prompt(text) 不能为空")
        if self._running:
            raise RuntimeError("agent 正在运行中，请用 steer()/follow_up() 代替连续 prompt")
        # 每个新的顶层 prompt 视为一个新回合：清空旧 error/signal/turn_count，
        # 但保留 messages 用于多轮上下文（与 continue_() 仅在最后角色异常时禁止的语义不同）。
        self._state.error = None
        self._state.turn_count = 0
        if self._signal.aborted:
            self._signal = AbortSignal()
        self._state.messages.append(UserMessage(content=text))
        await self._run()

    async def continue_(self) -> None:
        """基于现有 messages 继续下一轮。

        典型场景：用户 steer/注入了新 toolResult 消息、或上次 max_turns 后想续跑。
        """
        if not self._state.messages:
            raise AgentError("empty_messages", "continue() 要求 messages 非空")
        last = self._state.messages[-1]
        if last.role not in {"user", "toolResult"}:
            raise AgentError(
                "continue_bad_last_role",
                f"continue() 要求最后一条消息 role 为 user/toolResult，当前为 {last.role!r}",
            )
        if self._running:
            raise RuntimeError("agent 正在运行中")
        # 清除 error 和旧 signal，允许续跑
        self._state.error = None
        self._signal = AbortSignal()
        self._state.turn_count = 0
        await self._run()

    async def abort(self, reason: str = "aborted") -> None:
        """温柔取消：signal 传递到 LLM stream 和 tool.execute；不丢已产出内容。

        验收 §7.3：200ms 内 signal 传递（asyncio.Event.set 为原子操作）。
        """
        self._signal.abort(reason=reason)
        # 同步标记 state.error，让 wait_for_idle 后能立即读到
        self._state.error = AgentError(code="aborted", message=reason)

    async def steer(self, interrupt_msg: str) -> None:
        """在 tool 执行中注入打断消息，下一个 turn 立即生效。

        不会中断当前正在执行的 tool（由上层 abort 控制），但下一轮 LLM 会看到。
        """
        if not isinstance(interrupt_msg, str) or not interrupt_msg.strip():
            raise ValueError("steer(msg) 不能为空")
        self._state.messages.append(UserMessage(content=interrupt_msg, meta={"steer": True}))

    async def follow_up(self, prompt_text: str) -> None:
        """排队后续 user 消息：等当前循环结束后再执行。"""
        await self.wait_for_idle()
        await self.prompt(prompt_text)

    async def wait_for_idle(self) -> None:
        """等待直到当前 agent 循环完全结束。"""
        await self._idle.wait()

    # ------------------------------------------------------------------ #
    # 内部：实际执行
    # ------------------------------------------------------------------ #
    async def _run(self) -> None:
        if self._running:
            return
        self._running = True
        self._idle.clear()
        # 进入循环前 fresh signal（abort() 会覆盖它）
        if self._signal.aborted:
            self._signal = AbortSignal()
        try:
            await agent_loop(
                state=self._state,
                hooks=self._hooks,
                dispatcher=self._dispatcher,
                max_turns=self._max_turns,
                signal=self._signal,
                models=self._resolve_models(),
                tool_execution_mode=self._tool_execution,
                usage_context=self._usage_context,
            )
        finally:
            self._running = False
            self._idle.set()

    def _resolve_models(self) -> Any:
        if self._models is None:
            # 懒加载：允许 P1 单测不依赖真实 create_models；生产中上层业务应显式传入
            try:
                from app.ai import create_models  # type: ignore

                self._models = create_models()
            except Exception as exc:  # noqa: BLE001 - 降级
                raise AgentError(
                    "models_missing",
                    "Agent 未传入 models 且无法懒加载 create_models(); "
                    "请通过 Agent(models=...) 传入",
                    details={"inner": str(exc)},
                ) from None
        return self._models
