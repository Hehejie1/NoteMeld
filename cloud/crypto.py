"""Compatibility exports for the former client E2EE import path.

Device adapters should import :mod:`backend.app.cloud_sync.e2ee`. The cloud
service itself never decrypts relay frames and does not import this module.
"""

try:
    from app.cloud_sync.e2ee import (  # type: ignore[no-redef]  # noqa: F401
        SessionCipher,
        decrypt,
        derive_rekeyed_session_key,
        derive_session_key,
        encrypt,
        generate_ephemeral,
        generate_identity,
        sign_handshake,
        verify_handshake,
    )
except ModuleNotFoundError:
    from backend.app.cloud_sync.e2ee import (  # type: ignore[no-redef]  # noqa: F401
        SessionCipher,
        decrypt,
        derive_rekeyed_session_key,
        derive_session_key,
        encrypt,
        generate_ephemeral,
        generate_identity,
        sign_handshake,
        verify_handshake,
    )

__all__ = [
    "SessionCipher",
    "decrypt",
    "derive_rekeyed_session_key",
    "derive_session_key",
    "encrypt",
    "generate_ephemeral",
    "generate_identity",
    "sign_handshake",
    "verify_handshake",
]
