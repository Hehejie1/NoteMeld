from __future__ import annotations

import json
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time

import pytest

from app.services.note_import_service import ImportNoteRequest, NoteImportService
from app.models.summary_input import SummaryInput


class MemoryDocuments:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.fail_after_write = False

    def write(self, payload: dict) -> dict:
        self.rows[payload["task_id"]] = deepcopy(payload)
        if self.fail_after_write:
            raise RuntimeError("document commit failed")
        return deepcopy(payload)

    def read(self, task_id: str) -> dict | None:
        value = self.rows.get(task_id)
        return deepcopy(value) if value is not None else None

    def compensate(self, task_id: str, previous: dict | None) -> None:
        if previous is None:
            self.rows.pop(task_id, None)
        else:
            self.rows[task_id] = deepcopy(previous)


class VectorStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def index_task(self, task_id: str) -> None:
        self.calls.append(task_id)
        if self.fail:
            raise RuntimeError("vector unavailable")


def request(content: str = "# Draft\n\nInitial") -> ImportNoteRequest:
    return ImportNoteRequest(
        title="Research draft",
        content=content,
        source_type="whiteboard",
        metadata={"whiteboard_id": "wb_1", "revision": 1},
    )


def service(tmp_path: Path, documents: MemoryDocuments, *, vector=None, wiki=None):
    vector = vector or VectorStore()
    wiki = wiki or (lambda **_kwargs: None)
    return NoteImportService(
        output_dir=tmp_path,
        document_writer=documents.write,
        document_by_id_reader=documents.read,
        document_compensator=documents.compensate,
        vector_store_factory=lambda: vector,
        wiki_scheduler=wiki,
    )


def test_import_note_delegates_to_publish_revision_with_new_id(tmp_path, monkeypatch):
    documents = MemoryDocuments()
    importer = service(tmp_path, documents)
    calls = []

    def publish_revision(req, conversation_id, note_id=None, **kwargs):
        calls.append((req, conversation_id, note_id, kwargs))
        return "delegated"

    monkeypatch.setattr(importer, "publish_revision", publish_revision)

    assert importer.import_note(request(), conversation_id="conv_1") == "delegated"
    assert calls == [(request(), "conv_1", None, {})]


def test_publish_revision_updates_same_note_with_atomic_unique_temp_file(tmp_path):
    documents = MemoryDocuments()
    importer = service(tmp_path, documents)

    first = importer.publish_revision(request(), "conv_1")
    second = importer.publish_revision(
        request("# Draft\n\nUpdated"),
        "conv_1",
        note_id=first.note_id,
    )

    assert second.note_id == first.note_id
    assert documents.rows[first.note_id]["content"] == "# Draft\n\nUpdated"
    payload = json.loads((tmp_path / f"{first.note_id}.json").read_text("utf-8"))
    assert payload["markdown"] == "# Draft\n\nUpdated"
    assert not (tmp_path / f"{first.note_id}.tmp").exists()
    assert not list(tmp_path.glob(f".{first.note_id}.*.tmp"))


def test_publish_revision_persists_retry_resolvable_summary_input_sidecar(tmp_path):
    documents = MemoryDocuments()
    importer = service(tmp_path, documents)
    publish_request = request().model_copy(
        update={
            "metadata": {
                "whiteboard_id": "wb_1",
                "revision": 1,
                "provider_id": "provider_saved",
                "model_name": "model_saved",
            }
        }
    )

    result = importer.publish_revision(publish_request, "conv_1")

    sidecar_path = tmp_path / f"{result.note_id}_summary_input.json"
    summary_input = SummaryInput(**json.loads(sidecar_path.read_text("utf-8")))
    # Equivalent to routers.note.retry_wiki_extraction's resolver contract.
    assert summary_input.user_options["provider_id"] == "provider_saved"
    assert summary_input.user_options["model_name"] == "model_saved"


def test_document_failure_restores_previous_file_and_document(tmp_path):
    documents = MemoryDocuments()
    importer = service(tmp_path, documents)
    first = importer.publish_revision(request(), "conv_1")
    note_path = tmp_path / f"{first.note_id}.json"
    previous_bytes = note_path.read_bytes()
    sidecar_path = tmp_path / f"{first.note_id}_summary_input.json"
    previous_sidecar = sidecar_path.read_bytes()
    previous_document = documents.read(first.note_id)
    documents.fail_after_write = True

    with pytest.raises(RuntimeError, match="document commit failed"):
        importer.publish_revision(
            request("# Draft\n\nMust roll back"),
            "conv_1",
            note_id=first.note_id,
        )

    assert note_path.read_bytes() == previous_bytes
    assert sidecar_path.read_bytes() == previous_sidecar
    assert documents.read(first.note_id) == previous_document


def test_file_replace_failure_does_not_change_document_or_previous_result(
    tmp_path, monkeypatch
):
    documents = MemoryDocuments()
    importer = service(tmp_path, documents)
    first = importer.publish_revision(request(), "conv_1")
    note_path = tmp_path / f"{first.note_id}.json"
    previous_bytes = note_path.read_bytes()
    previous_document = documents.read(first.note_id)
    original_replace = Path.replace

    def fail_revision_replace(path: Path, target: Path):
        if Path(target) == note_path and Path(path) != note_path:
            raise OSError("replace failed")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_revision_replace)

    with pytest.raises(OSError, match="replace failed"):
        importer.publish_revision(
            request("# Draft\n\nNot durable"),
            "conv_1",
            note_id=first.note_id,
        )

    assert note_path.read_bytes() == previous_bytes
    assert documents.read(first.note_id) == previous_document
    assert not list(tmp_path.glob(f".{first.note_id}.*.tmp"))


def test_summary_sidecar_replace_failure_restores_previous_note_artifacts(
    tmp_path, monkeypatch
):
    documents = MemoryDocuments()
    importer = service(tmp_path, documents)
    first = importer.publish_revision(request(), "conv_1")
    note_path = tmp_path / f"{first.note_id}.json"
    sidecar_path = tmp_path / f"{first.note_id}_summary_input.json"
    previous_note = note_path.read_bytes()
    previous_sidecar = sidecar_path.read_bytes()
    previous_document = documents.read(first.note_id)
    original_replace = Path.replace

    def fail_sidecar_replace(path: Path, target: Path):
        if Path(target) == sidecar_path and Path(path) != sidecar_path:
            raise OSError("sidecar replace failed")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_sidecar_replace)

    with pytest.raises(OSError, match="sidecar replace failed"):
        importer.publish_revision(
            request("# Draft\n\nNot durable"),
            "conv_1",
            note_id=first.note_id,
        )

    assert note_path.read_bytes() == previous_note
    assert sidecar_path.read_bytes() == previous_sidecar
    assert documents.read(first.note_id) == previous_document


def test_commit_hook_failure_compensates_new_note_before_postprocessing(tmp_path):
    documents = MemoryDocuments()
    vector = VectorStore()
    wiki_calls = []
    importer = service(
        tmp_path,
        documents,
        vector=vector,
        wiki=lambda **kwargs: wiki_calls.append(kwargs),
    )

    with pytest.raises(RuntimeError, match="link commit failed"):
        importer.publish_revision(
            request(),
            "conv_1",
            commit_hook=lambda _note_id: (_ for _ in ()).throw(
                RuntimeError("link commit failed")
            ),
        )

    assert documents.rows == {}
    assert list(tmp_path.glob("note_*.json")) == []
    assert list(tmp_path.glob("note_*_summary_input.json")) == []
    assert vector.calls == []
    assert wiki_calls == []


def test_publish_revision_serializes_same_note_across_service_instances(tmp_path):
    class TrackingDocuments(MemoryDocuments):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()

        def write(self, payload: dict) -> dict:
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                time.sleep(0.05)
                return super().write(payload)
            finally:
                with self.lock:
                    self.active -= 1

    documents = TrackingDocuments()
    first_importer = service(tmp_path, documents)
    second_importer = service(tmp_path, documents)
    initial = first_importer.publish_revision(request(), "conv_1")
    documents.max_active = 0

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda item: item[0].publish_revision(
                    request(f"# Draft\n\nVersion {item[1]}"),
                    "conv_1",
                    note_id=initial.note_id,
                ),
                [(first_importer, "A"), (second_importer, "B")],
            )
        )

    assert documents.max_active == 1
    assert {result.note_id for result in results} == {initial.note_id}
    result_markdown = json.loads(
        (tmp_path / f"{initial.note_id}.json").read_text("utf-8")
    )["markdown"]
    assert documents.rows[initial.note_id]["content"] == result_markdown


@pytest.mark.parametrize(
    ("vector_fails", "wiki_fails", "expected_diagnostic", "expected_wiki"),
    [
        (True, False, "vector_index_failed", "pending"),
        (False, True, "wiki_schedule_failed", "partial"),
    ],
)
def test_postprocessing_failure_is_partial_but_note_remains_durable(
    tmp_path,
    vector_fails,
    wiki_fails,
    expected_diagnostic,
    expected_wiki,
):
    documents = MemoryDocuments()
    vector = VectorStore(fail=vector_fails)

    def wiki(**_kwargs):
        if wiki_fails:
            raise RuntimeError("wiki unavailable")

    importer = service(tmp_path, documents, vector=vector, wiki=wiki)

    result = importer.publish_revision(request(), "conv_1")

    assert result.status == "partial"
    assert expected_diagnostic in result.diagnostics
    assert result.wiki_status == expected_wiki
    expected_kind = "vector_reindex" if vector_fails else "wiki_retry"
    assert result.retry_actions == [
        {
            "kind": expected_kind,
            "endpoint": (
                "/api/migration/reindex"
                if vector_fails
                else f"/api/wiki/retry/{result.note_id}"
            ),
            "task_id": result.note_id,
        }
    ]
    assert result.note_id in documents.rows
    assert (tmp_path / f"{result.note_id}.json").is_file()
