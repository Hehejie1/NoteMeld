import asyncio
import os

import pytest

from cloud.relay import RedisRelayBroker


class _Peer:
    def __init__(self):
        self.messages: list[str] = []

    async def send_text(self, message: str):
        self.messages.append(message)


def test_redis_relay_delivers_between_worker_brokers():
    asyncio.run(_run_redis_relay_test())


async def _run_redis_relay_test():
    url = os.getenv("NOTEMELD_CLOUD_RELAY_TEST_URL")
    if not url:
        pytest.skip("Redis relay integration URL is not configured")
    left = RedisRelayBroker(url, online_ttl_seconds=10, key_prefix="notemeld-test-relay")
    right = RedisRelayBroker(url, online_ttl_seconds=10, key_prefix="notemeld-test-relay")
    sender, recipient = _Peer(), _Peer()
    try:
        await left.register("session", "sender", sender)
        await right.register("session", "recipient", recipient)
        assert await left.deliver("session", "recipient", "encrypted-frame", sender)
        assert recipient.messages == ["encrypted-frame"]
    finally:
        await asyncio.gather(left.close(), right.close())
