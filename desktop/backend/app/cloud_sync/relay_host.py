"""Cloud Relay Host transport for already-provisioned E2EE sessions.

The relay is only a websocket transport. This adapter never sends plaintext
commands to it and deliberately requires the platform to provide a
SessionCipher before connecting.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, Awaitable, Callable
from urllib.parse import quote, urlencode, urlparse, urlunparse

from .e2ee import SessionCipher
from .protocol import RemoteFrame
from .lan_auth import LanPeerAuthorization


class RelayHostError(RuntimeError):
    pass


AuthorizeFrame = Callable[[RemoteFrame], LanPeerAuthorization | Awaitable[LanPeerAuthorization]]
FrameHandler = Callable[[RemoteFrame, LanPeerAuthorization], dict[str, Any] | Awaitable[dict[str, Any]]]
CipherResolver = Callable[[LanPeerAuthorization], SessionCipher]
HandshakeHandler = Callable[[RemoteFrame, LanPeerAuthorization], RemoteFrame | Awaitable[RemoteFrame]]


class RelayHostSession:
    """Serve one device-remote session over the cloud relay websocket."""

    def __init__(
        self,
        *,
        cloud_base_url: str,
        token: str,
        host_device_id: str,
        session_id: str,
        authorize_frame: AuthorizeFrame,
        frame_handler: FrameHandler,
        cipher_resolver: CipherResolver,
        handshake_handler: HandshakeHandler | None = None,
        max_frame_bytes: int = 256 * 1024,
        connector: Callable[..., Any] | None = None,
    ) -> None:
        if not token or not host_device_id or not session_id:
            raise ValueError("relay Host identity and token are required")
        if max_frame_bytes < 1024:
            raise ValueError("relay frame limit is too small")
        parsed = urlparse(cloud_base_url.rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("invalid cloud base URL")
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = f"{parsed.path.rstrip('/')}/v1/relay/connect/{quote(session_id, safe='')}"
        self.url = urlunparse((scheme, parsed.netloc, path, "", urlencode({"device_id": host_device_id}), ""))
        self.token = token
        self.host_device_id = host_device_id
        self.session_id = session_id
        self.authorize_frame = authorize_frame
        self.frame_handler = frame_handler
        self.cipher_resolver = cipher_resolver
        self.handshake_handler = handshake_handler
        self.max_frame_bytes = max_frame_bytes
        self._connector = connector
        self._stop = asyncio.Event()
        self._socket: Any | None = None

    async def stop(self) -> None:
        self._stop.set()
        socket = self._socket
        if socket is not None:
            await socket.close()

    async def run(self) -> None:
        connector = self._connector
        if connector is None:
            try:
                from websockets.client import connect
            except ImportError as exc:  # pragma: no cover - packaging guard
                raise RelayHostError("websockets dependency is required for Relay Host") from exc
            connector = connect
        socket = connector(
            self.url,
            additional_headers={"Authorization": f"Bearer {self.token}"},
            max_size=self.max_frame_bytes,
        )
        if inspect.isawaitable(socket):
            socket = await socket
        self._socket = socket
        try:
            async with socket:
                async for raw in socket:
                    if self._stop.is_set():
                        break
                    if not isinstance(raw, str) or len(raw.encode("utf-8")) > self.max_frame_bytes:
                        continue
                    await self._handle_message(socket, raw)
        finally:
            self._socket = None

    async def _handle_message(self, socket: Any, raw: str) -> None:
        try:
            frame = RemoteFrame.from_json(raw)
            if frame.session_id != self.session_id or frame.recipient_device_id != self.host_device_id or frame.frame_type not in {"command", "handshake"}:
                raise RelayHostError("invalid relay command envelope")
            authorization = self.authorize_frame(frame)
            if inspect.isawaitable(authorization):
                authorization = await authorization
            if frame.frame_type == "handshake":
                if self.handshake_handler is None:
                    raise RelayHostError("relay handshake is unavailable")
                response = self.handshake_handler(frame, authorization)
                if inspect.isawaitable(response):
                    response = await response
                if not isinstance(response, RemoteFrame) or response.frame_type != "handshake":
                    raise RelayHostError("invalid relay handshake response")
                response.validate()
                await socket.send(response.to_json())
                return
            cipher = self.cipher_resolver(authorization)
            if not isinstance(cipher, SessionCipher):
                raise RelayHostError("relay cipher is unavailable")
            response = self.frame_handler(frame, authorization)
            if inspect.isawaitable(response):
                response = await response
            if not isinstance(response, dict) or response.get("type") != "received":
                return
            sequence = cipher.last_sent_sequence + 1
            receipt = RemoteFrame(
                session_id=frame.session_id,
                sender_device_id=self.host_device_id,
                recipient_device_id=frame.sender_device_id,
                sequence=sequence,
                ciphertext="",
                frame_id=frame.frame_id,
                authority_epoch=frame.authority_epoch,
                frame_type="receipt",
                nonce="",
            )
            payload = json.dumps({**response, "status": "received"}, separators=(",", ":")).encode("utf-8")
            await socket.send(cipher.encrypt_frame(receipt, payload).to_json())
        except (TypeError, ValueError, RelayHostError):
            # The cloud relay will return its own rejected/failed status for
            # malformed envelopes; do not echo local exception details.
            return
