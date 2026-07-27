from typing import Optional
import json

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from app.services.chat_service import chat as chat_service
from app.services.chat_service import free_chat as free_chat_service
from app.services.chat_service import free_chat_stream as free_chat_stream_service
from app.services.vector_store import VectorStoreManager
from app.utils.logger import get_logger
from app.utils.response import ResponseWrapper as R

logger = get_logger(__name__)

router = APIRouter()

# 索引状态追踪: task_id -> "indexing" | "indexed" | "failed"
_index_status: dict[str, str] = {}


class IndexRequest(BaseModel):
    task_id: str


class ChatMessage(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    task_id: str
    question: str
    history: list[ChatMessage] = []
    provider_id: str
    model_name: str


class FreeAskRequest(BaseModel):
    question: str
    history: list[ChatMessage] = []
    provider_id: str
    model_name: str
    conversation_id: Optional[str] = None
    linked_task_id: Optional[str] = None
    use_wiki: bool = True
    asset_content: Optional[str] = None


def _do_index(task_id: str):
    """后台执行索引任务。"""
    try:
        _index_status[task_id] = "indexing"
        store = VectorStoreManager()
        store.index_task(task_id)
        _index_status[task_id] = "indexed"
        logger.info(f"索引完成: {task_id}")
    except Exception as e:
        _index_status[task_id] = "failed"
        logger.error(f"索引失败: {task_id}, {e}")


@router.post("/chat/index")
def index_task(data: IndexRequest, background_tasks: BackgroundTasks):
    """触发后台索引，立即返回。"""
    if _index_status.get(data.task_id) == "indexing":
        return R.success(msg="正在索引中")

    # 如果已经索引过，直接返回
    store = VectorStoreManager()
    if store.is_indexed(data.task_id):
        _index_status[data.task_id] = "indexed"
        return R.success(msg="已完成索引")

    _index_status[data.task_id] = "indexing"
    background_tasks.add_task(_do_index, data.task_id)
    return R.success(msg="开始索引")


@router.get("/chat/status")
def chat_status(task_id: str):
    """返回索引状态：idle / indexing / indexed / failed。"""
    try:
        # 优先检查内存状态
        status = _index_status.get(task_id)
        if status:
            return R.success(data={"status": status, "indexed": status == "indexed"})

        # 内存没有记录，检查持久化
        store = VectorStoreManager()
        indexed = store.is_indexed(task_id)
        if indexed:
            _index_status[task_id] = "indexed"
        return R.success(data={"status": "indexed" if indexed else "idle", "indexed": indexed})
    except Exception as e:
        logger.error(f"查询索引状态失败: {e}")
        return R.success(data={"status": "idle", "indexed": False})


@router.post("/chat/ask")
def ask_question(data: AskRequest):
    """基于笔记内容的 RAG 问答。"""
    try:
        history = [{"role": m.role, "content": m.content} for m in data.history]
        result = chat_service(
            task_id=data.task_id,
            question=data.question,
            history=history,
            provider_id=data.provider_id,
            model_name=data.model_name,
        )
        return R.success(data=result)
    except ValueError as e:
        return R.error(msg=str(e))
    except Exception as e:
        logger.error(f"Chat 问答失败: {e}", exc_info=True)
        return R.error(msg=f"问答失败: {str(e)}")


@router.post("/chat/free")
def ask_free_question(data: FreeAskRequest):
    """普通聊天，可选关联笔记 RAG 和 llm wiki 上下文。"""
    try:
        history = [{"role": m.role, "content": m.content} for m in data.history]
        result = free_chat_service(
            question=data.question,
            history=history,
            provider_id=data.provider_id,
            model_name=data.model_name,
            conversation_id=data.conversation_id,
            linked_task_id=data.linked_task_id,
            use_wiki=data.use_wiki,
            asset_content=data.asset_content,
        )
        return R.success(data=result)
    except ValueError as e:
        return R.error(msg=str(e))
    except Exception as e:
        logger.error(f"普通 Chat 问答失败: {e}", exc_info=True)
        return R.error(msg=f"问答失败: {str(e)}")


@router.post("/chat/free/stream")
def ask_free_question_stream(data: FreeAskRequest):
    """普通聊天流式返回。"""

    def event_generator():
        try:
            history = [{"role": m.role, "content": m.content} for m in data.history]
            for event in free_chat_stream_service(
                question=data.question,
                history=history,
                provider_id=data.provider_id,
                model_name=data.model_name,
                conversation_id=data.conversation_id,
                linked_task_id=data.linked_task_id,
                use_wiki=data.use_wiki,
                asset_content=data.asset_content,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"普通 Chat 流式问答失败: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'问答失败: {str(e)}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
