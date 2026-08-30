from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import sqlite3
import time
from threading import Lock

from .protocol import SessionCommand


_PROCESS_OWNER = f"{os.getpid()}:{secrets.token_urlsafe(12)}"


@dataclass(frozen=True)
class QueueReceipt:
    sequence: int
    status: str


class SessionMailbox:
    """Process-local queue used by a device Host until durable ledger wiring lands."""

    def __init__(self, max_size: int = 1000):
        if type(max_size) is not int or max_size < 1:
            raise ValueError("max_size must be positive")
        self._items: deque[SessionCommand] = deque()
        self._next_sequence: dict[str, int] = {}
        self._max_size = max_size
        self._seen: dict[tuple[str, str], SessionCommand] = {}
        self._lock = Lock()

    def enqueue(self, session_id: str, request_id: str, input_text: str, authority_epoch: int = 0) -> QueueReceipt:
        with self._lock:
            identity = (session_id, request_id)
            existing = self._seen.get(identity)
            if existing:
                if existing.payload_hash != SessionCommand.create(session_id, request_id, input_text, existing.sequence, authority_epoch).payload_hash:
                    raise ValueError("payload conflict")
                return QueueReceipt(existing.sequence, "duplicate")
            if len(self._items) >= self._max_size:
                raise OverflowError("session queue is full")
            sequence = self._next_sequence.get(session_id, 1)
            command = SessionCommand.create(session_id, request_id, input_text, sequence, authority_epoch)
            self._next_sequence[session_id] = sequence + 1
            self._seen[identity] = command
            self._items.append(command)
            return QueueReceipt(command.sequence, "queued")

    def pop(self) -> SessionCommand | None:
        with self._lock:
            return self._items.popleft() if self._items else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class DurableSessionMailbox:
    """SQLite-backed mailbox for a local host that must survive restart."""

    def __init__(self, database: Path, max_size: int = 1000, process_owner: str | None = None):
        if type(max_size) is not int or max_size < 1:
            raise ValueError("max_size must be positive")
        self.database = database
        self.max_size = max_size
        self.process_owner = process_owner or _PROCESS_OWNER
        if not self.process_owner:
            raise ValueError("process owner is required")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as cx:
            cx.execute("CREATE TABLE IF NOT EXISTS sync_mailbox (session_id TEXT NOT NULL, request_id TEXT NOT NULL, input_text TEXT NOT NULL, sequence INTEGER NOT NULL, authority_epoch INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'queued', lease_owner TEXT, created_at INTEGER NOT NULL, PRIMARY KEY(session_id, request_id), UNIQUE(session_id, sequence))")
            columns = {str(row[1]) for row in cx.execute("PRAGMA table_info(sync_mailbox)").fetchall()}
            if "lease_owner" not in columns:
                cx.execute("ALTER TABLE sync_mailbox ADD COLUMN lease_owner TEXT")
            cx.execute("CREATE TABLE IF NOT EXISTS sync_mailbox_authority (session_id TEXT PRIMARY KEY, authority_epoch INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
            cx.execute("INSERT OR IGNORE INTO sync_mailbox_authority(session_id,authority_epoch,updated_at) SELECT session_id,MAX(authority_epoch),? FROM sync_mailbox GROUP BY session_id", (int(time.time()),))
            cx.execute("UPDATE sync_mailbox SET status='needs_attention',lease_owner=NULL WHERE status='admitted' AND (lease_owner IS NULL OR lease_owner<>?)", (self.process_owner,))

    def enqueue(self, session_id: str, request_id: str, input_text: str, authority_epoch: int = 0) -> QueueReceipt:
        with self._connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            authority = cx.execute("SELECT authority_epoch FROM sync_mailbox_authority WHERE session_id=?", (session_id,)).fetchone()
            if authority is None:
                cx.execute("INSERT INTO sync_mailbox_authority(session_id,authority_epoch,updated_at) VALUES(?,?,?)", (session_id, authority_epoch, int(time.time())))
            elif int(authority[0]) != authority_epoch:
                cx.execute("ROLLBACK")
                raise ValueError("authority epoch mismatch")
            existing = cx.execute("SELECT input_text,sequence FROM sync_mailbox WHERE session_id=? AND request_id=?", (session_id, request_id)).fetchone()
            if existing:
                if existing[0] != input_text:
                    cx.execute("ROLLBACK")
                    raise ValueError("payload conflict")
                cx.execute("COMMIT")
                return QueueReceipt(existing[1], "duplicate")
            recovery_required = cx.execute("SELECT 1 FROM sync_mailbox WHERE session_id=? AND status='needs_attention' LIMIT 1", (session_id,)).fetchone()
            if recovery_required:
                cx.execute("ROLLBACK")
                raise RuntimeError("session recovery is required before accepting new commands")
            count = cx.execute("SELECT COUNT(*) FROM sync_mailbox WHERE session_id=? AND status IN ('queued','admitted','needs_attention')", (session_id,)).fetchone()[0]
            if count >= self.max_size:
                cx.execute("ROLLBACK")
                raise OverflowError("session queue is full")
            sequence = cx.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM sync_mailbox WHERE session_id=?", (session_id,)).fetchone()[0]
            cx.execute("INSERT INTO sync_mailbox(session_id,request_id,input_text,sequence,authority_epoch,status,lease_owner,created_at) VALUES(?,?,?,?,?,?,?,?)", (session_id, request_id, input_text, sequence, authority_epoch, "queued", None, int(time.time())))
            cx.execute("COMMIT")
            return QueueReceipt(sequence, "queued")

    def pop(self, session_id: str) -> SessionCommand | None:
        with self._connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            active = cx.execute("SELECT 1 FROM sync_mailbox WHERE session_id=? AND status IN ('admitted','needs_attention') LIMIT 1", (session_id,)).fetchone()
            if active:
                cx.execute("COMMIT")
                return None
            authority = cx.execute("SELECT authority_epoch FROM sync_mailbox_authority WHERE session_id=?", (session_id,)).fetchone()
            if authority is None:
                cx.execute("COMMIT")
                return None
            row = cx.execute("SELECT session_id,request_id,input_text,sequence,authority_epoch FROM sync_mailbox WHERE session_id=? AND status='queued' AND authority_epoch=? ORDER BY sequence LIMIT 1", (session_id, authority[0])).fetchone()
            if not row:
                cx.execute("COMMIT")
                return None
            cx.execute("UPDATE sync_mailbox SET status='admitted',lease_owner=? WHERE session_id=? AND request_id=?", (self.process_owner, session_id, row[1]))
            cx.execute("COMMIT")
            return SessionCommand.create(row[0], row[1], row[2], row[3], row[4])

    def pending(self, session_id: str) -> list[SessionCommand]:
        with self._connect() as cx:
            rows = cx.execute("SELECT session_id,request_id,input_text,sequence,authority_epoch FROM sync_mailbox WHERE session_id=? AND status IN ('queued','admitted','needs_attention') ORDER BY sequence", (session_id,)).fetchall()
        return [SessionCommand.create(*row) for row in rows]

    def pending_sessions(self) -> list[dict[str, int | str]]:
        """List sessions with durable work requiring host attention."""
        with self._connect() as cx:
            rows = cx.execute(
                "SELECT session_id,COUNT(*) AS pending_count,"
                "SUM(CASE WHEN status='needs_attention' THEN 1 ELSE 0 END) AS attention_count "
                "FROM sync_mailbox WHERE status IN ('queued','admitted','needs_attention') "
                "GROUP BY session_id ORDER BY MIN(sequence)"
            ).fetchall()
        return [dict(row) for row in rows]

    def complete(self, session_id: str, request_id: str) -> bool:
        with self._connect() as cx:
            result = cx.execute("UPDATE sync_mailbox SET status='completed',lease_owner=NULL WHERE session_id=? AND request_id=? AND status='admitted' AND lease_owner=?", (session_id, request_id, self.process_owner))
        return result.rowcount == 1

    def fail(self, session_id: str, request_id: str) -> bool:
        with self._connect() as cx:
            result = cx.execute("UPDATE sync_mailbox SET status='failed',lease_owner=NULL WHERE session_id=? AND request_id=? AND status='admitted' AND lease_owner=?", (session_id, request_id, self.process_owner))
        return result.rowcount == 1

    def status(self, session_id: str, request_id: str) -> str | None:
        with self._connect() as cx:
            row = cx.execute("SELECT status FROM sync_mailbox WHERE session_id=? AND request_id=?", (session_id, request_id)).fetchone()
        return str(row[0]) if row else None

    def compact(self, session_id: str, keep_completed: int = 1000) -> int:
        """Drop terminal delivery rows after their result is durably projected."""
        if type(keep_completed) is not int or keep_completed < 0:
            raise ValueError("keep_completed must be non-negative")
        with self._connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            rows = cx.execute(
                "SELECT request_id FROM sync_mailbox WHERE session_id=? "
                "AND status IN ('completed','failed','abandoned') "
                "ORDER BY sequence DESC LIMIT -1 OFFSET ?",
                (session_id, keep_completed),
            ).fetchall()
            if not rows:
                cx.execute("COMMIT")
                return 0
            result = cx.executemany(
                "DELETE FROM sync_mailbox WHERE session_id=? AND request_id=? "
                "AND status IN ('completed','failed','abandoned')",
                ((session_id, row[0]) for row in rows),
            )
            cx.execute("COMMIT")
            return result.rowcount

    def discard_pending(self, session_id: str) -> int:
        with self._connect() as cx:
            result = cx.execute("UPDATE sync_mailbox SET status='abandoned',lease_owner=NULL WHERE session_id=? AND status IN ('queued','admitted','needs_attention')", (session_id,))
        return result.rowcount

    def recover(self, session_id: str, mode: str) -> int:
        if mode not in {"resume", "abandon"}:
            raise ValueError("recovery mode must be resume or abandon")
        with self._connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            authority = cx.execute("SELECT authority_epoch FROM sync_mailbox_authority WHERE session_id=?", (session_id,)).fetchone()
            if mode == "resume" and authority is not None:
                result = cx.execute("UPDATE sync_mailbox SET status='queued',authority_epoch=?,lease_owner=NULL WHERE session_id=? AND status IN ('admitted','needs_attention')", (authority[0], session_id))
            else:
                result = cx.execute("UPDATE sync_mailbox SET status='abandoned',lease_owner=NULL WHERE session_id=? AND status IN ('admitted','needs_attention')", (session_id,))
            cx.execute("COMMIT")
        return result.rowcount

    def rotate_authority(self, session_id: str, new_epoch: int) -> int:
        if not isinstance(new_epoch, int) or new_epoch < 1:
            raise ValueError("authority epoch must be positive")
        now = int(time.time())
        with self._connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            authority = cx.execute("SELECT authority_epoch FROM sync_mailbox_authority WHERE session_id=?", (session_id,)).fetchone()
            if authority is not None and new_epoch <= int(authority[0]):
                cx.execute("ROLLBACK")
                raise ValueError("authority epoch must increase")
            if authority is None:
                cx.execute("INSERT INTO sync_mailbox_authority(session_id,authority_epoch,updated_at) VALUES(?,?,?)", (session_id, new_epoch, now))
            else:
                cx.execute("UPDATE sync_mailbox_authority SET authority_epoch=?,updated_at=? WHERE session_id=?", (new_epoch, now, session_id))
            attention = cx.execute("UPDATE sync_mailbox SET status='needs_attention',lease_owner=NULL WHERE session_id=? AND status='admitted'", (session_id,)).rowcount
            queued = cx.execute("UPDATE sync_mailbox SET authority_epoch=? WHERE session_id=? AND status='queued'", (new_epoch, session_id)).rowcount
            cx.execute("COMMIT")
        return attention + queued

    def _connect(self) -> sqlite3.Connection:
        cx = sqlite3.connect(self.database, isolation_level=None)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA journal_mode=WAL")
        cx.execute("PRAGMA synchronous=FULL")
        cx.execute("PRAGMA busy_timeout=2000")
        return cx
