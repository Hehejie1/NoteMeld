from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ApprovalRequest:
    turn_id: str
    payload: dict[str, Any]
    future: asyncio.Future[bool] = field(default_factory=lambda: asyncio.get_running_loop().create_future())


class ApprovalManager:
    def __init__(self) -> None:
        self._pending: dict[str, ApprovalRequest] = {}

    def request(self, turn_id: str, payload: dict[str, Any]) -> ApprovalRequest:
        request = ApprovalRequest(turn_id, dict(payload))
        self._pending[turn_id] = request
        return request

    def resolve(self, turn_id: str, approved: bool) -> bool:
        request = self._pending.pop(turn_id, None)
        if request is None or request.future.done():
            return False
        request.future.set_result(bool(approved))
        return True

    async def wait(self, request: ApprovalRequest, *, timeout: float = 30.0) -> bool:
        try:
            return await asyncio.wait_for(request.future, timeout)
        except asyncio.TimeoutError:
            if not request.future.done():
                request.future.set_result(False)
            self._pending.pop(request.turn_id, None)
            return False

