from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, AsyncIterator

from app.services import agent_store


class EventBroker:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    async def publish(self, turn_id: str, event: dict[str, Any]) -> None:
        agent_store.append_event(turn_id, event, sequence=event.get("sequence"), event_type=event.get("type"))
        for queue in tuple(self._queues.get(turn_id, ())):
            await queue.put(event)

    async def subscribe(self, turn_id: str, *, after_sequence: int = -1) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues[turn_id].add(queue)
        try:
            for event in agent_store.list_events(turn_id):
                if int(event.get("sequence", -1)) > after_sequence:
                    after_sequence = int(event["sequence"])
                    yield event
            while True:
                event = await queue.get()
                sequence = int(event.get("sequence", -1))
                if sequence <= after_sequence:
                    continue
                after_sequence = sequence
                yield event
        finally:
            self._queues[turn_id].discard(queue)

