import pathlib
import sys
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

from app.routers import imported_notes  # noqa: E402


def test_note_library_returns_bounded_page_and_filters():
    app = FastAPI()
    app.include_router(imported_notes.router, prefix="/api")
    expected = {
        "items": [{"taskId": "task-1", "title": "Agent Runtime", "wikiStatus": "ready"}],
        "pagination": {"offset": 0, "limit": 20, "total": 1},
    }
    with patch.object(imported_notes, "list_note_library", return_value=expected) as list_notes:
        response = TestClient(app).get("/api/notes/library?q=Agent&limit=20&wiki_status=ready")

    assert response.status_code == 200
    assert response.json()["data"] == expected
    list_notes.assert_called_once_with(query="Agent", offset=0, limit=20, wiki_status="ready", status=None)


def test_note_library_rejects_unbounded_page_size():
    app = FastAPI()
    app.include_router(imported_notes.router, prefix="/api")
    response = TestClient(app).get("/api/notes/library?limit=0")
    assert response.status_code == 422
