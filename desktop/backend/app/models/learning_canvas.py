from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


MasteryStatus = Literal["unknown", "exposed", "learning", "provisional", "mastered"]
EvidenceKind = Literal["exposed", "recall", "explain", "apply", "transfer", "review"]
SourceType = Literal["local_wiki", "local_note", "web", "academic", "github"]


class LearningSource(BaseModel):
    id: str
    source_type: SourceType
    provider: str
    title: str
    url: Optional[str] = None
    snippet: str = ""
    published_at: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    repository: Optional[str] = None
    default_branch: Optional[str] = None
    stars: Optional[int] = None
    license: Optional[str] = None
    version: Optional[str] = None
    local_task_id: Optional[str] = None
    compile_status: str = "candidate"


class MasteryEvidence(BaseModel):
    id: str
    kind: EvidenceKind
    created_at: datetime
    answer_summary: str = ""
    rubric_version: str = "learning-rubric-v1"
    score: float = 0.0
    passed: bool = False
    feedback: str = ""
    model_name: Optional[str] = None
    provider_id: Optional[str] = None


class LearningNode(BaseModel):
    id: str
    label: str
    type: str = "concept"
    summary: str = ""
    priority: Literal["low", "medium", "high"] = "medium"
    mastery: MasteryStatus = "unknown"
    status: str = "ready"
    prerequisites: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    mastery_evidence: list[MasteryEvidence] = Field(default_factory=list)
    next_review_at: Optional[datetime] = None
    user_label: Optional[str] = None
    user_summary: Optional[str] = None


class LearningEdge(BaseModel):
    source: str
    target: str
    type: str = "prerequisite"
    weight: float = 1.0


class LearningPathStep(BaseModel):
    step: int
    node_ids: list[str]
    label: str
    difficulty: str = "introductory"
    minutes_estimate: int = 10
    depends_on: list[int] = Field(default_factory=list)


class LearningAttempt(BaseModel):
    kind: EvidenceKind
    answer: str
    created_at: datetime
    evidence_id: str


class LearningSession(BaseModel):
    id: str
    node_id: str
    stage: str = "explain"
    attempts: list[LearningAttempt] = Field(default_factory=list)
    started_at: datetime
    updated_at: datetime


class LearningUnit(BaseModel):
    node_id: str
    stage: str = "explain"
    explanation: str
    recall_question: str
    application_question: str


class ReviewItem(BaseModel):
    node_id: str
    next_review_at: datetime


class LearningCanvas(BaseModel):
    version: int = 2
    canvas_id: str
    conversation_id: str
    research_space_id: Optional[str] = None
    goal: str
    status: str = "active"
    diagnostic_status: str = "pending"
    nodes: list[LearningNode] = Field(default_factory=list)
    edges: list[LearningEdge] = Field(default_factory=list)
    clusters: list[dict[str, Any]] = Field(default_factory=list)
    path: list[LearningPathStep] = Field(default_factory=list)
    sources: list[LearningSource] = Field(default_factory=list)
    sessions: list[LearningSession] = Field(default_factory=list)
    review_queue: list[ReviewItem] = Field(default_factory=list)
    external_errors: list[dict[str, Any]] = Field(default_factory=list)
    current_node_id: Optional[str] = None
    document_task_id: Optional[str] = None
    whiteboard_id: Optional[str] = None
    overview: str = ""
    clarification: Optional[dict[str, Any]] = None
    suggested_actions: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
