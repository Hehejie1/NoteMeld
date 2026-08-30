import json

import pytest

from app.cloud_sync import DurableSessionMailbox, RemoteFrame
from app.cloud_sync.remote_host import RemoteHostAuthority, RemoteHostError


NONCE = "bm5ubm5ubm5ubm5u"


def frame(*, recipient: str = "host-device", epoch: int = 1, frame_id: str = "frame-1") -> RemoteFrame:
    return RemoteFrame(
        session_id="session-1",
        sender_device_id="controller-device",
        recipient_device_id=recipient,
        sequence=1,
        ciphertext="opaque-ciphertext",
        frame_id=frame_id,
        authority_epoch=epoch,
        nonce=NONCE,
        frame_type="command",
    )


def test_remote_host_receipts_only_after_durable_enqueue(tmp_path):
    database = tmp_path / "remote-queue.db"
    authority = RemoteHostAuthority(
        device_id="host-device",
        mailbox=DurableSessionMailbox(database),
        authorize=lambda session_id, sender_id, epoch: (session_id, sender_id, epoch) == ("session-1", "controller-device", 1),
    )
    payload = json.dumps({"request_id": "request-1", "input": "run the agent"}).encode()

    receipt = authority.receive_command(frame(), payload)
    assert receipt.delivery_status == "received"
    assert receipt.queue_status == "queued"
    assert receipt.receipt_payload() == {
        "frame_id": "frame-1",
        "request_id": "request-1",
        "session_id": "session-1",
        "queue_sequence": 1,
        "queue_status": "queued",
        "status": "received",
    }
    reopened = DurableSessionMailbox(database)
    assert reopened.pending("session-1")[0].input_text == "run the agent"

    duplicate = authority.receive_command(frame(frame_id="frame-retry"), payload)
    assert duplicate.queue_status == "duplicate"
    assert len(reopened.pending("session-1")) == 1


def test_remote_host_rejects_wrong_recipient_unauthorized_and_invalid_payload(tmp_path):
    authority = RemoteHostAuthority(
        device_id="host-device",
        mailbox=DurableSessionMailbox(tmp_path / "remote-queue.db"),
        authorize=lambda *_: False,
    )
    payload = b'{"request_id":"request-1","input":"hello"}'
    with pytest.raises(RemoteHostError, match="recipient") as wrong:
        authority.receive_command(frame(recipient="other-device"), payload)
    assert wrong.value.code == "wrong_recipient"
    with pytest.raises(RemoteHostError) as denied:
        authority.receive_command(frame(), payload)
    assert denied.value.code == "permission_denied"

    allowed = RemoteHostAuthority(
        device_id="host-device",
        mailbox=DurableSessionMailbox(tmp_path / "allowed-queue.db"),
        authorize=lambda *_: True,
    )
    for malformed in (b"not-json", b"[]", b'{"request_id":"r","input":"x","secret":"no"}', b'{"request_id":"","input":"x"}'):
        with pytest.raises(RemoteHostError) as invalid:
            allowed.receive_command(frame(), malformed)
        assert invalid.value.code == "invalid_payload"


def test_remote_host_drives_one_active_turn_and_explicit_recovery(tmp_path):
    mailbox = DurableSessionMailbox(tmp_path / "remote-queue.db")
    authority = RemoteHostAuthority(device_id="host-device", mailbox=mailbox, authorize=lambda *_: True)
    authority.receive_command(frame(frame_id="f1"), b'{"request_id":"r1","input":"first"}')
    second = RemoteFrame(**{**frame(frame_id="f2").__dict__, "sequence": 2})
    authority.receive_command(second, b'{"request_id":"r2","input":"second"}')

    active = authority.claim("session-1")
    assert active is not None and active.request_id == "r1"
    assert authority.claim("session-1") is None
    assert authority.complete("session-1", "r1") is True
    assert authority.claim("session-1").request_id == "r2"

    restarted = RemoteHostAuthority(
        device_id="host-device",
        mailbox=DurableSessionMailbox(tmp_path / "remote-queue.db", process_owner="restarted-host"),
        authorize=lambda *_: True,
    )
    assert restarted.claim("session-1") is None
    assert restarted.recover("session-1", "abandon") == 1
    assert restarted.pending("session-1") == []


def test_remote_host_normalizes_mailbox_failures_without_plaintext(tmp_path):
    database = tmp_path / "remote-queue.db"
    authority = RemoteHostAuthority(
        device_id="host-device",
        mailbox=DurableSessionMailbox(database, max_size=1),
        authorize=lambda *_: True,
    )
    authority.receive_command(frame(), b'{"request_id":"r1","input":"first"}')

    cases = [
        (frame(frame_id="conflict"), b'{"request_id":"r1","input":"changed"}', "payload_conflict"),
        (RemoteFrame(**{**frame(frame_id="full").__dict__, "sequence": 2}), b'{"request_id":"r2","input":"second"}', "queue_full"),
        (frame(epoch=2, frame_id="stale-authority"), b'{"request_id":"r3","input":"third"}', "authority_mismatch"),
    ]
    for incoming, payload, code in cases:
        with pytest.raises(RemoteHostError) as rejected:
            authority.receive_command(incoming, payload)
        assert rejected.value.code == code
        assert payload.decode() not in str(rejected.value)

    assert authority.claim("session-1") is not None
    restarted = RemoteHostAuthority(
        device_id="host-device",
        mailbox=DurableSessionMailbox(database, process_owner="new-process"),
        authorize=lambda *_: True,
    )
    with pytest.raises(RemoteHostError) as blocked:
        restarted.receive_command(RemoteFrame(**{**frame(frame_id="blocked").__dict__, "sequence": 3}), b'{"request_id":"r4","input":"blocked"}')
    assert blocked.value.code == "recovery_required"

    class BrokenMailbox:
        def enqueue(self, *_):
            raise OSError("/private/secret/queue.db")

    broken = RemoteHostAuthority(device_id="host-device", mailbox=BrokenMailbox(), authorize=lambda *_: True)  # type: ignore[arg-type]
    with pytest.raises(RemoteHostError) as unavailable:
        broken.receive_command(frame(frame_id="broken"), b'{"request_id":"r5","input":"private input"}')
    assert unavailable.value.code == "host_unavailable"
    assert "secret" not in str(unavailable.value) and "private input" not in str(unavailable.value)
