"""Local adapters for cloud-native and device-remote sessions."""

from .client import CloudClient, CloudClientError
from .connection import (
    ConnectionCandidate,
    connect_with_fallback,
    connection_candidates,
    validate_cloud_base_url,
)
from .device_id import make_device_id
from .e2ee import (
    SessionCipher,
    derive_rekeyed_session_key,
    derive_session_key,
    generate_ephemeral,
    generate_identity,
    sign_handshake,
    verify_handshake,
)
from .lan_auth import (
    LanAuthError,
    LanChallenge,
    LanPeerAuthenticator,
    LanPeerAuthorization,
)
from .lan_transport import (
    EncryptedRemoteHostHandler,
    LAN_PROTOCOL_VERSION,
    LanDirectFrameError,
    LanDirectService,
    install_lan_direct_service,
)
from .protocol import RemoteFrame, SessionCommand
from .queue import DurableSessionMailbox, SessionMailbox
from .remote_host import RemoteHostAuthority, RemoteHostError, RemoteHostReceipt
from .token_store import EncryptedTokenStore

__all__ = [
    "CloudClient",
    "CloudClientError",
    "ConnectionCandidate",
    "DurableSessionMailbox",
    "EncryptedTokenStore",
    "EncryptedRemoteHostHandler",
    "LanAuthError",
    "LanChallenge",
    "LanDirectFrameError",
    "LanDirectService",
    "LanPeerAuthenticator",
    "LanPeerAuthorization",
    "LAN_PROTOCOL_VERSION",
    "RemoteFrame",
    "RemoteHostAuthority",
    "RemoteHostError",
    "RemoteHostReceipt",
    "SessionCipher",
    "SessionCommand",
    "SessionMailbox",
    "connect_with_fallback",
    "connection_candidates",
    "derive_rekeyed_session_key",
    "derive_session_key",
    "generate_ephemeral",
    "generate_identity",
    "install_lan_direct_service",
    "make_device_id",
    "sign_handshake",
    "validate_cloud_base_url",
    "verify_handshake",
]
