"""P2-T5: Agent 统一入口，替代 chat_service 三函数内部实现。

提供三个函数：
- ``run_chat``：替代 ``chat()``（RAG + Tool Calling，max 3 轮 + 兜底）
- ``run_free_chat``：替代 ``free_chat()``（非流式）
- ``run_free_chat_stream``：替代 ``free_chat_stream()``（流式）

设计要点：
- 复用 P1 ``Agent`` + P2 ``ChatContextHooks`` + ``create_builtin_tools`` + ``sse_bridge``。
- ``run_chat`` 保留旧 ``chat()`` 的 max_rounds=3 + 兜底无 tools 调用语义：
  Agent max_turns=3；若 ``max_turns_reached`` 则再做一次 ``models.complete`` 无 tools 调用。
- ``run_free_chat`` / ``run_free_chat_stream`` 在 P3 阶段二启用：
  真实 workspace/memory/skill/wiki/MCP 能力进入请求级 CapabilityRegistry，
  模型首轮只看到三个 L1/L2/L3 元工具；流式路径注入 LongTaskManager，
  task_card/task_card_progress 经 SSE 派发。
- usage_context phase 与旧实现完全一致（free_chat / free_chat_stream / chat_tool_call / chat_final）。
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Optional

from app.agent.builtin_tools import create_builtin_tools
from app.agent.capability_catalog import (
    build_free_chat_registry,
    create_progressive_tools,
)
from app.agent.chat_adapter import (
    ChatContextHooks,
    build_chat_hooks,
    build_free_chat_hooks,
)
from app.agent.memory import create_memory_tools
from app.agent.core.agent import Agent
from app.agent.core.message import AgentMessage, AssistantMessage, UserMessage
from app.agent.core.state import AgentState
from app.agent.long_task import LongTaskManager
from app.agent.learning_tools import create_learning_tools
from app.agent.skill_loader import load_skills
from app.agent.sse_bridge import agent_events_to_sse_dict
from app.agent.workspace import create_workspace_tools
from app.utils.logger import get_logger

logger = get_logger(__name__)


#: P3 阶段二：free_chat 路径 Agent 最大轮次（允许若干轮工具调用）。
_FREE_CHAT_MAX_TURNS = 6


# ---------------------------------------------------------------------------
# run_chat：替代 chat()（RAG + Tool Calling）
# ---------------------------------------------------------------------------

async def run_chat(
    task_id: str,
    question: str,
    history: list[dict],
    provider_id: str,
    model_name: str,
) -> dict:
    """RAG + Tool Calling 问答（替代 ``chat_service.chat``）。

    语义对齐：
    - 3 轮 tool calling（Agent max_turns=3）
    - 若 3 轮仍有 tool_calls → 第 4 次无 tools 调用（与旧 ``chat_final`` 一致）
    - usage phase: chat_tool_call（前 3 轮）/ chat_final（兜底）
    """
    from app.ai.provider import LLMContext

    models, model = _resolve_model(provider_id, model_name)
    hooks = build_chat_hooks(task_id, question)
    # P3-T2: 追加记忆工具，让 Agent 可主动维护 user_profile / research_space
    tools = create_builtin_tools(task_id) + create_memory_tools()
    messages = _history_to_agent_messages(history[-20:])

    agent = Agent(
        initial_state=AgentState(model=model, tools=tools, messages=messages),
        max_turns=3,
        tool_execution="parallel",
        models=models,
        transform_context=hooks.transform_context,
        convert_to_llm=hooks.convert_to_llm,
        usage_context={"phase": "chat_tool_call", "task_id": task_id},
    )

    await agent.prompt(question)
    await agent.wait_for_idle()

    # 兜底：max_turns_reached → 无 tools 最终调用（对齐旧 chat_final）
    if agent.error is not None and agent.error.code == "max_turns_reached":
        logger.info("chat agent max_turns reached, fallback to no-tools final call")
        final_messages = hooks.convert_to_llm(
            hooks.transform_context(agent.messages, _noop_signal())
        )
        ctx = LLMContext(messages=final_messages, temperature=0.7)
        final_result = await models.complete(
            model,
            ctx,
            options={"usage_context": {"phase": "chat_final", "task_id": task_id}},
        )
        return {"answer": final_result.content, "sources": hooks.sources}

    if agent.error is not None:
        raise RuntimeError(agent.error.message or "agent error")

    answer = _extract_last_assistant_text(agent.messages)
    return {"answer": answer, "sources": hooks.sources}


# ---------------------------------------------------------------------------
# run_free_chat：替代 free_chat()（非流式）
# ---------------------------------------------------------------------------

def _build_free_chat_tools(
    conversation_id: Optional[str],
    long_task_manager: Optional[LongTaskManager] = None,
) -> list:
    """兼容性 helper：构造旧式 free_chat 扁平工具集。

    渐进式运行路径不再调用本函数，而由 ``build_free_chat_registry`` 注册以下
    真实能力；保留 helper 供既有内部调用/回滚，不重新暴露到模型首轮。

    - memory 工具始终注册（user_profile / research_space 维护）。
    - workspace 工具仅在 conversation_id 非空时注册（仅访问当前会话工作空间）。
    - skill 工具经 ``load_skills`` 加载；非流式场景 long_task_manager=None，
      长任务 skill 会因缺 manager 返回 error ToolResult（可接受，不 crash）。
      流式场景传入 long_task_manager，长任务 skill 经其接管。
    """
    tools = create_memory_tools()
    if conversation_id:
        tools = create_workspace_tools(conversation_id) + create_learning_tools(conversation_id) + tools
    skill_tools = load_skills(long_task_manager=long_task_manager)
    tools.extend(skill_tools)
    return tools


async def run_free_chat(
    question: str,
    history: list[dict],
    provider_id: str,
    model_name: str,
    conversation_id: Optional[str] = None,
    linked_task_id: Optional[str] = None,
    use_wiki: bool = True,
    asset_content: Optional[str] = None,
) -> dict:
    """非流式普通聊天（替代 ``chat_service.free_chat``）。

    P3.1：真实能力进入 CapabilityRegistry；初始只注册三个渐进式元工具，
    max_turns=6。
    """
    models, model = _resolve_model(provider_id, model_name)
    hooks = build_free_chat_hooks(
        question, linked_task_id, use_wiki, conversation_id, asset_content
    )
    registry = build_free_chat_registry(
        conversation_id=conversation_id,
        linked_task_id=linked_task_id,
        use_wiki=use_wiki,
        long_task_manager=None,
        source_sink=hooks.sources,
    )
    try:
        hooks.system_prompt = (
            registry.build_l0_summary(question) + "\n\n" + hooks.system_prompt
        )
        messages = _history_to_agent_messages(history[-20:])
        tools = create_progressive_tools(registry)

        agent = Agent(
            initial_state=AgentState(model=model, tools=tools, messages=messages),
            max_turns=_FREE_CHAT_MAX_TURNS,
            tool_execution="parallel",
            models=models,
            transform_context=hooks.transform_context,
            convert_to_llm=hooks.convert_to_llm,
            usage_context={"phase": "free_chat", "task_id": linked_task_id},
        )

        await agent.prompt(question)
        await agent.wait_for_idle()

        if agent.error is not None:
            raise RuntimeError(agent.error.message or "agent error")

        answer = _extract_last_assistant_text(agent.messages)
        return {"answer": answer, "sources": hooks.sources}
    finally:
        await registry.close()


# ---------------------------------------------------------------------------
# run_free_chat_stream：替代 free_chat_stream()（流式）
# ---------------------------------------------------------------------------

async def run_free_chat_stream(
    question: str,
    history: list[dict],
    provider_id: str,
    model_name: str,
    conversation_id: Optional[str] = None,
    linked_task_id: Optional[str] = None,
    use_wiki: bool = True,
    asset_content: Optional[str] = None,
) -> AsyncIterator[dict]:
    """流式普通聊天（替代 ``chat_service.free_chat_stream``）。

    P3.1：真实能力进入 CapabilityRegistry；初始只注册三个渐进式元工具，
    max_turns=6。注入 LongTaskManager，task_card/task_card_progress 经 SSE 派发，
    done 后流不立即关闭，等长任务收尾；registry 在流结束/断开时关闭。

    Yields:
        旧 SSE dict：``{"type":"delta","content":...}`` / ``{"type":"done",...}`` /
        ``{"type":"error",...}``；长任务启用时额外有 ``task_card`` / ``task_card_progress``。
    """
    models, model = _resolve_model(provider_id, model_name)
    hooks = build_free_chat_hooks(
        question, linked_task_id, use_wiki, conversation_id, asset_content
    )
    messages = _history_to_agent_messages(history[-20:])

    # 构造 LongTaskManager：dispatcher 由 sse_bridge 注入；auto_follow_up=False（spec §3）。
    # 仅在 conversation_id 非空时启用（长任务卡片需写入 conversation_messages）。
    long_task_manager: Optional[LongTaskManager] = None
    if conversation_id:
        long_task_manager = LongTaskManager(
            agent=None,
            auto_follow_up=False,
            dispatcher=None,
            default_timeout=0,
        )
        long_task_manager._conversation_id = conversation_id

    registry = build_free_chat_registry(
        conversation_id=conversation_id,
        linked_task_id=linked_task_id,
        use_wiki=use_wiki,
        long_task_manager=long_task_manager,
        source_sink=hooks.sources,
    )
    try:
        hooks.system_prompt = (
            registry.build_l0_summary(question) + "\n\n" + hooks.system_prompt
        )
        tools = create_progressive_tools(registry)

        agent = Agent(
            initial_state=AgentState(model=model, tools=tools, messages=messages),
            max_turns=_FREE_CHAT_MAX_TURNS,
            tool_execution="parallel",
            models=models,
            transform_context=hooks.transform_context,
            convert_to_llm=hooks.convert_to_llm,
            usage_context={"phase": "free_chat_stream", "task_id": linked_task_id},
        )

        async for event in agent_events_to_sse_dict(
            agent, question, hooks.sources, long_task_manager=long_task_manager
        ):
            yield event
    finally:
        await registry.close()


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _extract_last_assistant_text(messages: list[AgentMessage]) -> str:
    """从 messages 中提取最后一条 assistant 消息的文本。"""
    for msg in reversed(messages):
        if msg.role != "assistant":
            continue
        if isinstance(msg.content, str) and msg.content:
            return msg.content
        if isinstance(msg.content, list):
            # 拼接 [{"type":"text","text":...}] 内容
            parts = [
                c.get("text", "")
                for c in msg.content
                if isinstance(c, dict) and c.get("type") == "text"
            ]
            text = "".join(parts)
            if text:
                return text
    return ""


class _noop_signal:
    """transform_context 需要 signal 参数，但兜底场景不需要真 signal。"""

    @property
    def aborted(self) -> bool:
        return False

    @property
    def reason(self) -> None:
        return None


def _history_to_agent_messages(history: list[dict]) -> list[AgentMessage]:
    """把旧 history dict 列表转为 AgentMessage 列表。

    旧格式：``[{"role": "user"|"assistant", "content": "..."}]``
    """
    out: list[AgentMessage] = []
    for msg in history or []:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "assistant":
            out.append(AssistantMessage(content=content))
        else:
            out.append(UserMessage(content=content))
    return out


def _resolve_model(provider_id: str, model_name: str):
    """创建 Models + 获取 Model；model 不存在时抛 ValueError（对齐旧实现）。"""
    from app.ai import create_models

    models = create_models()
    model = models.get_model(provider_id, model_name)
    if model is None:
        raise ValueError(f"未找到模型供应商: {provider_id}")
    return models, model


__all__ = ["run_chat", "run_free_chat", "run_free_chat_stream"]
