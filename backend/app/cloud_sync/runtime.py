"""Dependency-injected local Host runtime for LAN/cloud remote sessions."""
from __future__ import annotations

from pathlib import Path
from threading import Lock
import time
from typing import Callable

from fastapi import FastAPI

from .client import CloudClient
from .e2ee import SessionCipher
from .lan_auth import LanPeerAuthorization
from .lan_transport import EncryptedRemoteHostHandler, LanDirectService, install_lan_direct_service
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
    ):
        if cloud_client.device_id != host_device_id:
            raise ValueError("CloudClient must be bound to the host device")
        if authorization_refresh_seconds <= 0 or authorization_refresh_seconds > 60:
            raise ValueError("authorization refresh interval must be between 0 and 60 seconds")
        self.cloud_client = cloud_client
        self.host_device_id = host_device_id
        self.mailbox = DurableSessionMailbox(mailbox_path, max_size=mailbox_max_size)
        self._cipher_resolver = cipher_resolver
        self._authorizations: dict[tuple[str, str], LanPeerAuthorization] = {}
        self._authorization_checked_at: dict[tuple[str, str], float] = {}
        self._authorization_refresh_seconds = authorization_refresh_seconds
        self._authorities: dict[str, RemoteHostAuthority] = {}
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
        )

    def install(self, app: FastAPI) -> None:
        install_lan_direct_service(app, self.service)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.cloud_client.close()

    def heartbeat(self, lan_endpoints: list[str] | None = None) -> dict:
        """Refresh cloud presence and publish current LAN candidates."""
        return self.cloud_client.heartbeat(self.host_device_id, lan_endpoints)

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
        return EncryptedRemoteHostHandler(
            authority,
            self._cipher_resolver,
        )(frame, authorization)


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
