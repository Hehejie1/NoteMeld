"""Ephemeral relay broker abstraction for encrypted frames."""
from __future__ import annotations

from typing import Any, Protocol


class RelayBroker(Protocol):
    def register(self, session_id: str, device_id: str, peer: Any) -> Any: ...
    def unregister(self, session_id: str, device_id: str, peer: Any) -> None: ...
    def peer(self, session_id: str, device_id: str) -> Any | None: ...
    def empty(self, session_id: str) -> bool: ...


class InMemoryRelayBroker:
    """Single-process broker; production deployments may replace this with pub/sub."""

    def __init__(self) -> None:
        self._peers: dict[str, dict[str, Any]] = {}

    def register(self, session_id: str, device_id: str, peer: Any) -> Any | None:
        peers = self._peers.setdefault(session_id, {})
        previous = peers.get(device_id)
        peers[device_id] = peer
        return previous

    def unregister(self, session_id: str, device_id: str, peer: Any) -> None:
        peers = self._peers.get(session_id)
        if peers is not None and peers.get(device_id) is peer:
            peers.pop(device_id, None)
            if not peers:
                self._peers.pop(session_id, None)

    def peer(self, session_id: str, device_id: str) -> Any | None:
        return self._peers.get(session_id, {}).get(device_id)

    def empty(self, session_id: str) -> bool:
        return not self._peers.get(session_id)
