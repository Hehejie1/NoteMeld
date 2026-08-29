from app.cloud_sync import DurableSessionMailbox, RemoteFrame, SessionMailbox, SessionCommand


def test_mailbox_is_serial_and_idempotent():
    mailbox = SessionMailbox(max_size=2)
    first = mailbox.enqueue("s1", "r1", "hello")
    duplicate = mailbox.enqueue("s1", "r1", "hello")
    second = mailbox.enqueue("s1", "r2", "world")
    assert (first.sequence, duplicate.status, second.sequence) == (1, "duplicate", 2)
    assert mailbox.pop().request_id == "r1"
    assert mailbox.pop().request_id == "r2"


def test_remote_frame_envelope_excludes_plaintext():
    frame = RemoteFrame("s", "a", "b", 1, "ciphertext", "f", 3)
    payload = frame.to_json()
    assert "ciphertext" in payload
    assert "input_text" not in payload
    assert frame.envelope()["authority_epoch"] == 3
    assert frame.envelope()["frame_type"] == "command"


def test_remote_frame_aad_binds_routing_metadata():
    frame = RemoteFrame("s", "a", "b", 1, "ciphertext", "f", 3, nonce="nonce")
    assert b'"recipient_device_id":"b"' in frame.associated_data()
    changed = RemoteFrame("s", "a", "other", 1, "ciphertext", "f", 3, nonce="nonce")
    assert frame.associated_data() != changed.associated_data()


def test_remote_frame_validation_is_shared_with_clients():
    frame = RemoteFrame("s", "a", "b", 1, "ciphertext", "f", 3, nonce="bm5ubm5ubm5ubm5u")
    frame.validate()
    try:
        RemoteFrame("s", "a", "b", 0, "ciphertext", "f", 3, nonce="bm5ubm5ubm5ubm5u").validate()
    except ValueError:
        pass
    else:
        raise AssertionError("invalid sequence must be rejected")


def test_remote_frame_from_json_validates_shape_and_fields():
    frame = RemoteFrame("s", "a", "b", 1, "ciphertext", "f", 3, nonce="bm5ubm5ubm5ubm5u")
    assert RemoteFrame.from_json(frame.to_json()) == frame
    malformed = frame.to_json().replace('"sequence":1', '"sequence":0')
    try:
        RemoteFrame.from_json(malformed)
    except ValueError:
        pass
    else:
        raise AssertionError("malformed frame must be rejected")


def test_durable_mailbox_survives_reopen(tmp_path):
    database = tmp_path / "queue.db"
    first = DurableSessionMailbox(database, max_size=2)
    assert first.enqueue("s1", "r1", "hello").sequence == 1
    assert first.enqueue("s1", "r2", "later").sequence == 2
    reopened = DurableSessionMailbox(database, max_size=2)
    command = reopened.pop("s1")
    assert command is not None and command.request_id == "r1" and command.sequence == 1
    reopened.complete("s1", "r1")
    assert len(reopened.pending("s1")) == 1
    assert reopened.discard_pending("s1") == 1
    assert reopened.pending("s1") == []


def test_durable_mailbox_recovery_requires_explicit_choice(tmp_path):
    mailbox = DurableSessionMailbox(tmp_path / "queue.db")
    mailbox.enqueue("s1", "r1", "hello")
    assert mailbox.pop("s1") is not None
    assert mailbox.recover("s1", "resume") == 1
    assert mailbox.pending("s1")[0].request_id == "r1"
    assert mailbox.pop("s1") is not None
    assert mailbox.recover("s1", "abandon") == 1
    assert mailbox.pending("s1") == []
