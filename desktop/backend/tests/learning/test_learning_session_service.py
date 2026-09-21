from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.learning_canvas import LearningCanvas, LearningNode
from app.services.learning_session_service import (
    LearningSessionService,
    LearningTransitionError,
)


def make_canvas() -> LearningCanvas:
    return LearningCanvas(
        canvas_id="lc_state",
        conversation_id="conv_state",
        goal="掌握知识图谱",
        nodes=[LearningNode(id="concept_graph", label="知识图谱", summary="实体与关系网络")],
    )


def passing_result(score: float = 0.8) -> dict:
    return {
        "rubric_version": "learning-rubric-v1",
        "score": score,
        "passed": True,
        "feedback": "回答满足要求",
        "answer_summary": "能够解释核心机制",
    }


def test_starting_unit_records_exposure_without_claiming_mastery() -> None:
    now = datetime(2026, 8, 11, 9, tzinfo=timezone.utc)
    service = LearningSessionService(now=lambda: now)
    canvas = make_canvas()

    unit = service.start_unit(canvas, "concept_graph")

    node = canvas.nodes[0]
    assert unit.stage == "explain"
    assert node.mastery == "exposed"
    assert [e.kind for e in node.mastery_evidence] == ["exposed"]
    assert node.next_review_at is None


def test_recall_without_application_cannot_become_provisional() -> None:
    now = datetime(2026, 8, 11, 9, tzinfo=timezone.utc)
    service = LearningSessionService(now=lambda: now)
    canvas = make_canvas()
    service.start_unit(canvas, "concept_graph")

    service.submit_evidence(
        canvas,
        "concept_graph",
        kind="recall",
        answer="知识图谱由实体和关系构成",
        rubric_result=passing_result(),
    )

    assert canvas.nodes[0].mastery == "learning"
    assert canvas.nodes[0].next_review_at is None


def test_recall_and_application_create_provisional_review() -> None:
    now = datetime(2026, 8, 11, 9, tzinfo=timezone.utc)
    service = LearningSessionService(now=lambda: now)
    canvas = make_canvas()
    service.start_unit(canvas, "concept_graph")
    service.submit_evidence(
        canvas,
        "concept_graph",
        kind="recall",
        answer="知识图谱由实体和关系构成",
        rubric_result=passing_result(),
    )

    service.submit_evidence(
        canvas,
        "concept_graph",
        kind="apply",
        answer="用实体表示论文，用关系表示引用",
        rubric_result=passing_result(),
    )

    node = canvas.nodes[0]
    assert node.mastery == "provisional"
    assert node.next_review_at == now + timedelta(hours=48)
    assert canvas.review_queue[0].node_id == node.id


def test_review_must_be_due_before_it_can_create_mastery() -> None:
    clock = {"now": datetime(2026, 8, 11, 9, tzinfo=timezone.utc)}
    service = LearningSessionService(now=lambda: clock["now"])
    canvas = make_canvas()
    service.start_unit(canvas, "concept_graph")
    for kind in ("recall", "apply"):
        service.submit_evidence(
            canvas,
            "concept_graph",
            kind=kind,
            answer="有效答案",
            rubric_result=passing_result(),
        )

    with pytest.raises(LearningTransitionError):
        service.submit_evidence(
            canvas,
            "concept_graph",
            kind="review",
            answer="过早复习",
            rubric_result=passing_result(),
        )

    clock["now"] = clock["now"] + timedelta(hours=49)
    service.submit_evidence(
        canvas,
        "concept_graph",
        kind="review",
        answer="延迟后仍能解释并应用",
        rubric_result=passing_result(),
    )

    assert canvas.nodes[0].mastery == "mastered"
    assert canvas.nodes[0].next_review_at is None
    assert canvas.review_queue == []


@pytest.mark.parametrize(
    ("answer", "rubric"),
    [
        ("", passing_result()),
        ("有效回答", {"score": 0.9, "passed": True}),
        ("有效回答", {**passing_result(), "score": 1.5}),
        ("有效回答", {**passing_result(score=0.5), "passed": True}),
    ],
)
def test_invalid_or_unsubstantiated_rubric_cannot_advance_mastery(
    answer: str, rubric: dict
) -> None:
    service = LearningSessionService()
    canvas = make_canvas()

    with pytest.raises(LearningTransitionError):
        service.submit_evidence(
            canvas,
            "concept_graph",
            kind="recall",
            answer=answer,
            rubric_result=rubric,
        )

    assert canvas.nodes[0].mastery == "unknown"
    assert canvas.nodes[0].mastery_evidence == []
