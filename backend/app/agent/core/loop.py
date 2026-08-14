"""agent_loop：核心生成器 + 工具执行调度（并行/串行）。

验收标准：
- §7.1 事件序列严格按 spec 顺序
- §7.2 并行工具 execute 并发，返回/写入顺序与原 tool_calls 一致
- §7.3 abort 传递到 tool.execute 的 signal 参数
- §7.5 超过 max_turns 兜底，不吞已有 assistant 文本
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.agent.core.events import (
    AgentEndEvent,
    AgentStartEvent,
    EventDispatcher,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from app.agent.core.hooks import Hooks
from app.agent.core.message import AssistantMessage, ToolResultMessage
from app.agent.core.signal import AbortSignal
from app.agent.core.state import AgentError, AgentState
from app.agent.core.tool import ToolResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# agent_loop 主入口
# ---------------------------------------------------------------------------

async def agent_loop(
    state: AgentState,
    hooks: Hooks,
    dispatcher: EventDispatcher,
    max_turns: int,
    signal: AbortSignal,
    models: Any,
    tool_execution_mode: str = "parallel",
    usage_context: dict | None = None,
) -> None:
    """执行一轮或多轮 agent 循环，直到：
    - assistant 消息不含 tool_calls（对话结束）
    - turn 数达 max_turns
    - signal.aborted
    """
    state.is_streaming = True
    state.error = None
    try:
        await dispatcher.emit(AgentStartEvent())

        # 最外层 while：多轮 turn，直到自然结束 / 达到上限 / 被 abort
        while state.turn_count < max_turns:
            if signal.aborted:
                state.error = AgentError(code="aborted", message=signal.reason or "aborted")
                break

            state.turn_count += 1
            turn = state.turn_count
            await dispatcher.emit(TurnStartEvent(turn=turn))

            # 1) transform + convert
            transform_fn = hooks.resolve_transform()
            convert_fn = hooks.resolve_convert()
            transformed = transform_fn(state.messages, signal)
            llm_messages = convert_fn(transformed)

            # 2) 拼装 tools → OpenAI dict
            tools_openai = [t.to_openai_function() for t in state.tools] or None

            # 3) 发消息事件：assistant 的 message_start 提前，stream 中持续 update
            await dispatcher.emit(MessageStartEvent(role="assistant", turn=turn))

            assistant_text_parts: list[str] = []
            tool_calls: list[dict] = []

            # 支持流式和非流式两种 models（单测可传 fake）
            llm_ctx = _build_llm_context(
                system_prompt=state.system_prompt,
                messages=llm_messages,
                tools=tools_openai,
            )
            model = state.model

            try:
                # 优先走 stream；如果 models 没 stream 方法就 fallback 到 complete
                if hasattr(models, "stream") and callable(getattr(models, "stream")):
                    async for evt in models.stream(
                        model,
                        llm_ctx,
                        options={"usage_context": usage_context} if usage_context else None,
                        signal=signal,
                    ):
                        if signal.aborted:
                            break
                        await _consume_stream_event(
                            evt,
                            assistant_text_parts=assistant_text_parts,
                            tool_calls=tool_calls,
                            dispatcher=dispatcher,
                            turn=turn,
                        )
                elif hasattr(models, "complete") and callable(getattr(models, "complete")):
                    result = await models.complete(
                        model,
                        llm_ctx,
                        options={"usage_context": usage_context} if usage_context else None,
                        signal=signal,
                    )
                    if result.content:
                        assistant_text_parts.append(result.content)
                        await dispatcher.emit(MessageUpdateEvent(delta=result.content, turn=turn))
                    for tc in getattr(result, "tool_calls", []) or []:
                        tool_calls.append(_normalize_tool_call(tc))
                else:  # pragma: no cover - 仅编程错误
                    raise TypeError(
                        f"models {type(models).__name__} 必须支持 .stream() 或 .complete()",
                    )
            except Exception as exc:  # noqa: BLE001
                if signal.aborted:
                    state.error = AgentError(code="aborted", message=signal.reason or "aborted")
                else:
                    state.error = AgentError(code="llm_error", message=str(exc))
                await dispatcher.emit(MessageEndEvent(
                    role="assistant",
                    turn=turn,
                    content="".join(assistant_text_parts),
                ))
                await dispatcher.emit(TurnEndEvent(turn=turn, tool_results=[]))
                break

            # 组装 assistant 消息存入 state.messages
            final_content = "".join(assistant_text_parts)
            state.pending_tool_calls = list(tool_calls)
            assistant_msg = AssistantMessage(
                content=final_content,
                tool_calls=list(tool_calls),
            )
            state.messages.append(assistant_msg)
            await dispatcher.emit(MessageEndEvent(
                role="assistant",
                turn=turn,
                tool_calls=list(tool_calls),
                content=final_content,
            ))

            # 4) 无 tool_call → 对话自然结束
            if not tool_calls:
                await dispatcher.emit(TurnEndEvent(turn=turn, tool_results=[]))
                break

            # 5) 执行工具（并行/串行）
            tool_results = await execute_tools(
                tool_calls=tool_calls,
                tools=state.tools,
                hooks=hooks,
                dispatcher=dispatcher,
                signal=signal,
                mode=tool_execution_mode,
                turn=turn,
            )

            # 6) 写回 toolResult 消息（每条 tool 一条）
            for r in tool_results:
                content_list = r.content if isinstance(r.content, list) else [{"type": "text", "text": str(r.content)}]
                state.messages.append(ToolResultMessage(
                    call_id=r.call_id,
                    content=content_list,
                    is_error=r.is_error,
                ))
                await dispatcher.emit(MessageStartEvent(role="toolResult", turn=turn))
                await dispatcher.emit(MessageEndEvent(role="toolResult", turn=turn))

            await dispatcher.emit(TurnEndEvent(turn=turn, tool_results=list(tool_results)))
            state.pending_tool_calls.clear()

            # 结束这一轮后再回到 while，开启下一轮
        else:
            # while 正常因 turn_count >= max_turns 退出。
            # 若最后一条 assistant 仍请求了工具但没有后续 turn 执行它们，
            # 视为达到最大 turn 数，标 error 便于上游感知。
            # 注意：AssistantMessage 是工厂函数，返回 AgentMessage，此处用 role 判定。
            last_has_pending_tool = False
            for m in reversed(state.messages):
                if m.role == "assistant":
                    last_has_pending_tool = bool(m.tool_calls)
                    break
            if last_has_pending_tool:
                state.error = AgentError(
                    code="max_turns_reached",
                    message=f"reached max_turns={max_turns}",
                    details={"turn_count": state.turn_count},
                )
    finally:
        state.is_streaming = False
        await dispatcher.emit(AgentEndEvent(error=state.error))


# ---------------------------------------------------------------------------
# LLM stream 事件消费
# ---------------------------------------------------------------------------

async def _consume_stream_event(
    evt: Any,
    *,
    assistant_text_parts: list[str],
    tool_calls: list[dict],
    dispatcher: EventDispatcher,
    turn: int,
) -> None:
    from app.ai.stream import StreamEventType

    etype = getattr(evt, "type", None)
    delta = getattr(evt, "delta", None)

    if etype == StreamEventType.TEXT_DELTA and delta:
        assistant_text_parts.append(delta)
        await dispatcher.emit(MessageUpdateEvent(delta=delta, turn=turn))
    elif etype == StreamEventType.TOOLCALL_START:
        # 新建一个占位 tool_call
        tool_calls.append({
            "id": getattr(evt, "tool_call_id", None) or "",
            "type": "function",
            "function": {
                "name": getattr(evt, "tool_name", "") or "",
                "arguments": "",
            },
        })
    elif etype == StreamEventType.TOOLCALL_DELTA:
        args_delta = getattr(evt, "arguments_delta", "") or ""
        if tool_calls:
            tool_calls[-1]["function"]["arguments"] += args_delta
    elif etype == StreamEventType.TOOLCALL_END:
        # 同步 arguments（覆盖流式累积的增量，避免截断/重复）
        idx = 0
        call_id = getattr(evt, "tool_call_id", None)
        if call_id:
            for i, t in enumerate(tool_calls):
                if t["id"] == call_id:
                    idx = i
                    break
        if tool_calls:
            final_args = getattr(evt, "arguments", None) or tool_calls[idx]["function"]["arguments"]
            tool_calls[idx]["function"]["arguments"] = final_args
            tool_calls[idx]["function"]["name"] = (
                getattr(evt, "tool_name", "") or tool_calls[idx]["function"]["name"]
            )
            if not tool_calls[idx]["id"] and call_id:
                tool_calls[idx]["id"] = call_id
    elif etype == StreamEventType.ERROR:
        # 错误单独由外层 try/except 处理（在 emit error 前）
        pass


def _normalize_tool_call(tc: dict) -> dict:
    """把 complete() 返回的 dict 标准化为 tool_calls list 元素格式。"""
    if "function" in tc:
        return tc
    return {
        "id": tc.get("id", ""),
        "type": "function",
        "function": {
            "name": tc.get("name", ""),
            "arguments": tc.get("arguments", "") or "",
        },
    }


def _build_llm_context(system_prompt: str, messages: list[dict], tools: list[dict] | None) -> Any:
    try:
        from app.ai.provider import LLMContext

        return LLMContext(
            system_prompt=system_prompt or None,
            messages=list(messages),
            tools=tools,
        )
    except Exception:  # pragma: no cover - 单测可以不用真实 LLMContext
        return type("FakeLLMCtx", (), {
            "system_prompt": system_prompt or None,
            "messages": list(messages),
            "tools": tools,
        })()


# ---------------------------------------------------------------------------
# 工具执行：并行/串行 + before_tool_call 权限拦截 + 异常 → isError=true
# ---------------------------------------------------------------------------

async def execute_tools(
    *,
    tool_calls: list[dict],
    tools: list,
    hooks: Hooks,
    dispatcher: EventDispatcher,
    signal: AbortSignal,
    mode: str = "parallel",
    turn: int | None = None,
) -> list[ToolResult]:
    """执行一批 tool_calls。

    返回顺序恒等于 tool_calls 顺序（与完成先后无关）——验收 §7.2。
    """
    n = len(tool_calls)
    results: list[ToolResult | None] = [None] * n

    # 只要本轮有任何一个 tool 标记 serial，或全局模式是 serial，就串行执行
    forced_serial = mode != "parallel" or any(
        (
            next((t for t in tools if t.name == _tc_name(tc)), None)
        ) and (
            next((t for t in tools if t.name == _tc_name(tc)), None).execution_mode == "serial"
        )
        for tc in tool_calls
    )

    async def run_one(i: int, tc: dict) -> None:
        results[i] = await _execute_single_tool(
            index=i,
            tool_call=tc,
            tools=tools,
            hooks=hooks,
            dispatcher=dispatcher,
            signal=signal,
            turn=turn,
        )

    if forced_serial:
        for i, tc in enumerate(tool_calls):
            await run_one(i, tc)
    else:
        tasks = [asyncio.create_task(run_one(i, tc)) for i, tc in enumerate(tool_calls)]
        await asyncio.gather(*tasks, return_exceptions=False)

    return [r if r is not None else ToolResult(call_id="", content=[], is_error=True) for r in results]


def _tc_name(tc: dict) -> str:
    f = tc.get("function") or {}
    return f.get("name", "") if isinstance(f, dict) else getattr(f, "name", "")


async def _execute_single_tool(
    *,
    index: int,  # noqa: ARG001 - 保留以用于日志
    tool_call: dict,
    tools: list,
    hooks: Hooks,
    dispatcher: EventDispatcher,
    signal: AbortSignal,
    turn: int | None,
) -> ToolResult:
    call_id = tool_call.get("id") or f"call-missing-{index}"
    name = _tc_name(tool_call)
    await dispatcher.emit(ToolExecutionStartEvent(call_id=call_id, tool_name=name, turn=turn))

    try:
        tool = next((t for t in tools if t.name == name), None)
        if tool is None:
            return ToolResult(
                call_id=call_id,
                content=[{"type": "text", "text": f"tool '{name}' not found"}],
                is_error=True,
            )

        # 参数解析：function.arguments 可能是 JSON string 或 dict
        raw_args = (tool_call.get("function") or {}).get("arguments", "") if "function" in tool_call else ""
        args = _parse_args(raw_args)

        # before_tool_call：权限/拦截钩子
        before_hook = hooks.resolve_before_tool()
        block_result = await before_hook(tool_call, args, {"turn": turn})
        if isinstance(block_result, dict) and block_result.get("block"):
            return ToolResult(
                call_id=call_id,
                content=[{"type": "text", "text": str(block_result.get("reason", "blocked by before_tool_call"))}],
                is_error=True,
                details={"blocked": True, **block_result},
            )

        if signal.aborted:
            return ToolResult(
                call_id=call_id,
                content=[{"type": "text", "text": signal.reason or "aborted"}],
                is_error=True,
                details={"aborted": True},
            )

        # 真实调用
        if tool.execute is None:
            return ToolResult(
                call_id=call_id,
                content=[{"type": "text", "text": f"tool '{name}' has no execute handler"}],
                is_error=True,
            )

        async def on_update(details: dict) -> None:
            await dispatcher.emit(ToolExecutionUpdateEvent(call_id=call_id, details=details, turn=turn))

        result = await tool.execute(call_id, args, signal, on_update)

        # 允许返回 ToolResult 或等价 dict
        if isinstance(result, ToolResult):
            final = result
            if not final.call_id:
                final.call_id = call_id
        elif isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            final = ToolResult(
                call_id=result.get("call_id") or call_id,
                content=content or [],
                details=result.get("details") or {},
                is_error=bool(result.get("is_error", False)),
            )
        else:
            # 纯值/字符串：当作成功的 text 返回
            text = str(result)
            final = ToolResult(
                call_id=call_id,
                content=[{"type": "text", "text": text}],
            )
        return final

    except Exception as exc:  # noqa: BLE001 - 验收：tool 异常不 crash agent
        logger.warning("tool '%s' threw: %s", name, exc, exc_info=True)
        return ToolResult(
            call_id=call_id,
            content=[{"type": "text", "text": str(exc)}],
            is_error=True,
            details={"exception_type": type(exc).__name__},
        )
    finally:
        # 一定派发 TOOL_EXECUTION_END；具体 result 由上面对象传入
        pass


# 执行完成后由 execute_tools 外层 emit TOOL_EXECUTION_END
async def _emit_tool_end(dispatcher: EventDispatcher, call_id: str, result: ToolResult, turn: int | None) -> None:  # pragma: no cover - 调用点内联
    await dispatcher.emit(ToolExecutionEndEvent(call_id=call_id, result=result, turn=turn))


# 由于上面 finally 里没发 end，这里在 execute_tools 外层补上。
# 我们实际做法是重写 execute_tools：在每个 run_one 结束后派发。这里不改动上面的 execute_tools 签名，
# 直接让 run_one 返回结果后统一派发（见下 patch）。

async def _run_one_with_end(
    i: int,
    tc: dict,
    *,
    tools: list,
    hooks: Hooks,
    dispatcher: EventDispatcher,
    signal: AbortSignal,
    turn: int | None,
    results_ref: list,
) -> None:
    result = await _execute_single_tool(
        index=i, tool_call=tc, tools=tools, hooks=hooks,
        dispatcher=dispatcher, signal=signal, turn=turn,
    )
    results_ref[i] = result
    await dispatcher.emit(ToolExecutionEndEvent(call_id=result.call_id, result=result, turn=turn))


# 覆盖 execute_tools：统一 dispatch TOOL_EXECUTION_END 并保持结果顺序
async def execute_tools(  # noqa: F811 - 有意覆盖上方旧实现
    *,
    tool_calls: list[dict],
    tools: list,
    hooks: Hooks,
    dispatcher: EventDispatcher,
    signal: AbortSignal,
    mode: str = "parallel",
    turn: int | None = None,
) -> list[ToolResult]:
    n = len(tool_calls)
    results: list[ToolResult | None] = [None] * n

    forced_serial = mode != "parallel" or any(
        (_find_tool(tools, _tc_name(tc)) or type("x", (), {"execution_mode": "serial"})()).execution_mode == "serial"
        for tc in tool_calls
    )

    if forced_serial:
        for i, tc in enumerate(tool_calls):
            await _run_one_with_end(
                i, tc, tools=tools, hooks=hooks, dispatcher=dispatcher,
                signal=signal, turn=turn, results_ref=results,
            )
    else:
        tasks = [
            asyncio.create_task(_run_one_with_end(
                i, tc, tools=tools, hooks=hooks, dispatcher=dispatcher,
                signal=signal, turn=turn, results_ref=results,
            ))
            for i, tc in enumerate(tool_calls)
        ]
        await asyncio.gather(*tasks, return_exceptions=False)

    return [r if r is not None else ToolResult(call_id="", content=[], is_error=True) for r in results]


def _find_tool(tools: list, name: str):
    return next((t for t in tools if t.name == name), None)


def _parse_args(raw: str | dict) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            # 解析失败时包装为 {"_raw": ...}，让工具自己处理
            return {"_raw": raw}
    return {}
