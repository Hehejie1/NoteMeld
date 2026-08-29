from app.cloud_sync import RemoteFrame, SessionMailbox, SessionCommand


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
