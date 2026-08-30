"""Device-remote Host boundary between decrypted relay frames and local Agent work."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable

from .protocol import RemoteFrame, SessionCommand
from .queue import DurableSessionMailbox


class RemoteHostError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RemoteHostReceipt:
    frame_id: str
    request_id: str
    session_id: str
    queue_sequence: int
    delivery_status: str
    queue_status: str

    def receipt_payload(self) -> dict[str, str | int]:
        return {
            "frame_id": self.frame_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "queue_sequence": self.queue_sequence,
            "queue_status": self.queue_status,
            "status": self.delivery_status,
        }


class RemoteHostAuthority:
    """Admit authenticated remote commands into the Host's durable mailbox.

    The platform transport must verify AEAD and pass the decrypted bytes here.
    A ``received`` receipt is returned only after ``enqueue`` commits locally.
    """

    def __init__(self, *, device_id: str, mailbox: DurableSessionMailbox,
                 authorize: Callable[[str, str, int], bool], max_payload_bytes: int = 100_000):
        if not device_id:
            raise ValueError("device id is required")
        if max_payload_bytes < 1:
            raise ValueError("max payload bytes must be positive")
        self.device_id = device_id
        self.mailbox = mailbox
        self.authorize = authorize
        self.max_payload_bytes = max_payload_bytes

    def receive_command(self, frame: RemoteFrame, plaintext: bytes) -> RemoteHostReceipt:
        try:
            frame.validate()
        except (TypeError, ValueError) as exc:
            raise RemoteHostError("invalid_frame", "remote frame is invalid") from exc
        if frame.frame_type != "command":
            raise RemoteHostError("invalid_frame_type", "remote Host accepts command frames only")
        if frame.recipient_device_id != self.device_id:
            raise RemoteHostError("wrong_recipient", "remote frame recipient does not match this Host")
        try:
            allowed = bool(self.authorize(frame.session_id, frame.sender_device_id, frame.authority_epoch))
        except Exception as exc:  # authorization adapters fail closed
            raise RemoteHostError("permission_denied", "remote command is not authorized") from exc
        if not allowed:
            raise RemoteHostError("permission_denied", "remote command is not authorized")
        request_id, input_text = self._decode_command(plaintext)
        try:
            queued = self.mailbox.enqueue(frame.session_id, request_id, input_text, frame.authority_epoch)
        except OverflowError as exc:
            raise RemoteHostError("queue_full", "remote session queue is full") from exc
        except RuntimeError as exc:
            raise RemoteHostError("recovery_required", "remote session requires recovery") from exc
        except ValueError as exc:
            code = "payload_conflict" if "payload conflict" in str(exc) else "authority_mismatch"
            raise RemoteHostError(code, "remote command was rejected") from exc
        except Exception as exc:
            raise RemoteHostError("host_unavailable", "remote Host could not persist the command") from exc
        return RemoteHostReceipt(
            frame_id=frame.frame_id,
            request_id=request_id,
            session_id=frame.session_id,
            queue_sequence=queued.sequence,
            delivery_status="received",
            queue_status=queued.status,
        )

    def claim(self, session_id: str) -> SessionCommand | None:
        return self.mailbox.pop(session_id)

    def complete(self, session_id: str, request_id: str) -> bool:
        return self.mailbox.complete(session_id, request_id)

    def fail(self, session_id: str, request_id: str) -> bool:
        return self.mailbox.fail(session_id, request_id)

    def recover(self, session_id: str, mode: str) -> int:
        return self.mailbox.recover(session_id, mode)

    def pending(self, session_id: str) -> list[SessionCommand]:
        return self.mailbox.pending(session_id)

    def rotate_authority(self, session_id: str, new_epoch: int) -> int:
        return self.mailbox.rotate_authority(session_id, new_epoch)

    def _decode_command(self, plaintext: bytes) -> tuple[str, str]:
        if not isinstance(plaintext, bytes) or len(plaintext) > self.max_payload_bytes:
            raise RemoteHostError("invalid_payload", "remote command payload is invalid")
        try:
            value = json.loads(plaintext.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RemoteHostError("invalid_payload", "remote command payload is invalid") from exc
        if not isinstance(value, dict) or set(value) != {"request_id", "input"}:
            raise RemoteHostError("invalid_payload", "remote command payload is invalid")
        request_id = value["request_id"]
        input_text = value["input"]
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise RemoteHostError("invalid_payload", "remote command payload is invalid")
        if not isinstance(input_text, str) or not 1 <= len(input_text) <= self.max_payload_bytes:
            raise RemoteHostError("invalid_payload", "remote command payload is invalid")
        return request_id, input_text
