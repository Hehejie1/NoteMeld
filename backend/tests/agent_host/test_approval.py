from __future__ import annotations

import pytest

from app.agent_host.approval import ApprovalManager


@pytest.mark.asyncio
async def test_approval_timeout_denies():
    manager = ApprovalManager()
    pending = manager.request("t1", {"operation": "write"})
    assert await manager.wait(pending, timeout=0.01) is False
