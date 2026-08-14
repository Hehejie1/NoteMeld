from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.learning_canvas_service import (
    LearningCanvasEmptyError,
    LearningCanvasService,
)
from app.services.learning_canvas_store import LearningCanvasStore
from app.services.conversation_store import append_message
from app.services.learning_session_service import (
    LearningSessionService,
    LearningTransitionError,
)
from app.services.research_search_config import ResearchSearchConfigManager
from app.utils.response import ResponseWrapper as R


router = APIRouter()
canvas_store = LearningCanvasStore()
canvas_service = LearningCanvasService(store=canvas_store, message_writer=append_message)
session_service = LearningSessionService()
search_config_manager = ResearchSearchConfigManager()


class ResearchSearchConfigPayload(BaseModel):
    enabled_scopes: list[Literal["web", "academic", "github"]] | None = None
    web_provider: Literal["disabled", "searxng", "tavily"] | None = None
    searxng_endpoint: str | None = None
    tavily_api_key: str | None = None
    github_token: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=30)
    clear_tavily_api_key: bool = False
    clear_github_token: bool = False


class CreateCanvasPayload(BaseModel):
    goal: str
    external_scopes: list[Literal["web", "academic", "github"]] | None = None
    external_limit: int = Field(default=5, ge=1, le=20)
    research_space_id: str | None = None
    provider_id: str | None = None
    model_name: str | None = None
    context_refs: list[dict[str, Any]] = Field(default_factory=list)


class UpdateCanvasPayload(BaseModel):
    node_id: str
    user_label: str | None = None
    user_summary: str | None = None


class EvidencePayload(BaseModel):
    kind: Literal["recall", "explain", "apply", "transfer", "review"]
    answer: str
    rubric_result: dict[str, Any]
    provider_id: str | None = None
    model_name: str | None = None


@router.get("/research-search/config")
def get_research_search_config():
    return R.success(search_config_manager.get_public_config())


@router.put("/research-search/config")
def put_research_search_config(data: ResearchSearchConfigPayload):
    return R.success(search_config_manager.update_config(data.model_dump(exclude_unset=True)))


@router.post("/conversations/{conversation_id}/learning-canvases")
def create_learning_canvas(conversation_id: str, data: CreateCanvasPayload):
    try:
        canvas = canvas_service.create_canvas(
            conversation_id,
            goal=data.goal,
            external_scopes=data.external_scopes,
            external_limit=data.external_limit,
            research_space_id=data.research_space_id,
            provider_id=data.provider_id,
            model_name=data.model_name,
            context_refs=data.context_refs,
        )
        return R.success(canvas.model_dump(mode="json"))
    except LearningCanvasEmptyError as exc:
        return R.error(str(exc), code=503)
    except ValueError as exc:
        return R.error(str(exc), code=400)


@router.get("/conversations/{conversation_id}/learning-canvases/{canvas_id}")
def get_learning_canvas(conversation_id: str, canvas_id: str):
    try:
        canvas = canvas_store.load(conversation_id, canvas_id)
        return R.success(canvas.model_dump(mode="json"))
    except FileNotFoundError:
        return R.error("学习空间不存在", code=404)
    except ValueError as exc:
        return R.error(str(exc), code=403)


@router.patch("/conversations/{conversation_id}/learning-canvases/{canvas_id}")
def patch_learning_canvas(
    conversation_id: str,
    canvas_id: str,
    data: UpdateCanvasPayload,
):
    try:
        def mutate(canvas):
            node = next((item for item in canvas.nodes if item.id == data.node_id), None)
            if node is None:
                raise KeyError(data.node_id)
            fields = data.model_fields_set
            if "user_label" in fields:
                node.user_label = str(data.user_label or "").strip() or None
            if "user_summary" in fields:
                node.user_summary = str(data.user_summary or "").strip() or None
            canvas.updated_at = datetime.now(timezone.utc)

        canvas, _ = canvas_store.update(conversation_id, canvas_id, mutate)
        return R.success(canvas.model_dump(mode="json"))
    except FileNotFoundError:
        return R.error("学习空间不存在", code=404)
    except KeyError:
        return R.error("学习节点不存在", code=404)
    except ValueError as exc:
        return R.error(str(exc), code=403)


@router.post(
    "/conversations/{conversation_id}/learning-canvases/{canvas_id}/units/{node_id}/start"
)
def start_learning_unit(conversation_id: str, canvas_id: str, node_id: str):
    try:
        canvas, unit = canvas_store.update(
            conversation_id,
            canvas_id,
            lambda current: session_service.start_unit(current, node_id),
        )
        return R.success(
            {
                "unit": unit.model_dump(mode="json"),
                "canvas": canvas.model_dump(mode="json"),
            }
        )
    except FileNotFoundError:
        return R.error("学习空间不存在", code=404)
    except KeyError:
        return R.error("学习节点不存在", code=404)
    except ValueError as exc:
        return R.error(str(exc), code=400)


@router.post(
    "/conversations/{conversation_id}/learning-canvases/{canvas_id}/units/{node_id}/evidence"
)
def submit_learning_evidence(
    conversation_id: str,
    canvas_id: str,
    node_id: str,
    data: EvidencePayload,
):
    try:
        canvas, evidence = canvas_store.update(
            conversation_id,
            canvas_id,
            lambda current: session_service.submit_evidence(
                current,
                node_id,
                kind=data.kind,
                answer=data.answer,
                rubric_result=data.rubric_result,
                provider_id=data.provider_id,
                model_name=data.model_name,
            ),
        )
        return R.success(
            {
                "evidence": evidence.model_dump(mode="json"),
                "canvas": canvas.model_dump(mode="json"),
            }
        )
    except FileNotFoundError:
        return R.error("学习空间不存在", code=404)
    except KeyError:
        return R.error("学习节点不存在", code=404)
    except LearningTransitionError as exc:
        return R.error(str(exc), code=409)
    except ValueError as exc:
        return R.error(str(exc), code=400)


@router.get(
    "/conversations/{conversation_id}/learning-canvases/{canvas_id}/reviews/due"
)
def get_due_reviews(conversation_id: str, canvas_id: str):
    try:
        canvas = canvas_store.load(conversation_id, canvas_id)
        now = session_service._now()
        due = [
            item.model_dump(mode="json")
            for item in canvas.review_queue
            if item.next_review_at <= now
        ]
        return R.success(due)
    except FileNotFoundError:
        return R.error("学习空间不存在", code=404)
    except ValueError as exc:
        return R.error(str(exc), code=403)
