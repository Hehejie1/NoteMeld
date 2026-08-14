"""P2-T3: 把旧 chat_service 的上下文构建封装为 Agent hooks。

提供两个 Hook 工厂：
- ``build_chat_hooks``：用于 ``chat()``（基于 task_id 的 RAG + Tool Calling）
- ``build_free_chat_hooks``：用于 ``free_chat()`` / ``free_chat_stream()``
  （保留 linked_task_id + asset_content 上下文，Wiki 改由渐进式能力按需检索）

设计要点：
- 复用 ``chat_service`` 已有的 ``_prepare_free_chat_context`` /
  ``_resolve_asset_context`` / ``_build_context`` / ``_build_sources`` 函数，
  确保上下文等价（spec §验收 1）。
- ``transform_context`` 在 messages 列表前注入 SystemMessage（含 RAG/wiki/asset 上下文）。
- ``convert_to_llm`` 复用 P1 core 默认实现（``_default_convert_to_llm``），它能正确
  处理 system / user / assistant / toolResult 角色。
- ``sources`` 通过 hooks 实例属性暴露给上层 ``agent_service``，用于 SSE done 事件回填。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.agent.core.hooks import _default_convert_to_llm
from app.agent.core.message import AgentMessage
from app.agent.core.signal import AbortSignal
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Hook 容器
# ---------------------------------------------------------------------------

@dataclass
class ChatContextHooks:
    """通用 Hook 容器：持有 system prompt + sources，供 agent_service 读取。

    Attributes:
        system_prompt: 已格式化的 system prompt（含 RAG/wiki/asset 上下文）。
        sources: 检索来源列表，用于 SSE done 事件回填。
    """

    system_prompt: str = ""
    sources: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # transform_context：注入 system 消息
    # ------------------------------------------------------------------ #
    def transform_context(self, messages: list[AgentMessage], signal: AbortSignal) -> list[AgentMessage]:  # noqa: ARG002
        if not self.system_prompt:
            return list(messages)
        head = AgentMessage(role="system", content=self.system_prompt)
        # 避免重复注入（continue_/follow_up 场景多次进入 loop）
        if messages and messages[0].role == "system" and messages[0].content == self.system_prompt:
            return list(messages)
        return [head, *list(messages)]

    # ------------------------------------------------------------------ #
    # convert_to_llm：复用 P1 默认实现
    # ------------------------------------------------------------------ #
    def convert_to_llm(self, messages: list[AgentMessage]) -> list[dict]:
        return _default_convert_to_llm(messages)


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def _memory_prefix(rs_id: Optional[str] = None) -> str:
    """P3 阶段二: 读取全局用户画像 + 当前会话研究空间记忆前缀，拼到 system prompt 前。

    Args:
        rs_id: 研究空间 id；None 时不注入研究空间记忆。容错：失败返回空串。

    注入顺序：user_profile（全局）→ research_space（cid 绑定的 rs_id）。
    """
    try:
        from app.agent.memory import MemoryManager

        return MemoryManager().build_system_prefix(rs_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory prefix 构建失败，跳过注入: %s", exc)
        return ""


def _resolve_research_space_id(conversation_id: Optional[str]) -> Optional[str]:
    """从 conversations 表读 rs_id；容错返回 None。"""
    if not conversation_id:
        return None
    try:
        from app.services.conversation_store import get_conversation_research_space_id

        return get_conversation_research_space_id(conversation_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取 conversation research_space_id 失败 cid=%s: %s", conversation_id, exc)
        return None


def build_chat_hooks(task_id: str, question: str) -> ChatContextHooks:
    """为 ``chat()``（RAG + Tool Calling）构建 hooks。

    复用 ``chat_service._build_context`` / ``_build_sources``。
    """
    from app.services.chat_service import SYSTEM_PROMPT, _build_context, _build_sources
    from app.services.vector_store import VectorStoreManager

    chunks: list[dict] = []
    try:
        chunks = VectorStoreManager().query(task_id, question, n_results=6)
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat hooks vector query 失败: %s", exc)

    context_text = _build_context(chunks) if chunks else "（未检索到相关内容，请使用工具查询）"
    sources = _build_sources(chunks) if chunks else []
    system_prompt = SYSTEM_PROMPT.format(context=context_text)
    # P3-T2: 叠加长期记忆前缀（user_profile 全局；run_chat 无 cid，rs_id=None）
    memory_prefix = _memory_prefix()
    if memory_prefix:
        system_prompt = memory_prefix + system_prompt
    return ChatContextHooks(system_prompt=system_prompt, sources=sources)


def build_free_chat_hooks(
    question: str,
    linked_task_id: Optional[str],
    use_wiki: bool,
    conversation_id: Optional[str],
    asset_content: Optional[str],
) -> ChatContextHooks:
    """为 ``free_chat()`` / ``free_chat_stream()`` 构建 hooks。

    复用 ``chat_service._prepare_free_chat_context`` / ``_resolve_asset_context``；
    关联笔记与资产保持旧语义，Wiki 显式关闭 prefetch，由 L0-L3 能力目录接管。

    P3 阶段二：通过 conversation_id 查询绑定的 research_space_id，
    注入对应研究空间记忆前缀；cid 为空或查询失败时降级为仅 user_profile。
    """
    from app.services.chat_service import (
        FREE_CHAT_SYSTEM_PROMPT,
        _prepare_free_chat_context,
        _resolve_asset_context,
    )

    query_context = _prepare_free_chat_context(
        question,
        linked_task_id,
        use_wiki,
        prefetch_wiki=False,
    )
    asset_context_text = _resolve_asset_context(conversation_id, asset_content)
    wiki_context_text = (
        "首轮未预取 Wiki 正文；涉及个人知识、来源或证据时，请按能力地图使用 L1→L2→L3。"
        if use_wiki
        else "Wiki 已由 use_wiki=false 关闭。"
    )
    system_prompt = FREE_CHAT_SYSTEM_PROMPT.format(
        note_context=query_context.context_text,
        asset_context=asset_context_text or "（当前没有上传的会话资产）",
        wiki_context=wiki_context_text,
    )
    # P3 阶段二：叠加长期记忆前缀（user_profile + cid 绑定的 research_space）
    rs_id = _resolve_research_space_id(conversation_id)
    memory_prefix = _memory_prefix(rs_id=rs_id)
    if memory_prefix:
        system_prompt = memory_prefix + system_prompt
    return ChatContextHooks(system_prompt=system_prompt, sources=list(query_context.sources))


__all__ = ["ChatContextHooks", "build_chat_hooks", "build_free_chat_hooks"]
