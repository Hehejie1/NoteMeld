from __future__ import annotations

import uuid
import math
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.models.learning_canvas import (
    EvidenceKind,
    LearningAttempt,
    LearningCanvas,
    LearningNode,
    LearningSession,
    LearningUnit,
    MasteryEvidence,
    ReviewItem,
)


class LearningTransitionError(ValueError):
    pass


class LearningSessionService:
    def __init__(self, now: Callable[[], datetime] | None = None):
        self._now = now or (lambda: datetime.now(timezone.utc))

    def start_unit(self, canvas: LearningCanvas, node_id: str) -> LearningUnit:
        node = self._node(canvas, node_id)
        now = self._now()
        session = LearningSession(
            id=f"ls_{uuid.uuid4().hex}",
            node_id=node.id,
            stage="explain",
            started_at=now,
            updated_at=now,
        )
        canvas.sessions.append(session)
        canvas.current_node_id = node.id
        if node.mastery == "unknown":
            node.mastery = "exposed"
        node.mastery_evidence.append(
            MasteryEvidence(
                id=f"ev_{uuid.uuid4().hex}",
                kind="exposed",
                created_at=now,
                answer_summary="学习单元已展示",
            )
        )
        return LearningUnit(
            node_id=node.id,
            explanation=node.user_summary or node.summary or f"学习 {node.user_label or node.label}",
            recall_question=f"不看资料，请用自己的话解释“{node.user_label or node.label}”。",
            application_question=f"请给出一个需要应用“{node.user_label or node.label}”的新场景，并说明理由。",
        )

    def submit_evidence(
        self,
        canvas: LearningCanvas,
        node_id: str,
        *,
        kind: EvidenceKind,
        answer: str,
        rubric_result: dict,
        provider_id: str | None = None,
        model_name: str | None = None,
    ) -> MasteryEvidence:
        if kind == "exposed":
            raise LearningTransitionError("exposed 只能由 start_unit 记录")
        normalized_answer = str(answer or "").strip()
        if not normalized_answer:
            raise LearningTransitionError("学习证据必须包含学习者作答")
        rubric = self._validated_rubric(rubric_result)
        node = self._node(canvas, node_id)
        now = self._now()
        if kind == "review":
            if node.next_review_at is None or now < node.next_review_at:
                raise LearningTransitionError("复习尚未到期")

        evidence = MasteryEvidence(
            id=f"ev_{uuid.uuid4().hex}",
            kind=kind,
            created_at=now,
            answer_summary=rubric["answer_summary"],
            rubric_version=rubric["rubric_version"],
            score=rubric["score"],
            passed=rubric["passed"],
            feedback=rubric["feedback"],
            provider_id=provider_id,
            model_name=model_name,
        )
        node.mastery_evidence.append(evidence)
        session = self._current_session(canvas, node.id, now)
        session.attempts.append(
            LearningAttempt(
                kind=kind,
                answer=normalized_answer,
                created_at=now,
                evidence_id=evidence.id,
            )
        )
        session.stage = kind
        session.updated_at = now

        if kind == "review":
            self._apply_review(canvas, node, evidence, now)
        else:
            self._apply_immediate_evidence(canvas, node, now)
        return evidence

    @staticmethod
    def _validated_rubric(rubric_result: dict) -> dict:
        if not isinstance(rubric_result, dict):
            raise LearningTransitionError("评测结果格式无效")
        required_text = ("rubric_version", "answer_summary", "feedback")
        normalized = {
            key: str(rubric_result.get(key) or "").strip() for key in required_text
        }
        if any(not normalized[key] for key in required_text):
            raise LearningTransitionError("评测结果缺少 rubric、答案摘要或反馈")
        score_raw = rubric_result.get("score")
        if isinstance(score_raw, bool):
            raise LearningTransitionError("评测分数格式无效")
        try:
            score = float(score_raw)
        except (TypeError, ValueError) as exc:
            raise LearningTransitionError("评测分数格式无效") from exc
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise LearningTransitionError("评测分数必须在 0 到 1 之间")
        passed_raw = rubric_result.get("passed")
        if not isinstance(passed_raw, bool):
            raise LearningTransitionError("评测 passed 必须是布尔值")
        if passed_raw and score < 0.7:
            raise LearningTransitionError("通过评测的分数不能低于 0.7")
        return {
            **normalized,
            "score": score,
            "passed": passed_raw,
        }

    def _apply_immediate_evidence(
        self, canvas: LearningCanvas, node: LearningNode, now: datetime
    ) -> None:
        passed = {item.kind for item in node.mastery_evidence if item.passed}
        recall_ready = bool(passed.intersection({"recall", "explain"}))
        application_ready = bool(passed.intersection({"apply", "transfer"}))
        if recall_ready and application_ready:
            node.mastery = "provisional"
            node.next_review_at = now + timedelta(hours=48)
            self._upsert_review(canvas, node)
        else:
            node.mastery = "learning"

    def _apply_review(
        self,
        canvas: LearningCanvas,
        node: LearningNode,
        evidence: MasteryEvidence,
        now: datetime,
    ) -> None:
        if evidence.passed:
            node.mastery = "mastered"
            node.next_review_at = None
            canvas.review_queue = [item for item in canvas.review_queue if item.node_id != node.id]
            return
        node.mastery = "learning"
        node.next_review_at = now + timedelta(hours=24)
        self._upsert_review(canvas, node)

    @staticmethod
    def _node(canvas: LearningCanvas, node_id: str) -> LearningNode:
        for node in canvas.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    @staticmethod
    def _current_session(
        canvas: LearningCanvas, node_id: str, now: datetime
    ) -> LearningSession:
        for session in reversed(canvas.sessions):
            if session.node_id == node_id:
                return session
        session = LearningSession(
            id=f"ls_{uuid.uuid4().hex}",
            node_id=node_id,
            started_at=now,
            updated_at=now,
        )
        canvas.sessions.append(session)
        return session

    @staticmethod
    def _upsert_review(canvas: LearningCanvas, node: LearningNode) -> None:
        canvas.review_queue = [item for item in canvas.review_queue if item.node_id != node.id]
        if node.next_review_at is not None:
            canvas.review_queue.append(
                ReviewItem(node_id=node.id, next_review_at=node.next_review_at)
            )
