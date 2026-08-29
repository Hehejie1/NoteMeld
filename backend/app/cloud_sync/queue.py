from __future__ import annotations

from collections import deque
from dataclasses import dataclass
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
