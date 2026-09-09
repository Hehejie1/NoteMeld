from __future__ import annotations

import pytest

from app.agent_host.note_contract import NoteAuthority, SdkNoteDto, note_id_from_task_id


def test_task_id_is_the_opaque_first_release_note_id():
    assert note_id_from_task_id(" task-123 ") == "task-123"
    dto = SdkNoteDto.from_note_document({"task_id": "task-123", "content": "# Note"})
    assert dto.note_id == "task-123"
    assert dto.content == "# Note"


def test_note_id_rejects_missing_task_id():
    with pytest.raises(ValueError, match="task_id"):
        note_id_from_task_id("")


def test_note_authority_separates_document_from_projections():
    boundary = NoteAuthority()
    assert boundary.authority_table == "note_documents"
    assert boundary.authority_id_column == "task_id"
    assert set(boundary.projections) == {"note_results", "conversation_messages", "wiki", "chroma"}
