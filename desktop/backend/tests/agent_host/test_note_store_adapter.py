from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.agent_host.note_contract import NoteId, SdkNoteDto
from app.agent_host.note_store_adapter import (
    IdempotencyConflictError,
    InvalidSourceError,
    NeedsAttentionError,
    NoteActorDto,
    NoteMeldNoteAuthority,
    NoteMeldNoteStoreAdapter,
    NoteMeldOperationStore,
    NoteProvenanceDto,
    PermissionDeniedError,
    SourceRefDto,
    VersionConflictError,
    canonical_payload_hash,
)
from app.db.note_agent_schema import ensure_note_agent_schema


def _prepare_database(tmp_path):
    database_path = tmp_path / "notemeld.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        PRAGMA user_version = 37;
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            deleted_at TEXT
        );
        CREATE TABLE note_documents (
            task_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            source_url TEXT,
            platform TEXT,
            model_name TEXT,
            style TEXT,
            status TEXT NOT NULL DEFAULT 'SUCCESS',
            wiki_status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT,
            updated_at TEXT,
            deleted_at TEXT,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        );
        INSERT INTO conversations(id) VALUES ('conversation-1');
        CREATE TABLE plugin_app_migrations (
            version INTEGER PRIMARY KEY,
            marker TEXT NOT NULL
        );
        INSERT INTO plugin_app_migrations(version, marker) VALUES (9, 'keep-me');
        """
    )
    connection.commit()
    connection.close()
    return database_path


def _provenance(*, source: str = "https://example.com/source"):
    return NoteProvenanceDto(
        actor=NoteActorDto(actor_id="actor-1", kind="agent"),
        plugin_id="official-link-note",
        plugin_version="1.0.0",
        turn_id="turn-1",
        sources=(SourceRefDto(authority="web", locator=source),),
    )


def _note(note_id: str, *, title: str = "N02", content: str = "# Body"):
    return SdkNoteDto(
        note_id=NoteId(note_id),
        title=title,
        content=content,
        source_url="https://example.com/source",
        platform="web",
    )


def test_migration_registry_coexists_and_survives_real_sqlite_reopen(tmp_path):
    database_path = _prepare_database(tmp_path)

    ensure_note_agent_schema(database_path)
    ensure_note_agent_schema(database_path)

    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "note_agent_app_migrations",
            "note_agent_sources",
            "note_agent_relations",
            "note_agent_operations",
            "note_agent_provenance",
        } <= tables
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 37
        assert connection.execute(
            "SELECT version, marker FROM plugin_app_migrations"
        ).fetchone() == (9, "keep-me")
        assert connection.execute(
            "SELECT version FROM note_agent_app_migrations"
        ).fetchall() == [(1,)]
    finally:
        connection.close()


def test_historical_note_uses_task_id_and_lazy_version_one_after_reopen(tmp_path):
    database_path = _prepare_database(tmp_path)
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        INSERT INTO note_documents(
            task_id, conversation_id, title, content, source_url, platform,
            created_at, updated_at
        ) VALUES ('legacy-task', 'conversation-1', 'Legacy', '# Legacy',
                  'https://example.com/legacy', 'web', CURRENT_TIMESTAMP,
                  CURRENT_TIMESTAMP)
        """
    )
    connection.commit()
    connection.close()

    first = NoteMeldNoteStoreAdapter(
        database_path, conversation_id="conversation-1"
    )
    assert first.read(NoteId("legacy-task")) == SdkNoteDto(
        note_id=NoteId("legacy-task"),
        title="Legacy",
        content="# Legacy",
        source_url="https://example.com/legacy",
        platform="web",
        version=1,
    )

    reopened = NoteMeldNoteStoreAdapter(
        database_path, conversation_id="conversation-1"
    )
    assert [note.note_id for note in reopened.search("Legacy")] == ["legacy-task"]


def test_same_request_replays_and_different_payload_conflicts(tmp_path):
    database_path = _prepare_database(tmp_path)
    adapter = NoteMeldNoteStoreAdapter(
        database_path, conversation_id="conversation-1"
    )
    provenance = _provenance()

    created = adapter.create(_note("task-1"), "request-1", provenance=provenance)
    replayed = adapter.create(_note("task-1"), "request-1", provenance=provenance)

    assert created.note and created.note.note_id == "task-1"
    assert replayed.replayed is True
    assert replayed.note == created.note
    with pytest.raises(IdempotencyConflictError, match="different payload"):
        adapter.create(
            _note("task-1", content="# Changed"),
            "request-1",
            provenance=provenance,
        )

    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM note_documents").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM note_agent_operations"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM note_agent_provenance"
        ).fetchone()[0] == 1
        source_ids = connection.execute(
            "SELECT source_ids_json FROM note_agent_provenance"
        ).fetchone()[0]
        assert "note-src-" in source_ids
    finally:
        connection.close()
    assert adapter.sources(NoteId("task-1")) == provenance.sources
    persisted_provenance = adapter.provenance(NoteId("task-1"), version=1)
    assert persisted_provenance[0]["actor"] == {"id": "actor-1", "kind": "agent"}
    assert persisted_provenance[0]["plugin"] == {
        "plugin_id": "official-link-note",
        "plugin_version": "1.0.0",
    }


def test_expected_version_serializes_concurrent_updates(tmp_path):
    database_path = _prepare_database(tmp_path)
    adapter = NoteMeldNoteStoreAdapter(
        database_path, conversation_id="conversation-1"
    )
    adapter.create(_note("task-1"), "create", provenance=_provenance())

    def update(request_id: str, content: str):
        worker = NoteMeldNoteStoreAdapter(
            database_path, conversation_id="conversation-1"
        )
        try:
            return worker.update(
                _note("task-1", content=content),
                request_id,
                1,
                provenance=_provenance(),
            )
        except VersionConflictError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda args: update(*args),
                (("update-a", "# A"), ("update-b", "# B")),
            )
        )

    successes = [result for result in results if not isinstance(result, Exception)]
    conflicts = [result for result in results if isinstance(result, VersionConflictError)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert conflicts[0].expected == 1
    assert conflicts[0].actual == 2
    assert adapter.read(NoteId("task-1")).version == 2


def test_note_operation_and_provenance_roll_back_as_one_transaction(tmp_path):
    database_path = _prepare_database(tmp_path)
    adapter = NoteMeldNoteStoreAdapter(
        database_path, conversation_id="conversation-1"
    )
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TRIGGER reject_note_provenance
        BEFORE INSERT ON note_agent_provenance
        BEGIN
            SELECT RAISE(ABORT, 'provenance unavailable');
        END
        """
    )
    connection.commit()
    connection.close()

    with pytest.raises(sqlite3.IntegrityError, match="provenance unavailable"):
        adapter.create(
            _note("rolled-back"),
            "atomic-request",
            provenance=_provenance(),
        )

    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM note_documents WHERE task_id = 'rolled-back'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM note_agent_sources"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM note_agent_operations"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_incomplete_operation_becomes_needs_attention_on_reopen(tmp_path):
    database_path = _prepare_database(tmp_path)
    first = NoteMeldOperationStore(database_path)
    payload_hash = canonical_payload_hash({"title": "uncertain"})
    begun = first.begin(
        request_id="uncertain-request",
        payload_hash=payload_hash,
        kind="create",
    )
    assert begun.status == "started"

    reopened = NoteMeldOperationStore(database_path)
    assert reopened.get_by_request("uncertain-request")["status"] == "needs_attention"
    with pytest.raises(NeedsAttentionError, match="needs attention"):
        reopened.begin(
            request_id="uncertain-request",
            payload_hash=payload_hash,
            kind="create",
        )


def test_operation_store_checkpoints_commits_replays_and_fails(tmp_path):
    database_path = _prepare_database(tmp_path)
    store = NoteMeldOperationStore(database_path)
    payload_hash = canonical_payload_hash({"title": "durable"})
    started = store.begin(
        request_id="durable-request",
        payload_hash=payload_hash,
        kind="update",
        note_id=NoteId("note-1"),
        expected_version=2,
    )
    store.checkpoint(started.operation_id, {"phase": "effect_committed"})
    outcome = {"note_id": "note-1", "version": 3, "status": "committed"}
    store.commit(started.operation_id, outcome)

    replay = store.begin(
        request_id="durable-request",
        payload_hash=payload_hash,
        kind="update",
        note_id=NoteId("note-1"),
        expected_version=2,
    )
    assert replay.status == "already_completed"
    assert replay.outcome == outcome
    assert store.get_by_request("durable-request")["checkpoint"] == {
        "phase": "effect_committed"
    }

    failed = store.begin(
        request_id="failed-request",
        payload_hash=canonical_payload_hash({"title": "failed"}),
        kind="create",
    )
    store.fail(failed.operation_id, {"code": "invalid_source"})
    assert store.get_by_request("failed-request")["status"] == "failed"


def test_note_commit_survives_projection_failure_and_is_not_replayed(tmp_path):
    database_path = _prepare_database(tmp_path)
    adapter = NoteMeldNoteStoreAdapter(
        database_path, conversation_id="conversation-1"
    )
    calls = []

    def broken_projection(note):
        calls.append(note.note_id)
        raise RuntimeError("wiki unavailable")

    result = adapter.create(
        _note("task-projection"),
        "projection-request",
        provenance=_provenance(),
        projectors=(broken_projection,),
    )
    replay = adapter.create(
        _note("task-projection"),
        "projection-request",
        provenance=_provenance(),
        projectors=(broken_projection,),
    )

    assert result.note == adapter.read(NoteId("task-projection"))
    assert result.projection_errors == ("RuntimeError: projection failed",)
    assert replay.replayed is True
    assert replay.projection_errors == ()
    assert calls == ["task-projection"]
    assert adapter.operations.get_by_request("projection-request")["status"] == "committed"


def test_link_and_authority_are_persisted_without_copying_note_body(tmp_path):
    database_path = _prepare_database(tmp_path)
    adapter = NoteMeldNoteStoreAdapter(
        database_path, conversation_id="conversation-1"
    )
    adapter.create(_note("parent"), "create-parent", provenance=_provenance())
    adapter.create(_note("child"), "create-child", provenance=_provenance())

    linked = adapter.link(
        NoteId("child"),
        NoteId("parent"),
        "link-request",
        provenance=_provenance(),
        kind="derived_from",
    )
    replayed = adapter.link(
        NoteId("child"),
        NoteId("parent"),
        "link-request",
        provenance=_provenance(),
        kind="derived_from",
    )

    assert linked.relation and linked.relation.kind == "derived_from"
    assert replayed.replayed is True
    assert adapter.relations(NoteId("child")) == (linked.relation,)
    connection = sqlite3.connect(database_path)
    try:
        metadata_columns = {
            row[1]
            for table in (
                "note_agent_sources",
                "note_agent_relations",
                "note_agent_operations",
                "note_agent_provenance",
            )
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
        assert "content" not in metadata_columns
        assert "title" not in metadata_columns
    finally:
        connection.close()

    authority = NoteMeldNoteAuthority()
    with pytest.raises(PermissionDeniedError):
        authority.can_write(NoteActorDto("unknown", "manifest"))
    with pytest.raises(InvalidSourceError):
        authority.trust_source(SourceRefDto("local", "/private/secret.md"))
