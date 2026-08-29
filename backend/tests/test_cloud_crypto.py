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


def test_session_cipher_rejects_replay_and_supports_explicit_rekey():
    first_private, first_public = crypto.generate_ephemeral()
    second_private, second_public = crypto.generate_ephemeral()
    first_key = crypto.derive_session_key(first_private, second_public, "session", "device-a", "device-b")
    second_key = crypto.derive_session_key(second_private, first_public, "session", "device-a", "device-b")
    sender = crypto.SessionCipher(first_key)
    receiver = crypto.SessionCipher(second_key)
    nonce, ciphertext = sender.encrypt(1, b"one", b"frame:1")
    assert receiver.decrypt(1, nonce, ciphertext, b"frame:1") == b"one"
    with pytest.raises(ValueError, match="replayed"):
        receiver.decrypt(1, nonce, ciphertext, b"frame:1")
    with pytest.raises(ValueError):
        sender.encrypt(1, b"duplicate", b"frame:1")
    rotated_first = crypto.derive_rekeyed_session_key(first_key, "session", "device-a", "device-b", 1)
    rotated_second = crypto.derive_rekeyed_session_key(second_key, "session", "device-a", "device-b", 1)
    assert rotated_first == rotated_second and rotated_first != first_key
    with pytest.raises(ValueError):
        crypto.derive_rekeyed_session_key(first_key, "session", "device-a", "device-b", 0)
