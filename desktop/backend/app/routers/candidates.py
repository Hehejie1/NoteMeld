from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.security.session_token import require_session_token
from app.services.candidates import CandidateNotApprovable, CandidateNotFound, CandidateService, CandidateValidationError
from app.services.plugins.response import PluginResponse as R


router = APIRouter(prefix="/candidates", dependencies=[Depends(require_session_token)])
service = CandidateService()


class CandidatePayload(BaseModel):
    kind: str
    title: str
    scope: dict = Field(default_factory=dict)
    evidence: list = Field(default_factory=list)
    trace: list = Field(default_factory=list)
    artifact: dict = Field(default_factory=dict)
    patch: dict = Field(default_factory=dict)
    tests: list = Field(default_factory=list)
    risks: list = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    rollback: dict = Field(default_factory=dict)
    model_safety_claim: str | None = None


class DecisionPayload(BaseModel):
    approved: bool
    reason: str | None = None


@router.get("")
def list_candidates():
    return R.success({"candidates": service.list()})


@router.post("")
def create_candidate(payload: CandidatePayload):
    try:
        return R.success(service.create(payload.model_dump()))
    except CandidateValidationError as exc:
        return R.error(str(exc), code=400)


@router.get("/{candidate_id}")
def get_candidate(candidate_id: str):
    try:
        return R.success(service.get(candidate_id))
    except CandidateNotFound:
        return R.error("candidate not found", code=404)


@router.post("/{candidate_id}/validate")
def validate_candidate(candidate_id: str):
    try:
        return R.success(service.validate(candidate_id))
    except CandidateNotFound:
        return R.error("candidate not found", code=404)


@router.post("/{candidate_id}/decision")
def decide_candidate(candidate_id: str, payload: DecisionPayload):
    try:
        return R.success(service.decide(candidate_id, approved=payload.approved, actor="desktop-user", reason=payload.reason))
    except CandidateNotFound:
        return R.error("candidate not found", code=404)
    except CandidateNotApprovable as exc:
        return R.error(str(exc), code=409)


@router.post("/{candidate_id}/approve")
def approve_candidate(candidate_id: str, payload: DecisionPayload | None = None):
    try:
        return R.success(service.decide(candidate_id, approved=True, actor="desktop-user", reason=payload.reason if payload else None))
    except CandidateNotFound:
        return R.error("candidate not found", code=404)
    except CandidateNotApprovable as exc:
        return R.error(str(exc), code=409)


@router.post("/{candidate_id}/decline")
def decline_candidate(candidate_id: str, payload: DecisionPayload | None = None):
    try:
        return R.success(service.decide(candidate_id, approved=False, actor="desktop-user", reason=payload.reason if payload else None))
    except CandidateNotFound:
        return R.error("candidate not found", code=404)
