from __future__ import annotations

import logging
from typing import Callable

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.db.engine import SessionLocal
from app.models.whiteboard import WhiteboardOperation
from app.services.whiteboard_repository import (
    WhiteboardRepository,
    WhiteboardRevisionConflict,
)
from app.services.whiteboard_seed_service import WhiteboardSeedService
from app.utils.response import ResponseWrapper as R


logger = logging.getLogger(__name__)
router = APIRouter()
repository = WhiteboardRepository(SessionLocal)
seed_service = WhiteboardSeedService(repository=repository)


class _StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateWhiteboardPayload(_StrictPayload):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2_000)


class MutateWhiteboardPayload(_StrictPayload):
    base_revision: int = Field(ge=0)
    operations: list[WhiteboardOperation]


def _wrapped(action: Callable[[], object], *, not_found_msg: str = "白板不存在"):
    try:
        result = action()
        if hasattr(result, "model_dump"):
            result = result.model_dump(mode="json")
        elif isinstance(result, list):
            result = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in result
            ]
        return R.success(result)
    except WhiteboardRevisionConflict as exc:
        return R.error(
            "白板已在其他窗口更新",
            code=409,
            data={"current_revision": exc.current_revision},
        )
    except PermissionError:
        return R.error("无权访问该白板", code=403)
    except (LookupError, FileNotFoundError):
        return R.error(not_found_msg, code=404)
    except ValueError:
        return R.error("白板操作无效", code=400)
    except Exception:
        logger.error("whiteboard request failed")
        return R.error("白板服务暂时不可用", code=500)


@router.post("/conversations/{conversation_id}/whiteboards")
def create_whiteboard(conversation_id: str, data: CreateWhiteboardPayload):
    return _wrapped(
        lambda: repository.create(
            conversation_id,
            data.title,
            data.description,
        )
    )


@router.get("/conversations/{conversation_id}/whiteboards")
def list_whiteboards(conversation_id: str):
    return _wrapped(lambda: repository.list_for_conversation(conversation_id))


@router.get("/conversations/{conversation_id}/whiteboards/{whiteboard_id}")
def get_whiteboard(conversation_id: str, whiteboard_id: str):
    return _wrapped(lambda: repository.get(conversation_id, whiteboard_id))


@router.delete("/conversations/{conversation_id}/whiteboards/{whiteboard_id}")
def delete_whiteboard(conversation_id: str, whiteboard_id: str):
    def delete():
        repository.soft_delete(conversation_id, whiteboard_id)
        return {"deleted": True}

    return _wrapped(delete)


@router.post(
    "/conversations/{conversation_id}/whiteboards/{whiteboard_id}/mutations"
)
def mutate_whiteboard(
    conversation_id: str,
    whiteboard_id: str,
    data: MutateWhiteboardPayload,
):
    def mutate():
        current = repository.get(conversation_id, whiteboard_id)
        if current.revision != data.base_revision:
            raise WhiteboardRevisionConflict(current.revision)
        return repository.apply_mutations(
            conversation_id,
            whiteboard_id,
            data.base_revision,
            data.operations,
        )

    return _wrapped(mutate)


@router.post(
    "/conversations/{conversation_id}/whiteboards/from-learning-canvas/{canvas_id}"
)
def seed_from_learning_canvas(conversation_id: str, canvas_id: str):
    return _wrapped(
        lambda: seed_service.ensure_from_learning_canvas(conversation_id, canvas_id),
        not_found_msg="学习空间不存在",
    )
