from __future__ import annotations

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

    def envelope(self) -> dict:
        return {"protocol_version": self.protocol_version, "session_id": self.session_id, "sender_device_id": self.sender_device_id, "recipient_device_id": self.recipient_device_id, "sequence": self.sequence, "frame_id": self.frame_id, "authority_epoch": self.authority_epoch}

    def to_json(self) -> str:
        return json.dumps({**self.envelope(), "ciphertext": self.ciphertext}, separators=(",", ":"))
