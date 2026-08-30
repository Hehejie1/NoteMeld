import sqlite3
from concurrent.futures import ThreadPoolExecutor

from app.cloud_sync import DurableSessionMailbox, RemoteFrame, SessionMailbox, SessionCommand


def test_mailbox_is_serial_and_idempotent():
    mailbox = SessionMailbox(max_size=2)
    first = mailbox.enqueue("s1", "r1", "hello")
    duplicate = mailbox.enqueue("s1", "r1", "hello")
    second = mailbox.enqueue("s1", "r2", "world")
    assert (first.sequence, duplicate.status, second.sequence) == (1, "duplicate", 2)
    assert mailbox.pop().request_id == "r1"
    assert mailbox.pop().request_id == "r2"


def test_process_mailbox_request_identity_and_sequence_are_session_scoped():
    mailbox = SessionMailbox()
    assert mailbox.enqueue("s1", "same-request", "one").sequence == 1
    assert mailbox.enqueue("s2", "same-request", "two").sequence == 1


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
    wrong_type = frame.to_json().replace('"sequence":1', '"sequence":"1"')
    try:
        RemoteFrame.from_json(wrong_type)
    except ValueError:
        pass
    else:
        raise AssertionError("wrong field type must be rejected")


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


def test_durable_mailbox_allows_only_one_admitted_turn_across_restart(tmp_path):
    database = tmp_path / "queue.db"
    mailbox = DurableSessionMailbox(database)
    mailbox.enqueue("s1", "r1", "first")
    mailbox.enqueue("s1", "r2", "second")
    assert mailbox.pop("s1").request_id == "r1"
    assert mailbox.pop("s1") is None

    same_process = DurableSessionMailbox(database)
    assert same_process.status("s1", "r1") == "admitted"
    assert same_process.pop("s1") is None

    reopened = DurableSessionMailbox(database, process_owner="simulated-restart")
    assert reopened.status("s1", "r1") == "needs_attention"
    assert reopened.pop("s1") is None
    assert reopened.enqueue("s1", "r1", "first").status == "duplicate"
    try:
        reopened.enqueue("s1", "r3", "blocked while recovery is required")
    except RuntimeError as exc:
        assert "recovery" in str(exc)
    else:
        raise AssertionError("new commands must be rejected while recovery is required")
    assert reopened.recover("s1", "resume") == 1
    assert reopened.pop("s1").request_id == "r1"
    assert reopened.complete("s1", "r1") is True
    assert reopened.complete("s1", "r1") is False
    assert reopened.pop("s1").request_id == "r2"
    assert reopened.fail("s1", "r2") is True
    assert reopened.pending("s1") == []


def test_durable_mailbox_concurrent_claim_admits_exactly_one_turn(tmp_path):
    mailbox = DurableSessionMailbox(tmp_path / "queue.db")
    mailbox.enqueue("s1", "r1", "first")
    mailbox.enqueue("s1", "r2", "second")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: mailbox.pop("s1"), range(2)))
    admitted = [command for command in results if command is not None]
    assert len(admitted) == 1
    assert admitted[0].request_id == "r1"


def test_durable_mailbox_authority_rotation_fences_old_active_turn(tmp_path):
    mailbox = DurableSessionMailbox(tmp_path / "queue.db")
    mailbox.enqueue("s1", "r1", "active", authority_epoch=1)
    mailbox.enqueue("s1", "r2", "queued", authority_epoch=1)
    assert mailbox.pop("s1").request_id == "r1"

    assert mailbox.rotate_authority("s1", 2) == 2
    assert mailbox.status("s1", "r1") == "needs_attention"
    assert mailbox.pop("s1") is None
    try:
        mailbox.enqueue("s1", "stale", "stale", authority_epoch=1)
    except ValueError as exc:
        assert "authority epoch" in str(exc)
    else:
        raise AssertionError("stale authority epoch must be rejected")

    assert mailbox.recover("s1", "abandon") == 1
    assert mailbox.pop("s1").request_id == "r2"
    assert mailbox.pending("s1")[0].authority_epoch == 2


def test_durable_mailbox_migrates_legacy_rows_without_lease_owner(tmp_path):
    database = tmp_path / "legacy-queue.db"
    with sqlite3.connect(database) as cx:
        cx.execute("CREATE TABLE sync_mailbox (session_id TEXT NOT NULL, request_id TEXT NOT NULL, input_text TEXT NOT NULL, sequence INTEGER NOT NULL, authority_epoch INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'queued', created_at INTEGER NOT NULL, PRIMARY KEY(session_id, request_id), UNIQUE(session_id, sequence))")
        cx.execute("INSERT INTO sync_mailbox VALUES ('s1','r1','legacy',1,4,'queued',1)")

    mailbox = DurableSessionMailbox(database)
    assert mailbox.pending("s1")[0].authority_epoch == 4
    with sqlite3.connect(database) as cx:
        columns = {row[1] for row in cx.execute("PRAGMA table_info(sync_mailbox)")}
        epoch = cx.execute("SELECT authority_epoch FROM sync_mailbox_authority WHERE session_id='s1'").fetchone()[0]
    assert "lease_owner" in columns
    assert epoch == 4
