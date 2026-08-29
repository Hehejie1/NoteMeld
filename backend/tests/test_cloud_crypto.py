import pytest


pytest.importorskip("cryptography")
crypto = pytest.importorskip("cloud.crypto")


def test_e2ee_handshake_and_aead_roundtrip():
    signing_private, signing_public = crypto.generate_identity()
    first_private, first_public = crypto.generate_ephemeral()
    second_private, second_public = crypto.generate_ephemeral()
    signature = crypto.sign_handshake(signing_private, "session", "device-a", "device-b", first_public)
    crypto.verify_handshake(signing_public, signature, "session", "device-a", "device-b", first_public)
    first_key = crypto.derive_session_key(first_private, second_public, "session", "device-a", "device-b")
    second_key = crypto.derive_session_key(second_private, first_public, "session", "device-a", "device-b")
    nonce, ciphertext = crypto.encrypt(first_key, b"secret", b"session:1")
    assert crypto.decrypt(second_key, nonce, ciphertext, b"session:1") == b"secret"
    with pytest.raises(Exception):
        crypto.decrypt(second_key, nonce, ciphertext, b"session:2")
