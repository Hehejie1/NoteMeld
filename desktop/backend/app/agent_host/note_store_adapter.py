"""Thin NoteMeld persistence adapters for the fixed SDK Note v1 ports.

The SDK owns Note Agent behavior.  This module only translates its JSON-shaped
Note/operation/authority contract to the existing ``note_documents`` authority
and the N02 namespaced metadata tables.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence
from urllib.parse import urlparse

from app.agent_host.note_contract import NoteId, SdkNoteDto, note_id_from_task_id
from app.db.note_agent_schema import (
    connect_note_agent_database,
    ensure_note_agent_schema,
)


class NoteAdapterError(RuntimeError):
    pass


class NoteNotFoundError(NoteAdapterError):
    pass


class IdempotencyConflictError(NoteAdapterError):
    pass


class VersionConflictError(NoteAdapterError):
    def __init__(self, note_id: str, expected: int, actual: int):
        super().__init__(
            f"version conflict for {note_id}: expected {expected}, found {actual}"
        )
        self.note_id = note_id
        self.expected = expected
        self.actual = actual


class NeedsAttentionError(NoteAdapterError):
    pass


class PermissionDeniedError(NoteAdapterError):
    pass


class InvalidSourceError(NoteAdapterError):
    pass


@dataclass(frozen=True)
class NoteActorDto:
    actor_id: str
    kind: str


@dataclass(frozen=True)
class SourceRefDto:
    authority: str
    locator: str
    digest: str | None = None
    captured_at: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class NoteProvenanceDto:
    actor: NoteActorDto
    operation_id: str = ""
    plugin_id: str | None = None
    plugin_version: str | None = None
    turn_id: str | None = None
    sources: tuple[SourceRefDto, ...] = ()


@dataclass(frozen=True)
class NoteRelationDto:
    relation_id: str
    source: NoteId
    target: NoteId
    kind: str = "related"
    operation_id: str = ""


@dataclass(frozen=True)
class NoteMutationResult:
    note: SdkNoteDto | None
    operation_id: str
    replayed: bool = False
    relation: NoteRelationDto | None = None
    projection_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationBeginResult:
    status: str
    operation_id: str
    outcome: Mapping[str, object] | None = None


def canonical_payload_hash(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _operation_id(request_id: str) -> str:
    digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    return f"note-op-{digest[:32]}"


def _require_text(label: str, value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} must be nonempty")
    return normalized


class NoteMeldNoteAuthority:
    """Product authority for actors and source locators, not an SDK policy copy."""

    _ACTOR_KINDS = frozenset({"user", "agent", "plugin", "system"})
    _SOURCE_SCHEMES = frozenset({"http", "https", "note", "task", "upload"})

    def validate_actor(self, actor: NoteActorDto) -> None:
        _require_text("actor id", actor.actor_id)
        if actor.kind not in self._ACTOR_KINDS:
            raise PermissionDeniedError(f"unsupported actor kind: {actor.kind}")

    def can_read(self, actor: NoteActorDto, note_id: NoteId) -> None:
        self.validate_actor(actor)
        note_id_from_task_id(str(note_id))

    def can_write(self, actor: NoteActorDto, note_id: NoteId | None = None) -> None:
        self.validate_actor(actor)
        if note_id is not None:
            note_id_from_task_id(str(note_id))

    def can_link(self, actor: NoteActorDto, source: NoteId, target: NoteId) -> None:
        self.can_write(actor, source)
        note_id_from_task_id(str(target))
        if source == target:
            raise PermissionDeniedError("self relation is not allowed")

    def trust_source(self, source: SourceRefDto) -> None:
        authority = _require_text("source authority", source.authority)
        locator = _require_text("source locator", source.locator)
        if len(locator.encode("utf-8")) > 4096:
            raise InvalidSourceError("source locator exceeds SDK limit")
        parsed = urlparse(locator)
        if parsed.scheme.lower() not in self._SOURCE_SCHEMES:
            raise InvalidSourceError(f"untrusted source locator for {authority}")
        if parsed.scheme.lower() in {"http", "https"} and not parsed.netloc:
            raise InvalidSourceError("web source requires a host")
        if source.digest and (
            not source.digest.startswith("sha256:")
            or len(source.digest) != len("sha256:") + 64
            or any(character not in "0123456789abcdefABCDEF" for character in source.digest[7:])
        ):
            raise InvalidSourceError("source digest must use sha256:<hex>")
        metadata_size = len(_json(dict(source.metadata)).encode("utf-8"))
        if metadata_size > 16 * 1024:
            raise InvalidSourceError("source metadata exceeds SDK limit")


class NoteMeldOperationStore:
    """Durable SDK operation ledger sharing the NoteMeld SQLite file."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        ensure_note_agent_schema(self.database_path)
        self.recover_incomplete()

    def _connect(self) -> sqlite3.Connection:
        return connect_note_agent_database(self.database_path)

    def recover_incomplete(self) -> tuple[str, ...]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT operation_id FROM note_agent_operations
                WHERE status IN ('begun', 'checkpointed')
                ORDER BY operation_id
                """
            ).fetchall()
            ids = tuple(str(row[0]) for row in rows)
            connection.execute(
                """
                UPDATE note_agent_operations
                SET status = 'needs_attention', updated_at = ?
                WHERE status IN ('begun', 'checkpointed')
                """,
                (_now(),),
            )
            connection.commit()
            return ids
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def begin(
        self,
        *,
        request_id: str,
        payload_hash: str,
        kind: str,
        note_id: NoteId | None = None,
        expected_version: int | None = None,
        operation_id: str | None = None,
    ) -> OperationBeginResult:
        request_id = _require_text("request id", request_id)
        operation_id = operation_id or _operation_id(request_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            result = _begin_operation(
                connection,
                operation_id=operation_id,
                request_id=request_id,
                payload_hash=_require_text("payload hash", payload_hash),
                kind=kind,
                note_id=str(note_id) if note_id is not None else None,
                expected_version=expected_version,
            )
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def checkpoint(self, operation_id: str, checkpoint: Mapping[str, object]) -> None:
        self._transition(
            operation_id,
            "checkpointed",
            "checkpoint_json = ?",
            _json(checkpoint),
            allowed=("begun", "checkpointed"),
        )

    def commit(self, operation_id: str, outcome: Mapping[str, object]) -> None:
        self._transition(
            operation_id,
            "committed",
            "outcome_json = ?",
            _json(outcome),
            allowed=("begun", "checkpointed"),
        )

    def fail(self, operation_id: str, error: Mapping[str, object]) -> None:
        self._transition(
            operation_id,
            "failed",
            "error_json = ?",
            _json(error),
            allowed=("begun", "checkpointed"),
        )

    def mark_needs_attention(self, operation_id: str) -> None:
        self._transition(
            operation_id,
            "needs_attention",
            "checkpoint_json = checkpoint_json",
            allowed=("begun", "checkpointed", "needs_attention"),
        )

    def _transition(
        self,
        operation_id: str,
        status: str,
        extra_assignment: str,
        extra_value: str | None = None,
        *,
        allowed: tuple[str, ...],
    ) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in allowed)
            params: list[object] = [status, _now()]
            if extra_value is not None:
                params.append(extra_value)
            params.extend([operation_id, *allowed])
            changed = connection.execute(
                f"""
                UPDATE note_agent_operations
                SET status = ?, updated_at = ?, {extra_assignment}
                WHERE operation_id = ? AND status IN ({placeholders})
                """,
                params,
            ).rowcount
            if changed != 1:
                raise NeedsAttentionError(f"operation cannot transition: {operation_id}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_by_request(self, request_id: str) -> Mapping[str, object] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT operation_id, request_id, payload_hash, kind, note_id,
                       expected_version, status, checkpoint_json, outcome_json,
                       error_json
                FROM note_agent_operations WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "operation_id": row["operation_id"],
                "request_id": row["request_id"],
                "payload_hash": row["payload_hash"],
                "kind": row["kind"],
                "note_id": row["note_id"],
                "expected_version": row["expected_version"],
                "status": row["status"],
                "checkpoint": json.loads(row["checkpoint_json"])
                if row["checkpoint_json"]
                else None,
                "outcome": json.loads(row["outcome_json"])
                if row["outcome_json"]
                else None,
                "error": json.loads(row["error_json"])
                if row["error_json"]
                else None,
            }
        finally:
            connection.close()


class NoteMeldNoteStoreAdapter:
    """N01 ``NoteSdkAdapter`` plus operation and authority ports."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        conversation_id: str,
        authority: NoteMeldNoteAuthority | None = None,
    ):
        self.database_path = Path(database_path)
        self.conversation_id = _require_text("conversation id", conversation_id)
        ensure_note_agent_schema(self.database_path)
        self.operations = NoteMeldOperationStore(self.database_path)
        self.authority = authority or NoteMeldNoteAuthority()

    def _connect(self) -> sqlite3.Connection:
        return connect_note_agent_database(self.database_path)

    def read(self, note_id: NoteId) -> SdkNoteDto | None:
        connection = self._connect()
        try:
            return _read_note(connection, note_id)
        finally:
            connection.close()

    def search(self, query: str, limit: int = 10) -> Sequence[SdkNoteDto]:
        normalized = str(query or "").strip()
        bounded_limit = max(1, min(int(limit or 10), 256))
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT task_id FROM note_documents
                WHERE deleted_at IS NULL AND (title LIKE ? OR content LIKE ?)
                ORDER BY updated_at DESC, created_at DESC, task_id
                LIMIT ?
                """,
                (f"%{normalized}%", f"%{normalized}%", bounded_limit),
            ).fetchall()
            return tuple(
                note
                for row in rows
                if (note := _read_note(connection, NoteId(str(row[0])))) is not None
            )
        finally:
            connection.close()

    def create(
        self,
        note: SdkNoteDto,
        request_id: str,
        *,
        provenance: NoteProvenanceDto,
        projectors: Iterable[Callable[[SdkNoteDto], None]] = (),
    ) -> NoteMutationResult:
        note_id = note_id_from_task_id(str(note.note_id))
        self.authority.can_write(provenance.actor, note_id)
        _validate_note(note)
        self._validate_sources(provenance.sources)
        payload = _mutation_payload("create", note, provenance)
        payload_hash = canonical_payload_hash(payload)
        operation_id = provenance.operation_id or _operation_id(request_id)

        connection = self._connect()
        replayed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            begin = _begin_operation(
                connection,
                operation_id=operation_id,
                request_id=request_id,
                payload_hash=payload_hash,
                kind="create",
                note_id=str(note_id),
                expected_version=None,
            )
            operation_id = begin.operation_id
            if begin.status == "already_completed":
                replayed = True
            else:
                if _read_note(connection, note_id) is not None:
                    raise VersionConflictError(str(note_id), 0, _note_version(connection, note_id))
                now = _now()
                connection.execute(
                    """
                    INSERT INTO note_documents(
                        task_id, conversation_id, title, content, source_url,
                        platform, model_name, style, status, wiki_status,
                        created_at, updated_at, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 'SUCCESS', 'pending', ?, ?, NULL)
                    """,
                    (
                        str(note_id),
                        self.conversation_id,
                        note.title,
                        note.content,
                        note.source_url or _primary_source(provenance.sources),
                        note.platform,
                        now,
                        now,
                    ),
                )
                _persist_sources(connection, note_id, operation_id, provenance.sources, now)
                _persist_provenance(
                    connection, note_id, 1, operation_id, provenance, now
                )
                _commit_operation(connection, operation_id, note_id, 1, payload_hash)
            committed = _require_note(connection, note_id)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        errors = () if replayed else _run_projectors(projectors, committed)
        return NoteMutationResult(committed, operation_id, replayed, projection_errors=errors)

    def update(
        self,
        note: SdkNoteDto,
        request_id: str,
        expected_version: int,
        *,
        provenance: NoteProvenanceDto,
        projectors: Iterable[Callable[[SdkNoteDto], None]] = (),
    ) -> NoteMutationResult:
        note_id = note_id_from_task_id(str(note.note_id))
        self.authority.can_write(provenance.actor, note_id)
        _validate_note(note)
        self._validate_sources(provenance.sources)
        payload = _mutation_payload(
            "update", note, provenance, expected_version=expected_version
        )
        payload_hash = canonical_payload_hash(payload)
        operation_id = provenance.operation_id or _operation_id(request_id)

        connection = self._connect()
        replayed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            begin = _begin_operation(
                connection,
                operation_id=operation_id,
                request_id=request_id,
                payload_hash=payload_hash,
                kind="update",
                note_id=str(note_id),
                expected_version=expected_version,
            )
            operation_id = begin.operation_id
            if begin.status == "already_completed":
                replayed = True
            else:
                _require_note(connection, note_id)
                actual = _note_version(connection, note_id)
                if actual != expected_version:
                    raise VersionConflictError(str(note_id), expected_version, actual)
                next_version = actual + 1
                now = _now()
                connection.execute(
                    """
                    UPDATE note_documents
                    SET title = ?, content = ?, source_url = ?, platform = ?,
                        status = 'SUCCESS', updated_at = ?
                    WHERE task_id = ? AND deleted_at IS NULL
                    """,
                    (
                        note.title,
                        note.content,
                        note.source_url or _primary_source(provenance.sources),
                        note.platform,
                        now,
                        str(note_id),
                    ),
                )
                _persist_sources(connection, note_id, operation_id, provenance.sources, now)
                _persist_provenance(
                    connection,
                    note_id,
                    next_version,
                    operation_id,
                    provenance,
                    now,
                )
                _commit_operation(
                    connection, operation_id, note_id, next_version, payload_hash
                )
            committed = _require_note(connection, note_id)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        errors = () if replayed else _run_projectors(projectors, committed)
        return NoteMutationResult(committed, operation_id, replayed, projection_errors=errors)

    def link(
        self,
        source: NoteId,
        target: NoteId,
        request_id: str,
        *,
        provenance: NoteProvenanceDto,
        kind: str = "related",
    ) -> NoteMutationResult:
        source = note_id_from_task_id(str(source))
        target = note_id_from_task_id(str(target))
        self.authority.can_link(provenance.actor, source, target)
        self._validate_sources(provenance.sources)
        relation_id = f"note-rel-{hashlib.sha256(request_id.encode()).hexdigest()[:32]}"
        payload = {
            "kind": "link",
            "source": str(source),
            "target": str(target),
            "relation_kind": kind,
            "provenance": _provenance_payload(provenance),
        }
        payload_hash = canonical_payload_hash(payload)
        operation_id = provenance.operation_id or _operation_id(request_id)

        connection = self._connect()
        replayed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            begin = _begin_operation(
                connection,
                operation_id=operation_id,
                request_id=request_id,
                payload_hash=payload_hash,
                kind="link",
                note_id=str(source),
                expected_version=None,
            )
            operation_id = begin.operation_id
            if begin.status == "already_completed":
                replayed = True
            else:
                _require_note(connection, source)
                _require_note(connection, target)
                now = _now()
                connection.execute(
                    """
                    INSERT INTO note_agent_relations(
                        relation_id, from_note_id, to_note_id, kind,
                        operation_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (relation_id, str(source), str(target), kind, operation_id, now),
                )
                _persist_sources(connection, source, operation_id, provenance.sources, now)
                _persist_provenance(
                    connection, None, None, operation_id, provenance, now
                )
                _commit_operation(
                    connection,
                    operation_id,
                    source,
                    _note_version(connection, source),
                    payload_hash,
                    relation_id=relation_id,
                )
            relation = _require_relation(connection, relation_id)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return NoteMutationResult(None, operation_id, replayed, relation=relation)

    def relations(self, note_id: NoteId) -> Sequence[NoteRelationDto]:
        connection = self._connect()
        try:
            _require_note(connection, note_id)
            rows = connection.execute(
                """
                SELECT relation_id, from_note_id, to_note_id, kind, operation_id
                FROM note_agent_relations
                WHERE from_note_id = ? OR to_note_id = ?
                ORDER BY relation_id
                """,
                (str(note_id), str(note_id)),
            ).fetchall()
            return tuple(_relation_from_row(row) for row in rows)
        finally:
            connection.close()

    def sources(self, note_id: NoteId) -> Sequence[SourceRefDto]:
        connection = self._connect()
        try:
            _require_note(connection, note_id)
            rows = connection.execute(
                """
                SELECT authority, locator, digest, captured_at, metadata_json
                FROM note_agent_sources WHERE note_id = ? ORDER BY created_at, source_id
                """,
                (str(note_id),),
            ).fetchall()
            return tuple(
                SourceRefDto(
                    authority=str(row["authority"]),
                    locator=str(row["locator"]),
                    digest=str(row["digest"]) if row["digest"] else None,
                    captured_at=str(row["captured_at"]) if row["captured_at"] else None,
                    metadata=json.loads(row["metadata_json"]),
                )
                for row in rows
            )
        finally:
            connection.close()

    def provenance(
        self, note_id: NoteId, version: int | None = None
    ) -> Sequence[Mapping[str, object]]:
        connection = self._connect()
        try:
            _require_note(connection, note_id)
            params: list[object] = [str(note_id)]
            version_sql = ""
            if version is not None:
                version_sql = " AND note_version = ?"
                params.append(version)
            rows = connection.execute(
                f"""
                SELECT provenance_id, note_version, operation_id, actor_id,
                       actor_kind, plugin_id, plugin_version, turn_id,
                       source_ids_json, created_at
                FROM note_agent_provenance
                WHERE note_id = ?{version_sql}
                ORDER BY note_version
                """,
                params,
            ).fetchall()
            return tuple(
                {
                    "provenance_id": row["provenance_id"],
                    "note_id": str(note_id),
                    "note_version": row["note_version"],
                    "operation_id": row["operation_id"],
                    "actor": {"id": row["actor_id"], "kind": row["actor_kind"]},
                    "plugin": (
                        {
                            "plugin_id": row["plugin_id"],
                            "plugin_version": row["plugin_version"],
                        }
                        if row["plugin_id"] or row["plugin_version"]
                        else None
                    ),
                    "turn_id": row["turn_id"],
                    "source_ids": json.loads(row["source_ids_json"]),
                    "created_at": row["created_at"],
                }
                for row in rows
            )
        finally:
            connection.close()

    def _validate_sources(self, sources: Sequence[SourceRefDto]) -> None:
        for source in sources:
            self.authority.trust_source(source)


def _begin_operation(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    request_id: str,
    payload_hash: str,
    kind: str,
    note_id: str | None,
    expected_version: int | None,
) -> OperationBeginResult:
    existing = connection.execute(
        """
        SELECT operation_id, payload_hash, status, outcome_json
        FROM note_agent_operations WHERE request_id = ?
        """,
        (request_id,),
    ).fetchone()
    if existing is not None:
        if existing["payload_hash"] != payload_hash:
            raise IdempotencyConflictError(f"different payload for request {request_id}")
        if existing["status"] == "needs_attention":
            raise NeedsAttentionError(f"operation needs attention: {existing['operation_id']}")
        if existing["status"] == "committed" and existing["outcome_json"]:
            return OperationBeginResult(
                "already_completed",
                str(existing["operation_id"]),
                json.loads(existing["outcome_json"]),
            )
        raise NeedsAttentionError(f"operation is not safely replayable: {existing['operation_id']}")

    now = _now()
    connection.execute(
        """
        INSERT INTO note_agent_operations(
            operation_id, request_id, payload_hash, kind, note_id,
            expected_version, status, checkpoint_json, outcome_json,
            error_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'begun', NULL, NULL, NULL, ?, ?)
        """,
        (
            operation_id,
            request_id,
            payload_hash,
            kind,
            note_id,
            expected_version,
            now,
            now,
        ),
    )
    return OperationBeginResult("started", operation_id)


def _commit_operation(
    connection: sqlite3.Connection,
    operation_id: str,
    note_id: NoteId,
    version: int,
    payload_hash: str,
    *,
    relation_id: str | None = None,
) -> None:
    outcome = {
        "operation_id": operation_id,
        "note_id": str(note_id),
        "version": version,
        "payload_hash": payload_hash,
        "status": "committed",
    }
    if relation_id:
        outcome["relation_id"] = relation_id
    connection.execute(
        """
        UPDATE note_agent_operations
        SET status = 'committed', outcome_json = ?, updated_at = ?
        WHERE operation_id = ? AND status = 'begun'
        """,
        (_json(outcome), _now(), operation_id),
    )


def _read_note(connection: sqlite3.Connection, note_id: NoteId) -> SdkNoteDto | None:
    row = connection.execute(
        """
        SELECT task_id, title, content, source_url, platform, created_at, updated_at
        FROM note_documents WHERE task_id = ? AND deleted_at IS NULL
        """,
        (str(note_id),),
    ).fetchone()
    if row is None:
        return None
    return SdkNoteDto(
        note_id=NoteId(str(row["task_id"])),
        title=str(row["title"] or ""),
        content=str(row["content"] or ""),
        source_url=str(row["source_url"] or ""),
        platform=str(row["platform"] or ""),
        version=_note_version(connection, note_id),
    )


def _require_note(connection: sqlite3.Connection, note_id: NoteId) -> SdkNoteDto:
    note = _read_note(connection, note_id)
    if note is None:
        raise NoteNotFoundError(f"note not found: {note_id}")
    return note


def _note_version(connection: sqlite3.Connection, note_id: NoteId) -> int:
    row = connection.execute(
        """
        SELECT MAX(note_version) FROM note_agent_provenance
        WHERE note_id = ? AND note_version IS NOT NULL
        """,
        (str(note_id),),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 1


def _persist_sources(
    connection: sqlite3.Connection,
    note_id: NoteId,
    operation_id: str,
    sources: Sequence[SourceRefDto],
    now: str,
) -> tuple[str, ...]:
    ids: list[str] = []
    for index, source in enumerate(sources):
        digest = hashlib.sha256(
            f"{operation_id}\0{index}\0{source.authority}\0{source.locator}".encode()
        ).hexdigest()
        source_id = f"note-src-{digest[:32]}"
        connection.execute(
            """
            INSERT INTO note_agent_sources(
                source_id, note_id, authority, locator, digest, captured_at,
                metadata_json, operation_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                str(note_id),
                source.authority,
                source.locator,
                source.digest,
                source.captured_at,
                _json(dict(source.metadata)),
                operation_id,
                now,
            ),
        )
        ids.append(source_id)
    return tuple(ids)


def _persist_provenance(
    connection: sqlite3.Connection,
    note_id: NoteId | None,
    note_version: int | None,
    operation_id: str,
    provenance: NoteProvenanceDto,
    now: str,
) -> None:
    source_rows = connection.execute(
        "SELECT source_id FROM note_agent_sources WHERE operation_id = ? ORDER BY source_id",
        (operation_id,),
    ).fetchall()
    source_ids = [str(row[0]) for row in source_rows]
    provenance_id = f"note-prov-{hashlib.sha256(operation_id.encode()).hexdigest()[:32]}"
    connection.execute(
        """
        INSERT INTO note_agent_provenance(
            provenance_id, note_id, note_version, operation_id, actor_id,
            actor_kind, plugin_id, plugin_version, turn_id, source_ids_json,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            provenance_id,
            str(note_id) if note_id is not None else None,
            note_version,
            operation_id,
            provenance.actor.actor_id,
            provenance.actor.kind,
            provenance.plugin_id,
            provenance.plugin_version,
            provenance.turn_id,
            _json(source_ids),
            now,
        ),
    )


def _validate_note(note: SdkNoteDto) -> None:
    if not note.title.strip():
        raise ValueError("note title must be nonempty")
    if len(note.title.encode("utf-8")) > 512:
        raise ValueError("note title exceeds SDK limit")
    if not note.content.strip():
        raise ValueError("note content must be nonempty")
    if len(note.content.encode("utf-8")) > 1024 * 1024:
        raise ValueError("note content exceeds SDK limit")
    note_id = str(note.note_id)
    if len(note_id.encode("utf-8")) > 256:
        raise ValueError("note id exceeds SDK limit")
    if note.content_format != "markdown":
        raise ValueError("NoteMeld Note authority accepts markdown content")


def _primary_source(sources: Sequence[SourceRefDto]) -> str:
    return sources[0].locator if sources else ""


def _provenance_payload(provenance: NoteProvenanceDto) -> Mapping[str, object]:
    return {
        "actor": {"id": provenance.actor.actor_id, "kind": provenance.actor.kind},
        "plugin": (
            {
                "plugin_id": provenance.plugin_id,
                "plugin_version": provenance.plugin_version,
            }
            if provenance.plugin_id or provenance.plugin_version
            else None
        ),
        "turn_id": provenance.turn_id,
        "sources": [
            {
                "authority": source.authority,
                "locator": source.locator,
                "digest": source.digest,
                "captured_at": source.captured_at,
                "metadata": dict(source.metadata),
            }
            for source in provenance.sources
        ],
    }


def _mutation_payload(
    kind: str,
    note: SdkNoteDto,
    provenance: NoteProvenanceDto,
    *,
    expected_version: int | None = None,
) -> Mapping[str, object]:
    return {
        "kind": kind,
        "note": {
            "id": str(note.note_id),
            "title": note.title,
            "content": note.content,
            "content_format": note.content_format,
            "source_url": note.source_url,
            "platform": note.platform,
        },
        "expected_version": expected_version,
        "provenance": _provenance_payload(provenance),
    }


def _run_projectors(
    projectors: Iterable[Callable[[SdkNoteDto], None]], note: SdkNoteDto
) -> tuple[str, ...]:
    errors: list[str] = []
    for projector in projectors:
        try:
            projector(note)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: projection failed")
    return tuple(errors)


def _relation_from_row(row: sqlite3.Row) -> NoteRelationDto:
    return NoteRelationDto(
        relation_id=str(row["relation_id"]),
        source=NoteId(str(row["from_note_id"])),
        target=NoteId(str(row["to_note_id"])),
        kind=str(row["kind"]),
        operation_id=str(row["operation_id"]),
    )


def _require_relation(connection: sqlite3.Connection, relation_id: str) -> NoteRelationDto:
    row = connection.execute(
        """
        SELECT relation_id, from_note_id, to_note_id, kind, operation_id
        FROM note_agent_relations WHERE relation_id = ?
        """,
        (relation_id,),
    ).fetchone()
    if row is None:
        raise NoteNotFoundError(f"relation not found: {relation_id}")
    return _relation_from_row(row)


__all__ = [
    "IdempotencyConflictError",
    "InvalidSourceError",
    "NeedsAttentionError",
    "NoteActorDto",
    "NoteMeldNoteAuthority",
    "NoteMeldNoteStoreAdapter",
    "NoteMeldOperationStore",
    "NoteMutationResult",
    "NoteNotFoundError",
    "NoteProvenanceDto",
    "NoteRelationDto",
    "OperationBeginResult",
    "PermissionDeniedError",
    "SourceRefDto",
    "VersionConflictError",
    "canonical_payload_hash",
]
