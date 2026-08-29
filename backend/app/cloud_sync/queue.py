from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import sqlite3
from pathlib import Path
import time
from threading import Lock

from .protocol import SessionCommand


@dataclass(frozen=True)
class QueueReceipt:
    sequence: int
    status: str


class SessionMailbox:
    """Process-local queue used by a device Host until durable ledger wiring lands."""

    def __init__(self, max_size: int = 1000):
        self._items: deque[SessionCommand] = deque()
        self._next_sequence = 1
        self._max_size = max_size
        self._seen: dict[str, SessionCommand] = {}
        self._lock = Lock()

    def enqueue(self, session_id: str, request_id: str, input_text: str, authority_epoch: int = 0) -> QueueReceipt:
        with self._lock:
            existing = self._seen.get(request_id)
            if existing:
                if existing.payload_hash != SessionCommand.create(session_id, request_id, input_text, existing.sequence, authority_epoch).payload_hash:
                    raise ValueError("payload conflict")
                return QueueReceipt(existing.sequence, "duplicate")
            if len(self._items) >= self._max_size:
                raise OverflowError("session queue is full")
            command = SessionCommand.create(session_id, request_id, input_text, self._next_sequence, authority_epoch)
            self._next_sequence += 1
            self._seen[request_id] = command
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

    def __init__(self, database: Path, max_size: int = 1000):
        self.database = database
        self.max_size = max_size
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as cx:
            cx.execute("CREATE TABLE IF NOT EXISTS sync_mailbox (session_id TEXT NOT NULL, request_id TEXT NOT NULL, input_text TEXT NOT NULL, sequence INTEGER NOT NULL, authority_epoch INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'queued', created_at INTEGER NOT NULL, PRIMARY KEY(session_id, request_id), UNIQUE(session_id, sequence))")

    def enqueue(self, session_id: str, request_id: str, input_text: str, authority_epoch: int = 0) -> QueueReceipt:
        with self._connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            existing = cx.execute("SELECT input_text,sequence FROM sync_mailbox WHERE session_id=? AND request_id=?", (session_id, request_id)).fetchone()
            if existing:
                if existing[0] != input_text:
                    cx.execute("ROLLBACK")
                    raise ValueError("payload conflict")
                cx.execute("COMMIT")
                return QueueReceipt(existing[1], "duplicate")
            count = cx.execute("SELECT COUNT(*) FROM sync_mailbox WHERE session_id=? AND status IN ('queued','admitted')", (session_id,)).fetchone()[0]
            if count >= self.max_size:
                cx.execute("ROLLBACK")
                raise OverflowError("session queue is full")
            sequence = cx.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM sync_mailbox WHERE session_id=?", (session_id,)).fetchone()[0]
            cx.execute("INSERT INTO sync_mailbox VALUES(?,?,?,?,?,?,?)", (session_id, request_id, input_text, sequence, authority_epoch, "queued", int(time.time())))
            cx.execute("COMMIT")
            return QueueReceipt(sequence, "queued")

    def pop(self, session_id: str) -> SessionCommand | None:
        with self._connect() as cx:
            cx.execute("BEGIN IMMEDIATE")
            row = cx.execute("SELECT session_id,request_id,input_text,sequence,authority_epoch FROM sync_mailbox WHERE session_id=? AND status='queued' ORDER BY sequence LIMIT 1", (session_id,)).fetchone()
            if not row:
                cx.execute("COMMIT")
                return None
            cx.execute("UPDATE sync_mailbox SET status='admitted' WHERE session_id=? AND request_id=?", (session_id, row[1]))
            cx.execute("COMMIT")
            return SessionCommand.create(row[0], row[1], row[2], row[3], row[4])

    def pending(self, session_id: str) -> list[SessionCommand]:
        with self._connect() as cx:
            rows = cx.execute("SELECT session_id,request_id,input_text,sequence,authority_epoch FROM sync_mailbox WHERE session_id=? AND status IN ('queued','admitted') ORDER BY sequence", (session_id,)).fetchall()
        return [SessionCommand.create(*row) for row in rows]

    def complete(self, session_id: str, request_id: str) -> None:
        with self._connect() as cx:
            cx.execute("UPDATE sync_mailbox SET status='completed' WHERE session_id=? AND request_id=? AND status='admitted'", (session_id, request_id))

    def discard_pending(self, session_id: str) -> int:
        with self._connect() as cx:
            result = cx.execute("UPDATE sync_mailbox SET status='abandoned' WHERE session_id=? AND status IN ('queued','admitted')", (session_id,))
        return result.rowcount

    def recover(self, session_id: str, mode: str) -> int:
        if mode not in {"resume", "abandon"}:
            raise ValueError("recovery mode must be resume or abandon")
        target = "queued" if mode == "resume" else "abandoned"
        with self._connect() as cx:
            result = cx.execute("UPDATE sync_mailbox SET status=? WHERE session_id=? AND status='admitted'", (target, session_id))
        return result.rowcount

    def _connect(self) -> sqlite3.Connection:
        cx = sqlite3.connect(self.database, isolation_level=None)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA busy_timeout=2000")
        return cx
