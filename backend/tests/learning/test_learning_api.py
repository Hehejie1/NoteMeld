from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.learning_canvas import LearningCanvas, LearningNode
from app.routers import learning
from app.services.learning_canvas_service import LearningCanvasService
from app.services.learning_canvas_store import LearningCanvasStore
from app.services.research_search import ResearchSearchBundle
from app.services.research_search_config import ResearchSearchConfigManager


class _NoExternal:
    def search(self, query: str, scopes: list[str], limit: int):
        return ResearchSearchBundle()


def _local(_goal: str):
    return [
        {
            "id": "wiki-concept-agent",
            "type": "wiki_concept",
            "title": "Agent",
            "text": "能调用工具的智能体",
            "score": 9,
            "metadata": {"source_id": "task-agent"},
        }
    ]


def make_client(tmp_path, monkeypatch) -> TestClient:
    store = LearningCanvasStore(root=tmp_path / "workspaces")
    service = LearningCanvasService(
        store=store,
        local_search=_local,
        research_search=_NoExternal(),
        message_writer=lambda *_args: None,
        note_importer=type(
            "NoteImporter",
            (),
            {"import_note": lambda self, request, conversation_id=None: type("Result", (), {"note_id": "note_api", "wiki_status": "pending"})()},
        )(),
    )
    monkeypatch.setattr(learning, "canvas_store", store)
    monkeypatch.setattr(learning, "canvas_service", service)
    monkeypatch.setattr(
        learning,
        "search_config_manager",
        ResearchSearchConfigManager(path=tmp_path / "research_search.json"),
    )
    app = FastAPI()
    app.include_router(learning.router, prefix="/api")
    return TestClient(app)


def test_create_and_reload_canvas_uses_response_wrapper(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)

    created = client.post(
        "/api/conversations/conv_api/learning-canvases",
        json={"goal": "学习 Agent", "external_scopes": []},
    )

    assert created.status_code == 200
    payload = created.json()
    assert payload["code"] == 0
    canvas_id = payload["data"]["canvas_id"]

    restored = client.get(
        f"/api/conversations/conv_api/learning-canvases/{canvas_id}"
    )
    assert restored.json()["data"]["goal"] == "学习 Agent"
    assert restored.json()["data"]["nodes"][0]["mastery"] == "unknown"


def test_create_canvas_can_omit_external_scopes(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)

    created = client.post(
        "/api/conversations/conv_default_scopes/learning-canvases",
        json={"goal": "学习 Agent"},
    )

    assert created.status_code == 200
    assert created.json()["code"] == 0
    assert created.json()["data"]["goal"] == "学习 Agent"


def test_create_canvas_accepts_bounded_context_references(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/conversations/conv_context/learning-canvases",
        json={
            "goal": "继续研究失败边界",
            "context_refs": [
                {
                    "id": "ref-1",
                    "type": "whiteboard_node",
                    "document_task_id": "note-1",
                    "label": "Agent 循环",
                    "snapshot": "规划、工具调用和反馈",
                }
            ],
        },
    )

    assert created.status_code == 200
    assert created.json()["code"] == 0


def test_start_and_submit_evidence_persist_transitions(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/conversations/conv_api/learning-canvases",
        json={"goal": "学习 Agent", "external_scopes": []},
    ).json()["data"]
    canvas_id = created["canvas_id"]
    node_id = created["nodes"][0]["id"]

    started = client.post(
        f"/api/conversations/conv_api/learning-canvases/{canvas_id}/units/{node_id}/start"
    )
    assert started.json()["data"]["canvas"]["nodes"][0]["mastery"] == "exposed"

    for kind in ("recall", "apply"):
        response = client.post(
            f"/api/conversations/conv_api/learning-canvases/{canvas_id}/units/{node_id}/evidence",
            json={
                "kind": kind,
                "answer": "有效回答",
                "rubric_result": {
                    "rubric_version": "learning-rubric-v1",
                    "score": 0.8,
                    "passed": True,
                    "feedback": "通过",
                    "answer_summary": "理解正确",
                },
            },
        )
        assert response.status_code == 200

    restored = client.get(
        f"/api/conversations/conv_api/learning-canvases/{canvas_id}"
    ).json()["data"]
    assert restored["nodes"][0]["mastery"] == "provisional"
    assert len(restored["review_queue"]) == 1


def test_config_endpoint_never_returns_secret(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)

    updated = client.put(
        "/api/research-search/config",
        json={"github_token": "gh-private", "enabled_scopes": ["github"]},
    )

    assert updated.status_code == 200
    rendered = updated.text
    assert "gh-private" not in rendered
    assert updated.json()["data"]["github_token_set"] is True


def test_missing_canvas_returns_wrapped_404(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)

    response = client.get(
        "/api/conversations/conv_api/learning-canvases/lc_missing"
    )

    assert response.json()["code"] == 404
    assert "不存在" in response.json()["msg"]


def test_patch_canvas_persists_user_label_and_summary(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    canvas = client.post(
        "/api/conversations/conv_api/learning-canvases",
        json={"goal": "学习 Agent", "external_scopes": []},
    ).json()["data"]
    node_id = canvas["nodes"][0]["id"]

    updated = client.patch(
        f"/api/conversations/conv_api/learning-canvases/{canvas['canvas_id']}",
        json={
            "node_id": node_id,
            "user_label": "智能体基础",
            "user_summary": "能感知环境并调用工具完成目标。",
        },
    )

    assert updated.json()["code"] == 0
    node = updated.json()["data"]["nodes"][0]
    assert node["user_label"] == "智能体基础"
    assert node["user_summary"] == "能感知环境并调用工具完成目标。"


def test_parallel_evidence_submissions_do_not_overwrite_each_other(
    tmp_path, monkeypatch
) -> None:
    class RacingStore(LearningCanvasStore):
        def __init__(self, root):
            super().__init__(root=root)
            self.load_barrier = threading.Barrier(2)
            self.race_enabled = False

        def load(self, conversation_id: str, canvas_id: str):
            canvas = super().load(conversation_id, canvas_id)
            if self.race_enabled:
                self.load_barrier.wait(timeout=2)
            return canvas

    store = RacingStore(root=tmp_path / "workspaces")
    service = LearningCanvasService(
        store=store,
        local_search=_local,
        research_search=_NoExternal(),
        message_writer=lambda *_args: None,
        note_importer=type(
            "NoteImporter",
            (),
            {"import_note": lambda self, request, conversation_id=None: type("Result", (), {"note_id": "note_race", "wiki_status": "pending"})()},
        )(),
    )
    monkeypatch.setattr(learning, "canvas_store", store)
    monkeypatch.setattr(learning, "canvas_service", service)
    canvas = service.create_canvas(
        "conv_race", goal="学习 Agent", external_scopes=[]
    )
    node_id = canvas.nodes[0].id
    learning.start_learning_unit("conv_race", canvas.canvas_id, node_id)
    store.race_enabled = True

    def submit(kind: str):
        return learning.submit_learning_evidence(
            "conv_race",
            canvas.canvas_id,
            node_id,
            learning.EvidencePayload(
                kind=kind,
                answer="有效回答",
                rubric_result={
                    "rubric_version": "learning-rubric-v1",
                    "score": 0.8,
                    "passed": True,
                    "feedback": "通过",
                    "answer_summary": "理解正确",
                },
            ),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, ["recall", "apply"]))

    assert all(json.loads(item.body)["code"] == 0 for item in responses)
    restored = LearningCanvasStore.load(store, "conv_race", canvas.canvas_id)
    assert len(restored.nodes[0].mastery_evidence) == 3
    assert len(restored.sessions[0].attempts) == 2
    assert restored.nodes[0].mastery == "provisional"
