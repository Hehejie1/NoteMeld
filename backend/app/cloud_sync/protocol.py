from __future__ import annotations

import base64
import binascii
import hashlib
import json
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
        text_fields = (self.session_id, self.sender_device_id, self.recipient_device_id, self.frame_id, self.ciphertext, self.nonce, self.frame_type)
        if any(not isinstance(value, str) or not value for value in text_fields):
            raise ValueError("incomplete remote frame")
        if any(len(value) > 4096 for value in (self.session_id, self.sender_device_id, self.recipient_device_id, self.frame_id)) or len(self.nonce) > 24 or len(self.ciphertext) > 4 * 1024 * 1024:
            raise ValueError("remote frame field is too large")
        if type(self.sequence) is not int or type(self.authority_epoch) is not int or self.sequence < 1 or self.authority_epoch < 0 or self.frame_type not in {"command", "receipt", "event"}:
            raise ValueError("invalid remote frame metadata")
        try:
            nonce = base64.b64decode(self.nonce + "=" * (-len(self.nonce) % 4), altchars=b"-_", validate=True)
        except (ValueError, TypeError, binascii.Error):
            raise ValueError("invalid remote frame nonce") from None
        if len(nonce) != 12:
            raise ValueError("invalid remote frame nonce")

    def to_json(self) -> str:
        return json.dumps({**self.envelope(), "ciphertext": self.ciphertext}, separators=(",", ":"))

    @classmethod
    def from_json(cls, payload: str) -> "RemoteFrame":
        if not isinstance(payload, str) or len(payload) > 5 * 1024 * 1024:
            raise ValueError("remote frame JSON is too large")
        try:
            value = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid remote frame JSON") from exc
        if not isinstance(value, dict) or set(value) != set(cls("", "", "", 1, "", "", 0).envelope()) | {"ciphertext"}:
            raise ValueError("invalid remote frame shape")
        frame = cls(
            session_id=value["session_id"], sender_device_id=value["sender_device_id"],
            recipient_device_id=value["recipient_device_id"], sequence=value["sequence"],
            ciphertext=value["ciphertext"], frame_id=value["frame_id"],
            authority_epoch=value["authority_epoch"], protocol_version=value["protocol_version"],
            nonce=value["nonce"], frame_type=value["frame_type"],
        )
        try:
            frame.validate()
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid remote frame fields") from exc
        return frame
