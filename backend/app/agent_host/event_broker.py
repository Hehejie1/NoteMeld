from __future__ import annotations

import asyncio
import threading
from typing import Any, AsyncIterator
from collections import defaultdict
from uuid import uuid4

from app.services import agent_store


class EventBroker:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._lock = threading.Lock()
        self._poll_seconds = 0.1

    @staticmethod
    def _normalize_payload(payload: Any) -> Any:
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            return payload
        return payload

    @staticmethod
    def _to_event_record(raw_event: dict[str, Any]) -> dict[str, Any]:
        event_payload = raw_event.get("payload_json", raw_event.get("payload"))
        event_type = raw_event.get("type") or raw_event.get("event_type") or "agent.event"
        payload = EventBroker._normalize_payload(event_payload)
        if isinstance(payload, dict) and payload.get("type") == event_type and "payload" in payload:
            nested_payload = payload.get("payload")
            if nested_payload is not None:
                payload = nested_payload
        return {
            "event_id": str(raw_event.get("event_id") or uuid4()),
            "turn_id": str(raw_event.get("turn_id") or ""),
            "sequence": raw_event.get("sequence", -1),
            "schema_version": str(event_payload.get("schema_version") if isinstance(event_payload, dict) else "1") if isinstance(event_payload, dict) and event_payload.get("schema_version") is not None else "1",
            "type": str(event_type),
            "payload": payload,
        }

    def _publish_to_subscribers(self, turn_id: str, event: dict[str, Any], *, sequence: int | None = None) -> None:
        payload = self._normalize_payload(event.get("payload"))
        if isinstance(payload, dict) and payload.get("schema_version") is not None and "payload" in payload and "type" in payload:
            event_type = payload.get("type")
            payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        else:
            event_type = event.get("type") or event.get("event_type") or "agent.event"
        record = {
            "event_id": str(event.get("event_id") or uuid4()),
            "turn_id": str(event.get("turn_id") or turn_id),
            "sequence": sequence if sequence is not None else int(event.get("sequence", -1)),
            "schema_version": str(payload.get("schema_version")) if isinstance(payload, dict) and payload.get("schema_version") is not None else "1",
            "type": str(event_type),
            "payload": payload,
        }
        for queue in tuple(self._with_lock(self._queues.get(turn_id, ())):
            queue.put_nowait(record)

    async def publish(self, turn_id: str, event: dict[str, Any]) -> None:
        self._publish_to_subscribers(
            turn_id,
            event,
            sequence=int(event.get("sequence", -1)),
        )

    def publish_sync(self, turn_id: str, event: dict[str, Any]) -> None:
        """Publish from sync call sites (for worker threads).

        Native executor callbacks happen on a background thread. Sync publishing
        avoids creating throwaway event loops and avoids silently dropping
        coroutine handles when callers forget to await.
        """
        self._publish_to_subscribers(
            turn_id,
            event,
            sequence=int(event.get("sequence", -1)),
        )

    async def _drain_turn_events(self, turn_id: str, after_sequence: int) -> list[dict[str, Any]]:
        events = []
        for event in agent_store.list_events(turn_id):
            if int(event.get("sequence", -1)) > after_sequence:
                events.append(self._to_event_record(event))
        events.sort(key=lambda item: int(item.get("sequence", -1)))
        return events

    def _with_lock(self, queues: set[asyncio.Queue[dict[str, Any]]]) -> tuple[asyncio.Queue[dict[str, Any]], ...]:
        if not queues:
            return ()
        with self._lock:
            return tuple(queues)

    async def subscribe(self, turn_id: str, *, after_sequence: int = -1) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        with self._lock:
            self._queues[turn_id].add(queue)
        try:
            while True:
                replayed = await self._drain_turn_events(turn_id, after_sequence)
                for event in replayed:
                    sequence = int(event["sequence"])
                    after_sequence = sequence
                    yield event
                if not replayed:
                    turn = agent_store.get_turn(turn_id)
                    if turn is not None and str(turn.get("status")) in {"succeeded", "failed", "interrupted", "cancelled"}:
                        return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=self._poll_seconds)
                except asyncio.TimeoutError:
                    continue
                event = self._to_event_record(event)
                sequence = int(event.get("sequence", -1))
                if sequence <= after_sequence:
                    continue
                after_sequence = sequence
                yield event
        finally:
            with self._lock:
                self._queues[turn_id].discard(queue)
