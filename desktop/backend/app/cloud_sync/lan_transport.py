"""Authenticated direct-LAN WebSocket transport for a configured local host."""
from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections import deque
from threading import Lock
from typing import Any, Awaitable, Callable

from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .e2ee import SessionCipher
from .lan_auth import LanAuthError, LanPeerAuthenticator, LanPeerAuthorization
from .protocol import RemoteFrame
from .remote_host import RemoteHostAuthority, RemoteHostError


LAN_PROTOCOL_VERSION = "notemeld.lan.v1"


class LanDirectFrameError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


FrameHandler = Callable[
    [RemoteFrame, LanPeerAuthorization],
    dict[str, Any] | RemoteFrame | Awaitable[dict[str, Any] | RemoteFrame],
]
CipherHandshake = Callable[[WebSocket, LanPeerAuthorization], SessionCipher | Awaitable[SessionCipher]]


class EncryptedRemoteHostHandler:
    """AEAD-verify a direct frame and commit it through RemoteHostAuthority."""

    def __init__(
        self,
        authority: RemoteHostAuthority,
        cipher_resolver: Callable[[LanPeerAuthorization], SessionCipher],
    ):
        self.authority = authority
        self.cipher_resolver = cipher_resolver

    def __call__(
        self,
        frame: RemoteFrame,
        authorization: LanPeerAuthorization,
    ) -> dict[str, Any]:
        try:
            cipher = self.cipher_resolver(authorization)
            if not isinstance(cipher, SessionCipher):
                raise TypeError("cipher resolver returned an invalid value")
        except Exception:
            raise LanDirectFrameError("host_unavailable") from None
        try:
            plaintext = cipher.decrypt(
                frame.sequence,
                frame.nonce,
                frame.ciphertext,
                frame.associated_data(),
            )
        except (InvalidTag, ValueError):
            raise LanDirectFrameError("invalid_ciphertext") from None
        try:
            receipt = self.authority.receive_command(frame, plaintext)
        except RemoteHostError as exc:
            raise LanDirectFrameError(exc.code) from None
        except Exception:
            raise LanDirectFrameError("host_unavailable") from None
        return {
            "type": "received",
            "frame_id": receipt.frame_id,
            "queue_sequence": receipt.queue_sequence,
            "queue_status": receipt.queue_status,
        }


class LanDirectService:
    def __init__(
        self,
        authenticator: LanPeerAuthenticator,
        frame_handler: FrameHandler,
        *,
        handshake_timeout_seconds: float = 10.0,
        max_frame_bytes: int = 256 * 1024,
        max_frames_per_minute: int = 120,
        peer_address: Callable[[WebSocket], str] | None = None,
        cipher_handshake: CipherHandshake | None = None,
        clock: Callable[[], float] = time.time,
    ):
        if handshake_timeout_seconds <= 0 or handshake_timeout_seconds > 60:
            raise ValueError("invalid LAN handshake timeout")
        if max_frame_bytes < 1024 or max_frames_per_minute < 1:
            raise ValueError("invalid LAN transport limit")
        self.authenticator = authenticator
        self.frame_handler = frame_handler
        self.handshake_timeout_seconds = handshake_timeout_seconds
        self.max_frame_bytes = max_frame_bytes
        self.max_frames_per_minute = max_frames_per_minute
        self._peer_address = peer_address or _websocket_peer_address
        self._cipher_handshake = cipher_handshake
        self._clock = clock
        self._connections: dict[tuple[str, str], tuple[WebSocket, asyncio.AbstractEventLoop]] = {}
        self._connections_lock = Lock()

    async def handle(self, websocket: WebSocket, session_id: str) -> None:
        offered = {
            item.strip()
            for item in websocket.headers.get("sec-websocket-protocol", "").split(",")
            if item.strip()
        }
        selected_subprotocol = LAN_PROTOCOL_VERSION if LAN_PROTOCOL_VERSION in offered else None
        await websocket.accept(subprotocol=selected_subprotocol)
        try:
            peer = self._peer_address(websocket)
            hello = await self._receive_object(
                websocket, timeout=self.handshake_timeout_seconds
            )
            if set(hello) != {"type", "protocol_version", "controller_device_id"}:
                raise LanAuthError("invalid_hello")
            if hello["type"] != "hello" or hello["protocol_version"] != LAN_PROTOCOL_VERSION:
                raise LanAuthError("invalid_hello")
            challenge = self.authenticator.issue(
                session_id, hello["controller_device_id"], peer
            )
            await websocket.send_json(
                {
                    "type": "challenge",
                    "protocol_version": LAN_PROTOCOL_VERSION,
                    "challenge_id": challenge.challenge_id,
                    "challenge": challenge.challenge,
                    "expires_at": challenge.expires_at,
                    "host_device_id": self.authenticator.host_device_id,
                }
            )
            proof = await self._receive_object(
                websocket, timeout=self.handshake_timeout_seconds
            )
            if set(proof) != {"type", "challenge_id", "challenge", "signature"}:
                raise LanAuthError("invalid_proof")
            if proof["type"] != "proof":
                raise LanAuthError("invalid_proof")
            authorization = self.authenticator.verify(
                proof["challenge_id"], proof["challenge"], proof["signature"], peer
            )
            await websocket.send_json(
                {
                    "type": "authorized",
                    "protocol_version": LAN_PROTOCOL_VERSION,
                    "session_id": authorization.session_id,
                    "host_device_id": authorization.host_device_id,
                    "authority_epoch": authorization.authority_epoch,
                    "valid_until": authorization.valid_until,
                }
            )
            if self._cipher_handshake is not None:
                cipher = self._cipher_handshake(websocket, authorization)
                if inspect.isawaitable(cipher):
                    await cipher
            with self._connections_lock:
                self._connections[(authorization.session_id, authorization.controller_device_id)] = (
                    websocket,
                    asyncio.get_running_loop(),
                )
            await self._serve_frames(websocket, authorization)
        except LanAuthError as exc:
            await _close_safely(websocket, 4403, exc.code)
        except (TypeError, ValueError):
            await _close_safely(websocket, 4403, "E2EE handshake rejected")
        except (asyncio.TimeoutError, WebSocketDisconnect):
            await _close_safely(websocket, 4408, "LAN handshake or authorization expired")
        finally:
            with self._connections_lock:
                current = self._connections.get((authorization.session_id, authorization.controller_device_id)) if 'authorization' in locals() else None
                if current is not None and current[0] is websocket:
                    self._connections.pop((authorization.session_id, authorization.controller_device_id), None)

    def send_event_nowait(self, session_id: str, controller_device_id: str, frame: RemoteFrame) -> bool:
        """Schedule an encrypted event on the active LAN socket, if present."""
        with self._connections_lock:
            connection = self._connections.get((session_id, controller_device_id))
        if connection is None:
            return False
        websocket, loop = connection
        try:
            asyncio.run_coroutine_threadsafe(websocket.send_text(frame.to_json()), loop)
        except RuntimeError:
            return False
        return True

    async def _serve_frames(
        self,
        websocket: WebSocket,
        authorization: LanPeerAuthorization,
    ) -> None:
        frame_times: deque[int] = deque()
        last_sequence = 0
        while True:
            now = int(self._clock())
            remaining = authorization.valid_until - now
            if remaining <= 0:
                await _close_safely(websocket, 4408, "LAN authorization expired")
                return
            try:
                payload = await asyncio.wait_for(
                    websocket.receive_text(), timeout=float(remaining)
                )
            except asyncio.TimeoutError:
                await _close_safely(websocket, 4408, "LAN authorization expired")
                return
            if len(payload.encode("utf-8")) > self.max_frame_bytes:
                await websocket.send_json({"type": "rejected", "error": "frame_too_large"})
                continue
            now = int(self._clock())
            while frame_times and frame_times[0] <= now - 60:
                frame_times.popleft()
            if len(frame_times) >= self.max_frames_per_minute:
                await websocket.send_json(
                    {"type": "rejected", "error": "frame_rate_limited"}
                )
                continue
            frame_times.append(now)
            try:
                frame = RemoteFrame.from_json(payload)
                if (
                    frame.session_id != authorization.session_id
                    or frame.sender_device_id != authorization.controller_device_id
                    or frame.recipient_device_id != authorization.host_device_id
                    or frame.authority_epoch != authorization.authority_epoch
                    or frame.frame_type != "command"
                    or frame.sequence <= last_sequence
                    or "message.send" not in authorization.scopes
                ):
                    raise LanDirectFrameError("invalid_envelope")
                response = self.frame_handler(frame, authorization)
                if inspect.isawaitable(response):
                    response = await response
                await self._send_handler_response(websocket, response, frame, authorization)
                last_sequence = frame.sequence
            except LanDirectFrameError as exc:
                await websocket.send_json({"type": "rejected", "error": exc.code})
            except (TypeError, ValueError, json.JSONDecodeError):
                await websocket.send_json(
                    {"type": "rejected", "error": "invalid_envelope"}
                )
            except Exception:
                await websocket.send_json(
                    {"type": "failed", "error": "host_unavailable"}
                )

    async def _receive_object(
        self, websocket: WebSocket, *, timeout: float
    ) -> dict[str, Any]:
        payload = await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
        if len(payload.encode("utf-8")) > 16 * 1024:
            raise LanAuthError("handshake_too_large")
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise LanAuthError("invalid_handshake") from exc
        if not isinstance(value, dict):
            raise LanAuthError("invalid_handshake")
        return value

    async def _send_handler_response(
        self,
        websocket: WebSocket,
        response: dict[str, Any] | RemoteFrame,
        request_frame: RemoteFrame,
        authorization: LanPeerAuthorization,
    ) -> None:
        if isinstance(response, RemoteFrame):
            response.validate()
            if (
                response.session_id != authorization.session_id
                or response.sender_device_id != authorization.host_device_id
                or response.recipient_device_id != authorization.controller_device_id
                or response.authority_epoch != authorization.authority_epoch
                or response.frame_type not in {"receipt", "event"}
            ):
                raise LanDirectFrameError("invalid_host_response")
            await websocket.send_text(response.to_json())
            return
        allowed = {"type", "frame_id", "queue_sequence", "queue_status"}
        if (
            not isinstance(response, dict)
            or not set(response).issubset(allowed)
            or response.get("type") != "received"
            or response.get("frame_id") != request_frame.frame_id
            or type(response.get("queue_sequence", 0)) is not int
            or response.get("queue_sequence", 0) < 0
            or response.get("queue_status", "queued")
            not in {"queued", "duplicate", "admitted"}
        ):
            raise LanDirectFrameError("invalid_host_response")
        await websocket.send_json(response)


router = APIRouter()


def install_lan_direct_service(app: Any, service: LanDirectService) -> None:
    """Install a platform-configured service without exposing its token or keys."""
    if not isinstance(service, LanDirectService):
        raise TypeError("service must be a LanDirectService")
    app.state.lan_direct_service = service


@router.websocket("/v1/lan/connect/{session_id}")
async def lan_connect(websocket: WebSocket, session_id: str):
    service = getattr(websocket.app.state, "lan_direct_service", None)
    if not isinstance(service, LanDirectService):
        await websocket.close(code=1013, reason="LAN direct service is not configured")
        return
    await service.handle(websocket, session_id)


def _websocket_peer_address(websocket: WebSocket) -> str:
    if websocket.client is None or not websocket.client.host:
        raise LanAuthError("invalid_peer_address")
    return websocket.client.host


async def _close_safely(websocket: WebSocket, code: int, reason: str) -> None:
    try:
        await websocket.close(code=code, reason=reason[:123])
    except RuntimeError:
        pass
