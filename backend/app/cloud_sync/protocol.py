from __future__ import annotations

import hashlib
import json
import base64
from dataclasses import dataclass


PROTOCOL_VERSION = "notemeld.sync.v1"


@dataclass(frozen=True)
class SessionCommand:
    session_id: str
    request_id: str
    input_text: str
    sequence: int
    payload_hash: str
    authority_epoch: int = 0

    @classmethod
    def create(cls, session_id: str, request_id: str, input_text: str, sequence: int, authority_epoch: int = 0) -> "SessionCommand":
        return cls(session_id, request_id, input_text, sequence, hashlib.sha256(input_text.encode()).hexdigest(), authority_epoch)


@dataclass(frozen=True)
class RemoteFrame:
    session_id: str
    sender_device_id: str
    recipient_device_id: str
    sequence: int
    ciphertext: str
    frame_id: str
    authority_epoch: int
    protocol_version: str = PROTOCOL_VERSION
    nonce: str = ""
    frame_type: str = "command"

    def envelope(self) -> dict:
        return {"protocol_version": self.protocol_version, "session_id": self.session_id, "sender_device_id": self.sender_device_id, "recipient_device_id": self.recipient_device_id, "sequence": self.sequence, "frame_id": self.frame_id, "authority_epoch": self.authority_epoch, "nonce": self.nonce, "frame_type": self.frame_type}

    def associated_data(self) -> bytes:
        """Canonical metadata bytes to bind into the client-side AEAD tag."""
        return json.dumps(self.envelope(), sort_keys=True, separators=(",", ":")).encode("utf-8")

    def validate(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError("unsupported sync protocol")
        if not self.session_id or not self.sender_device_id or not self.recipient_device_id or not self.frame_id or not self.ciphertext:
            raise ValueError("incomplete remote frame")
        if self.sequence < 1 or self.authority_epoch < 0 or self.frame_type not in {"command", "receipt", "event"}:
            raise ValueError("invalid remote frame metadata")
        try:
            nonce = base64.urlsafe_b64decode(self.nonce + "=" * (-len(self.nonce) % 4))
        except (ValueError, TypeError):
            raise ValueError("invalid remote frame nonce") from None
        if len(nonce) != 12:
            raise ValueError("invalid remote frame nonce")

    def to_json(self) -> str:
        return json.dumps({**self.envelope(), "ciphertext": self.ciphertext}, separators=(",", ":"))
