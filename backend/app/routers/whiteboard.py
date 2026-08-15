from __future__ import annotations

import logging
from typing import Callable, Literal
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.engine import SessionLocal
from app.models.whiteboard import SafeId, WhiteboardOperation
from app.services.conversation_context_refs import resolve_context_refs
from app.services.whiteboard_repository import (
    WhiteboardRepository,
    WhiteboardRevisionConflict,
)
from app.services.whiteboard_note_publish_service import WhiteboardNotePublishService
from app.services.whiteboard_seed_service import WhiteboardSeedService
from app.utils.response import ResponseWrapper as R


logger = logging.getLogger(__name__)
router = APIRouter()
repository = WhiteboardRepository(SessionLocal)
seed_service = WhiteboardSeedService(repository=repository)
publish_service = WhiteboardNotePublishService(repository=repository)


class _StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateWhiteboardPayload(_StrictPayload):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2_000)


class MutateWhiteboardPayload(_StrictPayload):
    base_revision: int = Field(ge=0)
    operations: list[WhiteboardOperation]


class PublishWhiteboardPayload(_StrictPayload):
    base_revision: int = Field(ge=1)
    scope: Literal["all", "selection"] = "all"
    card_ids: list[str] = Field(default_factory=list, max_length=20)
    relation_ids: list[str] = Field(default_factory=list, max_length=40)
    provider_id: str | None = Field(default=None, max_length=200)
    model_name: str | None = Field(default=None, max_length=500)


class WhiteboardContextPayload(_StrictPayload):
    revision: int = Field(ge=1)
    card_ids: list[SafeId] = Field(max_length=20)
    relation_ids: list[SafeId] = Field(max_length=40)
    label: str = Field(min_length=1, max_length=200)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("label must not be blank")
        return normalized


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
    "/conversations/{conversation_id}/whiteboards/{whiteboard_id}/context"
)
def create_whiteboard_context(
    conversation_id: str,
    whiteboard_id: str,
    data: WhiteboardContextPayload,
):
    def resolve():
        current = repository.get(conversation_id, whiteboard_id)
        if current.revision != data.revision:
            raise ValueError("stale whiteboard revision")
        resolved = resolve_context_refs(
            conversation_id,
            [
                {
                    "id": f"whiteboard-selection-{uuid4().hex}",
                    "type": "whiteboard_selection",
                    "whiteboard_id": whiteboard_id,
                    "revision": data.revision,
                    "card_ids": data.card_ids,
                    "relation_ids": data.relation_ids,
                    "label": data.label,
                }
            ],
            repository,
        )
        if len(resolved) != 1:
            raise ValueError("invalid whiteboard selection")
        return resolved[0]

    return _wrapped(resolve)


@router.post(
    "/conversations/{conversation_id}/whiteboards/{whiteboard_id}/publish-note"
)
def publish_whiteboard_note(
    conversation_id: str,
    whiteboard_id: str,
    data: PublishWhiteboardPayload,
):
    return _wrapped(
        lambda: publish_service.publish(
            conversation_id,
            whiteboard_id,
            data.base_revision,
            data.scope,
            data.card_ids,
            data.relation_ids,
            data.provider_id,
            data.model_name,
        )
    )


@router.post(
    "/conversations/{conversation_id}/whiteboards/from-learning-canvas/{canvas_id}"
)
def seed_from_learning_canvas(conversation_id: str, canvas_id: str):
    return _wrapped(
        lambda: seed_service.ensure_from_learning_canvas(conversation_id, canvas_id),
        not_found_msg="学习空间不存在",
    )
