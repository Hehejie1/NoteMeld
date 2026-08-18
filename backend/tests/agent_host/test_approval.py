from __future__ import annotations

import asyncio

from app.agent_host.approval import ApprovalManager


def test_approval_timeout_denies():
    async def exercise():
        manager = ApprovalManager()
        pending = manager.request("t1", {"operation": "write"})
        assert await manager.wait(pending, timeout=0.01) is False
    asyncio.run(exercise())
