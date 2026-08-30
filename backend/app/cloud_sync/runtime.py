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
    ):
        if cloud_client.device_id != host_device_id:
            raise ValueError("CloudClient must be bound to the host device")
        self.cloud_client = cloud_client
        self.host_device_id = host_device_id
        self.mailbox = DurableSessionMailbox(mailbox_path, max_size=mailbox_max_size)
        self._cipher_resolver = cipher_resolver
        self._authorizations: dict[tuple[str, str], LanPeerAuthorization] = {}
        self._authorities: dict[str, RemoteHostAuthority] = {}
        self._lock = Lock()
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
        self.cloud_client.close()

    def pending(self, session_id: str):
        return self._authority_for(session_id).pending(session_id)

    def recover(self, session_id: str, mode: str) -> int:
        return self._authority_for(session_id).recover(session_id, mode)

    def rotate_authority(self, session_id: str, new_epoch: int) -> int:
        return self._authority_for(session_id).rotate_authority(session_id, new_epoch)

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
        authorization = LanPeerAuthorization(
            session_id=session_id,
            controller_device_id=controller_device_id,
            host_device_id=host_device_id,
            grant_id=assertion["grant_id"],
            role=assertion["role"],
            scopes=frozenset(assertion["scopes"]),
            workspace_id=assertion["workspace_id"],
            authority_epoch=assertion["authority_epoch"],
            valid_until=assertion["valid_until"],
        )
        with self._lock:
            self._authorizations[(session_id, controller_device_id)] = authorization
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
                with self._lock:
                    assertion = self._authorizations.get(
                        (authorized_session_id, controller_device_id)
                    )
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
