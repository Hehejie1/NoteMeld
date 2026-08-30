"""Ephemeral relay broker abstraction for encrypted frames.

The relay deliberately treats Redis as a transient transport only.  It never
uses Redis keys, streams, or lists to persist the application payload; frames
are published and removed by the broker's Pub/Sub path.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import threading
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

    async def close(self) -> None:
        return None

    async def deliver(self, session_id: str, recipient_device_id: str, message: str, sender: Any) -> bool:
        peer = self.peer(session_id, recipient_device_id)
        if peer is None or peer is sender:
            return False
        try:
            await peer.send_text(message)
        except Exception:  # noqa: BLE001 - disconnected peers are offline
            self.unregister(session_id, recipient_device_id, peer)
            return False
        return True


class RedisRelayBroker:
    """Multi-worker transient relay backed by Redis Pub/Sub.

    A local websocket is registered in the process-local map.  Other workers
    publish a frame to the session channel and wait briefly for a delivery ack.
    Redis keys only represent online presence with a short TTL; no frame body
    is stored in a Redis data structure.
    """

    def __init__(self, url: str, *, online_ttl_seconds: int = 90, key_prefix: str = "notemeld:relay") -> None:
        try:
            import redis.asyncio as redis
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("redis relay requires the redis package") from exc
        self._redis = redis.from_url(url, decode_responses=True)
        self._ttl = max(5, int(online_ttl_seconds))
        self._prefix = key_prefix
        self._peers: dict[str, dict[str, Any]] = {}
        self._connection_ids: dict[tuple[str, str], str] = {}
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self._lock = threading.RLock()
        self._listener_task: asyncio.Task[None] | None = None
        self._closed = False

    def _channel(self, session_id: str) -> str:
        return f"{self._prefix}:channel:{session_id}"

    def _presence_key(self, session_id: str, device_id: str) -> str:
        return f"{self._prefix}:online:{session_id}:{device_id}"

    async def _ensure_listener(self) -> None:
        if self._listener_task is None:
            self._listener_task = asyncio.create_task(self._listen())

    async def register(self, session_id: str, device_id: str, peer: Any) -> Any | None:
        await self._ensure_listener()
        with self._lock:
            peers = self._peers.setdefault(session_id, {})
            previous = peers.get(device_id)
            peers[device_id] = peer
            self._connection_ids[(session_id, device_id)] = secrets.token_urlsafe(12)
            connection_id = self._connection_ids[(session_id, device_id)]
        await self._redis.set(self._presence_key(session_id, device_id), connection_id, ex=self._ttl)
        return previous

    async def unregister(self, session_id: str, device_id: str, peer: Any) -> None:
        with self._lock:
            peers = self._peers.get(session_id)
            if peers is None or peers.get(device_id) is not peer:
                return
            peers.pop(device_id, None)
            connection_id = self._connection_ids.pop((session_id, device_id), None)
            if not peers:
                self._peers.pop(session_id, None)
        if connection_id is not None:
            # The random value prevents a replaced connection from deleting
            # the newer connection's presence marker.
            script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
            await self._redis.eval(script, 1, self._presence_key(session_id, device_id), connection_id)

    def peer(self, session_id: str, device_id: str) -> Any | None:
        with self._lock:
            return self._peers.get(session_id, {}).get(device_id)

    def empty(self, session_id: str) -> bool:
        with self._lock:
            return not self._peers.get(session_id)

    async def deliver(self, session_id: str, recipient_device_id: str, message: str, sender: Any) -> bool:
        local = self.peer(session_id, recipient_device_id)
        if local is not None:
            try:
                await local.send_text(message)
            except Exception:  # noqa: BLE001
                await self.unregister(session_id, recipient_device_id, local)
                return False
            return True
        if not await self._redis.exists(self._presence_key(session_id, recipient_device_id)):
            return False
        delivery_id = secrets.token_urlsafe(16)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending[delivery_id] = future
        try:
            await self._redis.publish(
                self._channel(session_id),
                json.dumps({"kind": "frame", "delivery_id": delivery_id, "recipient_device_id": recipient_device_id, "message": message}, separators=(",", ":")),
            )
            try:
                return await asyncio.wait_for(future, timeout=2.0)
            except asyncio.TimeoutError:
                return False
        finally:
            self._pending.pop(delivery_id, None)

    async def _listen(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe(f"{self._prefix}:channel:*")
        try:
            while not self._closed:
                item = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not item or item.get("type") not in {"pmessage", "message"}:
                    await asyncio.sleep(0)
                    continue
                try:
                    payload = json.loads(item["data"])
                except (TypeError, json.JSONDecodeError):
                    continue
                if payload.get("kind") == "ack":
                    future = self._pending.get(payload.get("delivery_id"))
                    if future is not None and not future.done():
                        future.set_result(bool(payload.get("delivered")))
                    continue
                if payload.get("kind") != "frame":
                    continue
                session_id = str(item.get("channel", "")).rsplit(":", 1)[-1]
                recipient = payload.get("recipient_device_id")
                peer = self.peer(session_id, recipient)
                delivered = False
                if peer is not None:
                    try:
                        await peer.send_text(payload["message"])
                        delivered = True
                    except Exception:  # noqa: BLE001
                        await self.unregister(session_id, recipient, peer)
                await self._redis.publish(
                    self._channel(session_id),
                    json.dumps({"kind": "ack", "delivery_id": payload.get("delivery_id"), "delivered": delivered}, separators=(",", ":")),
                )
        finally:
            await pubsub.close()

    async def close(self) -> None:
        self._closed = True
        if self._listener_task is not None:
            self._listener_task.cancel()
            await asyncio.gather(self._listener_task, return_exceptions=True)
        await self._redis.aclose()
