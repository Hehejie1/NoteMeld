"""Dependency-injected local Host runtime for LAN/cloud remote sessions."""
from __future__ import annotations

from pathlib import Path
from threading import Lock
import time
import json
import uuid
import inspect
import base64
import os
from typing import Callable, Awaitable, Any

from fastapi import FastAPI

from .client import CloudClient
from .agent_consumer import RemoteAgentMailboxConsumer
from .e2ee import HandshakeEnvelope, SessionCipher, create_handshake_envelope, derive_handshake_session_key, generate_ephemeral, verify_handshake_envelope, _unb64, _b64
from .e2ee_handshake import accept_handshake
from .lan_auth import LanPeerAuthorization
from .lan_transport import EncryptedRemoteHostHandler, LanDirectService, install_lan_direct_service
from .protocol import RemoteFrame
from .relay_host import RelayHostSession
from .queue import DurableSessionMailbox
from .remote_host import RemoteHostAuthority


class CloudSyncHostRuntime:
    """Assemble the local remote Host without duplicating the Agent loop.

    The platform owns construction of ``CloudClient`` and its encrypted token
    store, plus the session-key resolver. This class owns only routing,
    authorization assertions, durable command admission and recovery APIs.
    """

    def __init__(
        self,
        *,
        cloud_client: CloudClient,
        host_device_id: str,
        mailbox_path: Path,
        cipher_resolver: Callable[[LanPeerAuthorization], SessionCipher],
        mailbox_max_size: int = 1000,
        authorization_refresh_seconds: float = 5.0,
        cipher_handshake: Callable[[object, LanPeerAuthorization], SessionCipher] | None = None,
        host_signing_private: bytes | None = None,
        host_signing_public: bytes | None = None,
        agent_runner: Callable[[object, Callable[[dict], None]], None] | None = None,
        remote_event_sink: Callable[[object, dict], None] | None = None,
        agent_poll_interval_seconds: float = 0.25,
    ):
        if cloud_client.device_id != host_device_id:
            raise ValueError("CloudClient must be bound to the host device")
        if authorization_refresh_seconds <= 0 or authorization_refresh_seconds > 60:
            raise ValueError("authorization refresh interval must be between 0 and 60 seconds")
        self.cloud_client = cloud_client
        self.host_device_id = host_device_id
        self.mailbox = DurableSessionMailbox(mailbox_path, max_size=mailbox_max_size)
        self._cipher_resolver = cipher_resolver
        if (host_signing_private is None) != (host_signing_public is None):
            raise ValueError("host signing key pair must be provided together")
        if cipher_handshake is not None and host_signing_private is not None:
            raise ValueError("provide either cipher_handshake or host signing keys")
        self._cipher_handshake = cipher_handshake
        self._host_signing_private = host_signing_private
        self._host_signing_public = host_signing_public
        self._authorizations: dict[tuple[str, str], LanPeerAuthorization] = {}
        self._authorization_checked_at: dict[tuple[str, str], float] = {}
        self._authorization_refresh_seconds = authorization_refresh_seconds
        self._authorities: dict[str, RemoteHostAuthority] = {}
        self._session_ciphers: dict[tuple[str, str], SessionCipher] = {}
        self._session_controllers: dict[str, str] = {}
        self._relay_sessions: dict[str, RelayHostSession] = {}
        self._relay_tasks: dict[str, Any] = {}
        self._relay_discovery_task: Any | None = None
        self._lock = Lock()
        self._closed = False
        from .lan_auth import LanPeerAuthenticator

        authenticator = LanPeerAuthenticator(
            host_device_id,
            self._authorize_lan_peer,
        )
        self.service = LanDirectService(
            authenticator,
            self._handle_frame,
            cipher_handshake=self._complete_cipher_handshake
            if cipher_handshake is not None or host_signing_private is not None
            else None,
        )
        self._agent_consumer = RemoteAgentMailboxConsumer(
            self._authority_for,
            pending_sessions=self.pending_sessions,
            runner=agent_runner,
            event_sink=remote_event_sink or self._emit_remote_event,
            poll_interval_seconds=agent_poll_interval_seconds,
        )

    def install(self, app: FastAPI) -> None:
        install_lan_direct_service(app, self.service)
        self._agent_consumer.start()
        # A controller may create a device_remote session from mobile while
        # this desktop is already online. Discover those authorized sessions
        # so the host relay is started without requiring a desktop click.
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and self._relay_discovery_task is None:
            self._relay_discovery_task = loop.create_task(self._discover_relay_sessions(), name="notemeld-relay-discovery")

    def install_session_cipher(self, session_id: str, controller_device_id: str, cipher: SessionCipher) -> None:
        """Install a platform-derived cipher for one remote session.

        The key itself never leaves the platform adapter. Keeping the cipher
        instance here preserves monotonic send/receive replay cursors across
        frames; callers must explicitly replace or remove it on re-key/revoke.
        """
        if not session_id or not controller_device_id or not isinstance(cipher, SessionCipher):
            raise ValueError("session and a valid cipher are required")
        with self._lock:
            if self._closed:
                raise RuntimeError("cloud sync runtime is closed")
            self._session_ciphers[(session_id, controller_device_id)] = cipher

    def remove_session_cipher(self, session_id: str, controller_device_id: str) -> bool:
        with self._lock:
            return self._session_ciphers.pop((session_id, controller_device_id), None) is not None

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._session_ciphers.clear()
            self._session_controllers.clear()
            relay_tasks = list(self._relay_tasks.values())
            self._relay_tasks.clear()
            self._relay_sessions.clear()
            discovery_task = self._relay_discovery_task
            self._relay_discovery_task = None
        if discovery_task is not None:
            discovery_task.cancel()
        for task in relay_tasks:
            task.cancel()
        self._agent_consumer.stop()
        self.cloud_client.close()

    async def _discover_relay_sessions(self) -> None:
        """Keep relays aligned with Cloud grants for this host device."""
        import asyncio

        list_grants = getattr(self.cloud_client, "list_grants", None)
        list_sessions = getattr(self.cloud_client, "list_sessions", None)
        if not callable(list_grants) or not callable(list_sessions):
            return
        while not self._closed:
            try:
                grants, sessions = await asyncio.gather(
                    asyncio.to_thread(list_grants),
                    asyncio.to_thread(list_sessions, False),
                )
                eligible = {
                    str(grant["session_id"])
                    for grant in grants
                    if grant.get("session_id")
                    and grant.get("host_device_id") == self.host_device_id
                    and grant.get("revoked_at") is None
                }
                # Cloud grants are not currently session-bound, so intersect
                # with active device_remote sessions owned by this account.
                eligible.intersection_update(
                    str(session.get("id"))
                    for session in sessions
                    if session.get("kind") == "device_remote"
                    and session.get("status") not in {"archived", "deleted"}
                )
                # The Cloud API exposes grants by device pair. If no session
                # id is present, a device-pair grant authorizes all active
                # remote sessions and each relay still performs frame-level
                # authorization before accepting traffic.
                pair_grants = {
                    grant for grant in grants
                    if grant.get("host_device_id") == self.host_device_id
                    and grant.get("revoked_at") is None
                }
                if pair_grants and not eligible:
                    eligible = {
                        str(session.get("id")) for session in sessions
                        if session.get("kind") == "device_remote"
                        and session.get("status") not in {"archived", "deleted"}
                    }
                for session_id in sorted(eligible):
                    await self.start_relay_session(session_id)
                running = set(self._relay_tasks)
                for session_id in sorted(running - eligible):
                    await self.stop_relay_session(session_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Cloud may be temporarily offline; the next cycle retries
                # without taking down the local Agent or LAN service.
                pass
            await asyncio.sleep(5)

    def heartbeat(self, lan_endpoints: list[str] | None = None) -> dict:
        """Refresh cloud presence and publish current LAN candidates."""
        return self.cloud_client.heartbeat(self.host_device_id, lan_endpoints)

    def relay_session(self, session_id: str) -> RelayHostSession:
        """Create a Relay Host transport for a session with an installed cipher.

        Starting/owning the async task remains a platform lifecycle decision;
        this method only wires Cloud auth, the canonical remote Host handler,
        and the injected cipher resolver together.
        """
        token = self.cloud_client.token
        if not isinstance(token, str) or not token:
            raise RuntimeError("Cloud device token is unavailable")

        def authorize(frame: RemoteFrame) -> LanPeerAuthorization:
            self._authorize_lan_peer(session_id, frame.sender_device_id, self.host_device_id)
            with self._lock:
                authorization = self._authorizations.get((session_id, frame.sender_device_id))
            if authorization is None or authorization.authority_epoch != frame.authority_epoch:
                raise PermissionError("remote relay authority is not current")
            return authorization

        return RelayHostSession(
            cloud_base_url=str(self.cloud_client.base_url),
            token=token,
            host_device_id=self.host_device_id,
            session_id=session_id,
            authorize_frame=authorize,
            frame_handler=self._handle_frame,
            cipher_resolver=self._cipher_for,
            handshake_handler=self._handle_relay_handshake,
        )

    def _handle_relay_handshake(self, frame: RemoteFrame, authorization: LanPeerAuthorization) -> RemoteFrame:
        """Complete the signed X25519 handshake inside an E2EE Relay frame."""
        if self._host_signing_private is None or self._host_signing_public is None:
            raise RuntimeError("host signing identity is unavailable")
        if frame.authority_epoch != authorization.authority_epoch:
            raise PermissionError("stale relay authority")
        try:
            encoded = frame.ciphertext.replace("-", "+").replace("_", "/") + "=" * ((4 - len(frame.ciphertext) % 4) % 4)
            peer = HandshakeEnvelope.from_dict(json.loads(base64.b64decode(encoded).decode("utf-8")))
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("invalid relay handshake payload") from exc
        if peer.session_id != authorization.session_id or peer.sender_device_id != authorization.controller_device_id or peer.recipient_device_id != authorization.host_device_id:
            raise ValueError("relay handshake endpoint mismatch")
        if not authorization.controller_public_key:
            raise ValueError("controller public key is required")
        verify_handshake_envelope(peer, _unb64(authorization.controller_public_key, expected_length=32))
        local_private, local_public = generate_ephemeral()
        local = create_handshake_envelope(self._host_signing_private, frame.session_id, self.host_device_id, frame.sender_device_id, local_public)
        cipher = SessionCipher(derive_handshake_session_key(local_private, local, peer))
        self.install_session_cipher(frame.session_id, frame.sender_device_id, cipher)
        payload = json.dumps(local.as_dict(), separators=(",", ":")).encode("utf-8")
        nonce = _b64(os.urandom(12))
        return RemoteFrame(
            session_id=frame.session_id,
            sender_device_id=self.host_device_id,
            recipient_device_id=frame.sender_device_id,
            sequence=1,
            ciphertext=_b64(payload),
            frame_id=frame.frame_id,
            authority_epoch=frame.authority_epoch,
            frame_type="handshake",
            nonce=nonce,
        )

    async def start_relay_session(self, session_id: str) -> dict[str, str]:
        """Start and own a Relay Host websocket for one authorized session."""
        if not session_id:
            raise ValueError("session_id is required")
        with self._lock:
            if self._closed:
                raise RuntimeError("cloud sync runtime is closed")
            existing = self._relay_tasks.get(session_id)
        if existing is not None and not existing.done():
            return {"status": "already_running", "session_id": session_id}
        relay = self.relay_session(session_id)
        import asyncio

        task = asyncio.create_task(relay.run(), name=f"notemeld-relay-host:{session_id}")
        with self._lock:
            self._relay_sessions[session_id] = relay
            self._relay_tasks[session_id] = task

        def cleanup(done_task: Any) -> None:
            with self._lock:
                if self._relay_tasks.get(session_id) is done_task:
                    self._relay_tasks.pop(session_id, None)
                    self._relay_sessions.pop(session_id, None)

        task.add_done_callback(cleanup)
        return {"status": "started", "session_id": session_id}

    async def stop_relay_session(self, session_id: str) -> dict[str, str]:
        with self._lock:
            relay = self._relay_sessions.pop(session_id, None)
            task = self._relay_tasks.pop(session_id, None)
        if relay is not None:
            await relay.stop()
        if task is not None and not task.done():
            task.cancel()
        return {"status": "stopped", "session_id": session_id}

    def pending(self, session_id: str):
        return self._authority_for(session_id).pending(session_id)

    def pending_sessions(self) -> list[dict[str, int | str]]:
        """Enumerate durable sessions needing resume/abandon decisions."""
        return self.mailbox.pending_sessions()

    def recover(self, session_id: str, mode: str) -> int:
        return self._authority_for(session_id).recover(session_id, mode)

    def rotate_authority(self, session_id: str, new_epoch: int) -> int:
        return self._authority_for(session_id).rotate_authority(session_id, new_epoch)

    def compact(self, session_id: str, keep_completed: int = 1000) -> int:
        """Compact terminal delivery rows after Agent results are projected."""
        return self.mailbox.compact(session_id, keep_completed)

    def status(self, session_id: str) -> dict[str, object]:
        """Return a UI-safe projection of durable Host queue state."""
        pending = self.pending(session_id)
        return {
            "session_id": session_id,
            "host_device_id": self.host_device_id,
            "pending_count": len(pending),
            "pending": [
                {
                    "request_id": item.request_id,
                    "sequence": item.sequence,
                    "status": self.mailbox.status(session_id, item.request_id) or "unknown",
                    "authority_epoch": item.authority_epoch,
                }
                for item in pending
            ],
        }

    def _authorize_lan_peer(
        self,
        session_id: str,
        controller_device_id: str,
        host_device_id: str,
    ) -> dict:
        assertion = self.cloud_client.authorize_lan_peer(
            session_id,
            controller_device_id,
            host_device_id,
        )
        if (
            assertion.get("session_id") != session_id
            or assertion.get("controller_device_id") != controller_device_id
            or assertion.get("host_device_id") != host_device_id
        ):
            raise ValueError("cloud LAN assertion identity mismatch")
        ttl_seconds = assertion.get("ttl_seconds")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 60:
            raise ValueError("cloud LAN assertion has invalid ttl")
        if type(assertion.get("valid_until")) is not int:
            raise ValueError("cloud LAN assertion has invalid expiry")
        authorization = LanPeerAuthorization(
            session_id=session_id,
            controller_device_id=controller_device_id,
            host_device_id=host_device_id,
            grant_id=assertion["grant_id"],
            role=assertion["role"],
            scopes=frozenset(assertion["scopes"]),
            workspace_id=assertion["workspace_id"],
            authority_epoch=assertion["authority_epoch"],
            # The cloud's wall clock is not authoritative for a local host.
            # Use the validated TTL so modest clock skew cannot invalidate a
            # freshly authorized LAN handshake (or extend it beyond the cap).
            valid_until=int(time.time()) + ttl_seconds,
            controller_public_key=str(assertion.get("controller_public_key") or ""),
        )
        with self._lock:
            key = (session_id, controller_device_id)
            self._authorizations[key] = authorization
            self._authorization_checked_at[key] = time.time()
        return assertion

    def _authority_for(self, session_id: str) -> RemoteHostAuthority:
        with self._lock:
            authority = self._authorities.get(session_id)
            if authority is not None:
                return authority

            def authorize(
                authorized_session_id: str,
                controller_device_id: str,
                epoch: int,
            ) -> bool:
                key = (authorized_session_id, controller_device_id)
                with self._lock:
                    assertion = self._authorizations.get(key)
                    checked_at = self._authorization_checked_at.get(key, 0.0)
                if assertion and time.time() - checked_at >= self._authorization_refresh_seconds:
                    try:
                        self._authorize_lan_peer(
                            authorized_session_id,
                            controller_device_id,
                            self.host_device_id,
                        )
                    except Exception:  # noqa: BLE001 - revocation/network errors fail closed
                        return False
                    with self._lock:
                        assertion = self._authorizations.get(key)
                return bool(
                    assertion
                    and assertion.session_id == authorized_session_id
                    and assertion.controller_device_id == controller_device_id
                    and assertion.host_device_id == self.host_device_id
                    and assertion.authority_epoch == epoch
                    and assertion.valid_until > time.time()
                )

            authority = RemoteHostAuthority(
                device_id=self.host_device_id,
                mailbox=self.mailbox,
                authorize=authorize,
            )
            self._authorities[session_id] = authority
            return authority

    def _handle_frame(
        self,
        frame,
        authorization: LanPeerAuthorization,
    ):
        authority = self._authority_for(frame.session_id)
        response = EncryptedRemoteHostHandler(
            authority,
            lambda current: self._cipher_for(current),
        )(frame, authorization)
        with self._lock:
            self._session_controllers[frame.session_id] = frame.sender_device_id
        self._agent_consumer.wake()
        return response

    def _emit_remote_event(self, command, event: dict) -> None:
        """Project persisted Agent events to the active encrypted controller."""
        with self._lock:
            controller_device_id = self._session_controllers.get(command.session_id)
            cipher = self._session_ciphers.get((command.session_id, controller_device_id or ""))
        if not controller_device_id or cipher is None:
            return
        sequence = cipher.last_sent_sequence + 1
        frame = RemoteFrame(
            session_id=command.session_id,
            sender_device_id=self.host_device_id,
            recipient_device_id=controller_device_id,
            sequence=sequence,
            ciphertext="",
            frame_id=str(uuid.uuid4()),
            authority_epoch=command.authority_epoch,
            frame_type="event",
            nonce="",
        )
        payload = json.dumps(
            {"frame_id": frame.frame_id, "request_id": command.request_id, "event": event},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        encrypted = cipher.encrypt_frame(frame, payload)
        self.service.send_event_nowait(command.session_id, controller_device_id, encrypted)

    def _cipher_for(self, authorization: LanPeerAuthorization) -> SessionCipher:
        with self._lock:
            installed = self._session_ciphers.get((authorization.session_id, authorization.controller_device_id))
        if installed is not None:
            return installed
        return self._cipher_resolver(authorization)

    def _complete_cipher_handshake(self, websocket: object, authorization: LanPeerAuthorization) -> SessionCipher:
        if self._cipher_handshake is not None:
            result: Any = self._cipher_handshake(websocket, authorization)
        elif self._host_signing_private is not None and self._host_signing_public is not None:
            result = accept_handshake(
                websocket,
                authorization,
                signing_private=self._host_signing_private,
                signing_public=self._host_signing_public,
            )
        else:
            raise RuntimeError("cipher handshake is not configured")

        if inspect.isawaitable(result):
            async def finish() -> SessionCipher:
                cipher = await result
                return self._install_handshake_cipher(authorization, cipher)
            return finish()  # type: ignore[return-value]
        return self._install_handshake_cipher(authorization, result)

    def _install_handshake_cipher(self, authorization: LanPeerAuthorization, cipher: Any) -> SessionCipher:
        if not isinstance(cipher, SessionCipher):
            raise TypeError("cipher handshake returned an invalid cipher")
        self.install_session_cipher(authorization.session_id, authorization.controller_device_id, cipher)
        return cipher


def attach_cloud_sync_runtime(app: FastAPI, runtime: CloudSyncHostRuntime) -> None:
    """Register a platform-constructed runtime for the backend lifespan.

    The caller must construct ``runtime`` with platform secure-storage
    credentials. This helper only stores the dependency; it never reads
    tokens or private keys from process environment variables.
    """
    if not isinstance(runtime, CloudSyncHostRuntime):
        raise TypeError("runtime must be a CloudSyncHostRuntime")
    existing = getattr(app.state, "cloud_sync_runtime", None)
    if existing is not None and existing is not runtime:
        raise RuntimeError("cloud sync runtime is already attached")
    app.state.cloud_sync_runtime = runtime
