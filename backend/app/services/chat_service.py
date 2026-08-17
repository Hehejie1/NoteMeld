import json
from typing import AsyncIterator, Optional

from app.ai import create_models
from app.ai.provider import LLMContext
from app.ai.stream import StreamEventType
from app.services.vector_store import VectorStoreManager
from app.services.chat_tools import TOOLS, execute_tool
from app.services.wiki_search import WikiSearch
from app.services.context_builder import QueryContext, build_query_context
from app.services.query_intent import build_vector_quotas, classify_query_intent
from app.utils.logger import get_logger
from app.utils.storage_paths import note_output_dir

logger = get_logger(__name__)

SYSTEM_PROMPT = """你是一个视频笔记问答助手。你拥有以下能力：

1. 系统已自动检索了一些相关内容作为初始参考（见下方）
2. 你可以调用工具主动查询更多信息：
   - lookup_transcript: 查询视频原始转录文本（支持按时间、关键词、位置筛选）
   - get_video_info: 获取视频元信息（标题、作者、简介、标签等）
   - get_note_content: 获取完整笔记内容

--- 初始检索内容 ---
{context}
---

回答要求：
- 如果初始检索内容不足以回答问题，请主动调用工具获取更多信息
- 回答关于视频具体原话、细节时，用 lookup_transcript 查询原文
- 回答关于作者、标题等基本信息时，用 get_video_info 查询
- 请用中文回答，保持简洁准确"""

FREE_CHAT_SYSTEM_PROMPT = """你是 NoteMeld 的知识库聊天助手。

你可以基于三类信息回答：
1. 当前关联笔记的检索内容
2. llm wiki 的相关知识片段
3. 用户当前对话上下文
4. 当前会话上传的 Markdown 资产

--- 关联笔记上下文 ---
{note_context}
---

--- 会话资产上下文 ---
{asset_context}
---

--- llm wiki 上下文 ---
{wiki_context}
---

回答要求：
- 优先结合可用上下文回答
- 上下文不足时可以直接进行普通聊天，但不要伪造来源
- 用中文回答，简洁准确"""


def _build_context(chunks: list[dict]) -> str:
    """将检索到的片段拼接为上下文文本。"""
    parts = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        source_type = meta.get("source_type", "unknown")
        if source_type == "meta":
            label = "[视频信息]"
        elif source_type == "markdown":
            label = f"[笔记 - {meta.get('section_title', '')}]"
        else:
            start = meta.get("start_time", 0)
            end = meta.get("end_time", 0)
            label = f"[转录 - {start:.0f}s~{end:.0f}s]"
        parts.append(f"{label}\n{chunk['text']}")
    return "\n\n".join(parts)


def _build_sources(chunks: list[dict]) -> list[dict]:
    """从检索片段中提取来源信息。"""
    sources = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        source = {
            "text": chunk["text"][:200],
            "source_type": meta.get("source_type", "unknown"),
        }
        if meta.get("section_title"):
            source["section_title"] = meta["section_title"]
        if meta.get("start_time") is not None:
            source["start_time"] = meta["start_time"]
        if meta.get("end_time") is not None:
            source["end_time"] = meta["end_time"]
        sources.append(source)
    return sources


def _build_wiki_context(sources: list[dict]) -> str:
    if not sources:
        return "（未检索到相关 Wiki 内容）"
    return "\n\n".join(
        f"[Wiki - {source.get('title', source.get('page_id', '未知页面'))}]\n{source.get('text', '')}"
        for source in sources
    )


def _prepare_free_chat_context(
    question: str,
    linked_task_id: Optional[str],
    use_wiki: bool,
    *,
    prefetch_wiki: bool = True,
) -> QueryContext:
    """构建 free-chat 上下文。

    ``prefetch_wiki`` 默认保持旧调用方语义；Agent 路径关闭预取，由 L0-L3
    能力目录决定是否在 L3 执行 Wiki 搜索。
    """
    intent = classify_query_intent(question)
    note_chunks: list[dict] = []
    if linked_task_id and intent.scope in ("current_note", "mixed"):
        try:
            note_chunks = VectorStoreManager().query(
                linked_task_id,
                question,
                n_results=6,
                quotas=build_vector_quotas(intent),
            )
        except Exception as exc:
            logger.warning(f"关联笔记检索失败，降级为 Wiki/普通聊天: {exc}")

    wiki_sources: list[dict] = []
    if (
        use_wiki
        and prefetch_wiki
        and intent.scope in ("global_wiki", "mixed", "current_note")
    ):
        try:
            wiki_sources = WikiSearch(note_output_dir() / "wiki").search(
                question,
                limit=8,
                intent=intent,
                linked_task_id=linked_task_id,
            )
        except Exception as exc:
            logger.warning(f"Wiki 检索失败，降级为普通聊天: {exc}")

    return build_query_context(question, intent, note_chunks, wiki_sources)


def _resolve_asset_context(conversation_id: Optional[str], asset_content: Optional[str]) -> str:
    from app.services.conversation_context_refs import split_asset_and_context_refs

    normalized_content, rendered_refs = split_asset_and_context_refs(asset_content)
    if normalized_content:
        return "\n\n".join(part for part in (normalized_content, rendered_refs) if part)

    normalized_conversation_id = (conversation_id or "").strip()
    if not normalized_conversation_id:
        return rendered_refs

    try:
        from app.services.conversation_asset_store import ConversationAssetStore

        assets = ConversationAssetStore().list_assets(normalized_conversation_id)
    except Exception as exc:
        logger.warning(f"读取会话资产失败，降级为空上下文: {exc}")
        return rendered_refs

    if not assets:
        return rendered_refs

    rendered_assets: list[str] = []
    for item in assets[-3:]:
        title = str(item.get("title") or "未命名资产").strip() or "未命名资产"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        rendered_assets.append(f"# {title}\n{content}")
    return "\n\n".join([*rendered_assets, *([rendered_refs] if rendered_refs else [])])


async def free_chat(
    question: str,
    history: list[dict],
    provider_id: str,
    model_name: str,
    conversation_id: Optional[str] = None,
    linked_task_id: Optional[str] = None,
    use_wiki: bool = True,
    asset_content: Optional[str] = None,
) -> dict:
    query_context = _prepare_free_chat_context(question, linked_task_id, use_wiki)
    resolved_asset_content = _resolve_asset_context(conversation_id, asset_content)

    messages = [
        {
            "role": "system",
            "content": FREE_CHAT_SYSTEM_PROMPT.format(
                note_context=query_context.context_text,
                asset_context=resolved_asset_content or "（当前没有上传的会话资产）",
                wiki_context="已合并到上方检索上下文中。",
            ),
        }
    ]
    for msg in history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    models = create_models()
    model = models.get_model(provider_id, model_name)
    if model is None:
        raise ValueError(f"未找到模型供应商: {provider_id}")

    ctx = LLMContext(messages=messages, temperature=0.7)
    # usage 由 Models.complete() 自动写入（phase=free_chat, task_id=linked_task_id）
    result = await models.complete(
        model,
        ctx,
        options={"usage_context": {
            "phase": "free_chat",
            "task_id": linked_task_id,
        }},
    )
    return {"answer": result.content, "sources": query_context.sources}


async def free_chat_stream(
    question: str,
    history: list[dict],
    provider_id: str,
    model_name: str,
    conversation_id: Optional[str] = None,
    linked_task_id: Optional[str] = None,
    use_wiki: bool = True,
    asset_content: Optional[str] = None,
) -> AsyncIterator[dict]:
    query_context = _prepare_free_chat_context(question, linked_task_id, use_wiki)
    resolved_asset_content = _resolve_asset_context(conversation_id, asset_content)

    messages = [
        {
            "role": "system",
            "content": FREE_CHAT_SYSTEM_PROMPT.format(
                note_context=query_context.context_text,
                asset_context=resolved_asset_content or "（当前没有上传的会话资产）",
                wiki_context="已合并到上方检索上下文中。",
            ),
        }
    ]
    for msg in history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    models = create_models()
    model = models.get_model(provider_id, model_name)
    if model is None:
        raise ValueError(f"未找到模型供应商: {provider_id}")

    ctx = LLMContext(messages=messages, temperature=0.7)
    # usage 由 Models.stream() 自动写入（成功写一条，失败写一条 status=failed）
    full_answer = ""
    async for event in models.stream(
        model,
        ctx,
        options={"usage_context": {
            "phase": "free_chat_stream",
            "task_id": linked_task_id,
        }},
    ):
        if event.type == StreamEventType.TEXT_DELTA:
            delta = event.delta or ""
            if not delta:
                continue
            full_answer += delta
            yield {"type": "delta", "content": delta}
        elif event.type == StreamEventType.DONE:
            yield {"type": "done", "answer": full_answer, "sources": query_context.sources}
        elif event.type == StreamEventType.ERROR:
            # usage 已由 Models.stream() 写为 status=failed
            raise event.error


async def chat(
    task_id: str,
    question: str,
    history: list[dict],
    provider_id: str,
    model_name: str,
) -> dict:
    """
    RAG + Tool Calling 问答。
    1. 向量检索初始上下文
    2. 调用 LLM（带 tools）
    3. 如果 LLM 调用了工具，执行工具并将结果返回给 LLM
    4. 循环直到 LLM 给出最终回答
    """
    vector_store = VectorStoreManager()

    # 1. 检索初始上下文
    chunks = vector_store.query(task_id, question, n_results=6)
    context = _build_context(chunks) if chunks else "（未检索到相关内容，请使用工具查询）"
    sources = _build_sources(chunks) if chunks else []

    # 2. 构建消息
    system_msg = SYSTEM_PROMPT.format(context=context)
    messages = [{"role": "system", "content": system_msg}]

    for msg in history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": question})

    # 3. 获取 Model 对象
    models = create_models()
    model = models.get_model(provider_id, model_name)
    if model is None:
        raise ValueError(f"未找到模型供应商: {provider_id}")

    logger.info(f"Chat: task_id={task_id}, model={model_name}")

    # 4. Tool calling 循环（最多 3 轮）
    max_rounds = 3
    for round_i in range(max_rounds):
        # usage 由 Models.complete() 自动写入（phase=chat_tool_call）
        ctx = LLMContext(messages=messages, tools=TOOLS, temperature=0.7)
        result = await models.complete(
            model,
            ctx,
            options={"usage_context": {
                "phase": "chat_tool_call",
                "task_id": task_id,
                "request_meta": {"round": round_i + 1, "has_tools": True},
            }},
        )

        # 没有工具调用，直接返回
        if not result.tool_calls:
            return {"answer": result.content, "sources": sources}

        # 处理工具调用：将 assistant 消息（含 tool_calls）追加到 messages
        messages.append({
            "role": "assistant",
            "content": result.content or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in result.tool_calls
            ],
        })

        for tc in result.tool_calls:
            fn_name = tc["name"]
            try:
                fn_args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                fn_args = {}

            logger.info(f"Tool call [{round_i+1}/{max_rounds}]: {fn_name}({fn_args})")

            tool_result = execute_tool(task_id, fn_name, fn_args)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_result,
            })

    # 超过最大轮次，做最后一次不带 tools 的调用
    # usage 由 Models.complete() 自动写入（phase=chat_final）
    ctx = LLMContext(messages=messages, temperature=0.7)
    result = await models.complete(
        model,
        ctx,
        options={"usage_context": {
            "phase": "chat_final",
            "task_id": task_id,
        }},
    )
    return {"answer": result.content, "sources": sources}
