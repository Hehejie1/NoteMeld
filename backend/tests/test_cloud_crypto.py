import base64
import json
from pathlib import Path

import pytest

from app.cloud_sync.protocol import RemoteFrame


pytest.importorskip("cryptography")
crypto = pytest.importorskip("app.cloud_sync.e2ee")


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


def test_e2ee_rejects_ambiguous_identity_and_noncanonical_base64():
    signing_private, _ = crypto.generate_identity()
    _, ephemeral_public = crypto.generate_ephemeral()
    with pytest.raises(ValueError, match="identity"):
        crypto.sign_handshake(signing_private, "session\0forged", "device-a", "device-b", ephemeral_public)
    with pytest.raises(ValueError, match="base64"):
        crypto.decrypt(b"k" * 32, "not valid!", "also invalid!")
    with pytest.raises(ValueError, match="base64"):
        crypto.decrypt(b"k" * 32, "AAAAAAAAAAAAAAAA=", "YWJjZA")


def test_session_cipher_builds_frame_after_nonce_for_canonical_aad():
    sender = crypto.SessionCipher(b"k" * 32)
    receiver = crypto.SessionCipher(b"k" * 32)
    metadata = RemoteFrame(
        session_id="session",
        sender_device_id="device-a",
        recipient_device_id="device-b",
        sequence=1,
        ciphertext="",
        frame_id="frame-a",
        authority_epoch=1,
        nonce="",
    )

    encrypted = sender.encrypt_frame(metadata, b"secret")

    assert encrypted.nonce and encrypted.ciphertext
    assert receiver.decrypt(
        encrypted.sequence,
        encrypted.nonce,
        encrypted.ciphertext,
        encrypted.associated_data(),
    ) == b"secret"


def test_python_decrypts_browser_aes_gcm_contract_fixture():
    fixture = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts" / "relay-aes-gcm-v1.json").read_text(
            encoding="utf-8"
        )
    )
    frame = RemoteFrame(**fixture["frame"])
    key = base64.urlsafe_b64decode(fixture["key"] + "=")

    assert frame.associated_data().decode() == fixture["associated_data"]
    assert crypto.decrypt(
        key,
        frame.nonce,
        frame.ciphertext,
        frame.associated_data(),
    ).decode() == fixture["plaintext"]
