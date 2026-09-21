from __future__ import annotations

import concurrent.futures
import json

import pytest

from app.models.learning_canvas import LearningCanvas, LearningNode, ReviewItem
from app.services.learning_canvas_store import LearningCanvasStore


def make_canvas(summary: str = "初始摘要") -> LearningCanvas:
    return LearningCanvas(
        canvas_id="lc_test",
        conversation_id="conv_test",
        goal="掌握推测解码",
        nodes=[
            LearningNode(
                id="concept_speculative_decoding",
                label="推测解码",
                summary=summary,
            )
        ],
    )


def test_learning_canvas_defaults_do_not_claim_mastery() -> None:
    canvas = make_canvas()

    node = canvas.nodes[0]
    assert canvas.version == 2
    assert node.mastery == "unknown"
    assert node.mastery_evidence == []
    assert node.next_review_at is None


def test_store_loads_legacy_version_one_canvas(tmp_path) -> None:
    store = LearningCanvasStore(root=tmp_path)
    path = store.path_for("conv_test", "lc_test")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "canvas_id": "lc_test",
                "conversation_id": "conv_test",
                "goal": "旧学习目标",
                "nodes": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    restored = store.load("conv_test", "lc_test")

    assert restored.version == 1
    assert restored.document_task_id is None


def test_store_round_trip_preserves_learning_state(tmp_path) -> None:
    store = LearningCanvasStore(root=tmp_path)
    canvas = make_canvas()
    canvas.current_node_id = canvas.nodes[0].id
    canvas.review_queue.append(
        ReviewItem(node_id=canvas.nodes[0].id, next_review_at="2026-08-13T09:00:00Z")
    )

    store.save(canvas)
    restored = store.load("conv_test", "lc_test")

    assert restored.model_dump(mode="json") == canvas.model_dump(mode="json")


@pytest.mark.parametrize("bad_id", ["../escape", "/absolute", "a/b", "", "has space"])
def test_store_rejects_unsafe_identifiers(tmp_path, bad_id: str) -> None:
    store = LearningCanvasStore(root=tmp_path)

    with pytest.raises(ValueError):
        store.path_for(bad_id, "lc_test")
    with pytest.raises(ValueError):
        store.path_for("conv_test", bad_id)


def test_concurrent_saves_never_leave_invalid_json(tmp_path) -> None:
    store = LearningCanvasStore(root=tmp_path)

    def write(index: int) -> None:
        store.save(make_canvas(summary=f"摘要 {index}"))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(32)))

    path = store.path_for("conv_test", "lc_test")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["nodes"][0]["summary"].startswith("摘要 ")


def test_latest_returns_most_recent_canvas_for_conversation(tmp_path) -> None:
    store = LearningCanvasStore(root=tmp_path)
    older = make_canvas(summary="旧画布")
    store.save(older)
    newer = older.model_copy(deep=True)
    newer.canvas_id = "lc_newer"
    newer.nodes[0].summary = "新画布"
    store.save(newer)

    restored = store.latest("conv_test")

    assert restored.canvas_id == "lc_newer"
    assert restored.nodes[0].summary == "新画布"
