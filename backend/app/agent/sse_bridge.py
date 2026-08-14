"""P2-T4: Agent 10 类事件 → 旧 SSE delta/done/error 格式映射。

旧 ``free_chat_stream`` yield 三种事件 dict：
- ``{"type":"delta","content":delta}``
- ``{"type":"done","answer":full_answer,"sources":[...]}``
- ``{"type":"error","message":...}``

Agent 10 类事件映射规则：
- ``MESSAGE_UPDATE(delta)`` → ``{"type":"delta","content":delta}``（累积到 full_answer）
- ``AGENT_END(error=None)`` → ``{"type":"done","answer":full_answer,"sources":[...]}``
- ``AGENT_END(error=...)`` → ``{"type":"error","message":...}``
- 其他 8 类事件 → 忽略（旧前端不处理）

设计要点：
- 使用 ``asyncio.Queue`` 解耦 listener（在 agent_loop 内同步调用）与外层生成器。
- ``agent.prompt`` 在后台 task 中执行，避免阻塞生成器迭代。
- listener 异常被 ``EventDispatcher`` 吞掉，因此 ``run_agent`` 外层兜底 error 事件。
- 生成器退出时（客户端断连 / break）取消后台 task，避免泄漏。
- 同时提供 ``collect_agent_result`` 用于非流式场景（``free_chat`` / ``chat``），
  返回 ``{"answer":..., "sources":...}`` 与旧返回结构逐字段等价。
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Optional

from app.agent.core.agent import Agent
from app.agent.core.events import AgentEventType
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 流式：Agent 事件 → 旧 SSE dict 序列
# ---------------------------------------------------------------------------

async def agent_events_to_sse_dict(
    agent: Agent,
    question: str,
    sources: list[dict] | None = None,
    long_task_manager: Any = None,
) -> AsyncIterator[dict]:
    """订阅 Agent 事件，yield 旧 SSE 格式 dict。

    Args:
        agent: 已配置好的 Agent（未启动）。
        question: 用户问题（会调用 ``agent.prompt(question)``）。
        sources: 检索来源列表，用于 done 事件回填。
        long_task_manager: 可选的长任务管理器。传入时会：

            1. 把 ``long_task_manager.dispatcher`` 设为把事件 dict 写入同一队列的
               回调，使 ``task_card`` / ``task_card_progress`` 经 SSE 流派发；
            2. ``done`` / ``error`` 后**不立即关闭**流，而是等待 long_task_manager
               所有活跃卡片结束（``list_active_cards()`` 为空）且队列排空后才退出，
               以保证长任务进度持续推送直到任务完成。
            3. run_agent 完成后调用 ``await long_task_manager.wait_for_all(timeout=30)``
               做最终收尾。

    Yields:
        旧 SSE dict：``{"type":"delta"|"done"|"error"}``；
        long_task_manager 启用时额外有 ``task_card`` / ``task_card_progress``。
    """
    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    # 用 list 容器便于在闭包中修改
    full_answer: list[str] = [""]
    emitted_end: list[bool] = [False]

    async def listener(evt: Any) -> None:
        try:
            if evt.type == AgentEventType.MESSAGE_UPDATE and evt.delta:
                full_answer[0] += evt.delta
                await queue.put({"type": "delta", "content": evt.delta})
            elif evt.type == AgentEventType.AGENT_END:
                if evt.error is not None:
                    msg = getattr(evt.error, "message", None) or str(evt.error) or "agent error"
                    await queue.put({"type": "error", "message": msg})
                else:
                    await queue.put({
                        "type": "done",
                        "answer": full_answer[0],
                        "sources": sources or [],
                    })
                emitted_end[0] = True
        except Exception as exc:  # noqa: BLE001 - listener 异常不能 crash agent_loop
            logger.error("sse_bridge listener error: %s", exc, exc_info=True)

    agent.subscribe(listener)

    # 注入 long_task_manager.dispatcher：把 task_card / task_card_progress 汇入同一队列
    if long_task_manager is not None:
        def _dispatcher(evt: dict):  # noqa: ANN202
            try:
                queue.put_nowait(evt)
            except Exception as exc:  # noqa: BLE001
                logger.warning("sse_bridge long_task dispatcher put 失败: %s", exc)
            return None
        try:
            long_task_manager.dispatcher = _dispatcher
        except Exception as exc:  # noqa: BLE001
            logger.warning("注入 long_task_manager.dispatcher 失败: %s", exc)

    async def run_agent() -> None:
        try:
            await agent.prompt(question)
            await agent.wait_for_idle()
        except Exception as exc:  # noqa: BLE001 - 兜底：prompt 抛异常但未 emit AGENT_END
            if not emitted_end[0]:
                await queue.put({"type": "error", "message": str(exc)})
                emitted_end[0] = True
        finally:
            # run_agent 结束后，若启用 long_task_manager，等待所有长任务收尾
            if long_task_manager is not None:
                try:
                    await long_task_manager.wait_for_all(timeout=30.0)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("sse_bridge wait_for_all 失败: %s", exc)
                # 哨兵：通知主循环退出（仅在启用长任务时需要，
                # 因为 done/error 不再立即 break）
                try:
                    queue.put_nowait(None)
                except Exception:  # noqa: BLE001
                    pass

    task = asyncio.create_task(run_agent())

    try:
        while True:
            item = await queue.get()
            if item is None:
                # 哨兵由 run_agent finally 在 wait_for_all 后放入。
                # 收到哨兵即退出：长任务事件已在 wait_for_all 期间排入队列（FIFO，
                # 哨兵在最后），主循环已按序 yield 完毕。
                break
            yield item
            if item.get("type") in ("done", "error"):
                # 无 long_task_manager：立即 break（旧行为）
                if long_task_manager is None:
                    break
                # 有 long_task_manager：不立即 break，等 run_agent finally 的哨兵
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        try:
            agent.unsubscribe(listener)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# 非流式：收集 Agent 最终回答
# ---------------------------------------------------------------------------

async def collect_agent_result(
    agent: Agent,
    question: str,
    sources: list[dict] | None = None,
) -> dict:
    """运行 Agent 并返回 ``{"answer":..., "sources":...}``。

    用于 ``chat()`` / ``free_chat()`` 非流式场景。
    从 ``agent.state.messages`` 提取最后一条 assistant 消息的 content 作为 answer。
    """
    answer_holder: list[str] = [""]

    async def listener(evt: Any) -> None:
        if evt.type == AgentEventType.MESSAGE_START and evt.role == "assistant":
            # 每轮 assistant 开始时重置，只保留最后一轮文本
            answer_holder[0] = ""
        elif evt.type == AgentEventType.MESSAGE_UPDATE and evt.delta:
            answer_holder[0] += evt.delta

    agent.subscribe(listener)
    try:
        await agent.prompt(question)
        await agent.wait_for_idle()
    finally:
        try:
            agent.unsubscribe(listener)
        except Exception:  # noqa: BLE001
            pass

    if agent.error is not None:
        msg = getattr(agent.error, "message", None) or str(agent.error)
        raise RuntimeError(msg)

    # 优先用 listener 累积的最后一轮文本；fallback 到 state.messages 最后一条 assistant
    answer = answer_holder[0]
    if not answer:
        for msg in reversed(agent.messages):
            if msg.role == "assistant" and isinstance(msg.content, str) and msg.content:
                answer = msg.content
                break

    return {"answer": answer, "sources": sources or []}


__all__ = ["agent_events_to_sse_dict", "collect_agent_result"]
