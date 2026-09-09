from __future__ import annotations

from app.cloud_sync.agent_consumer import RemoteAgentMailboxConsumer
from app.cloud_sync.queue import DurableSessionMailbox
from app.cloud_sync.remote_host import RemoteHostAuthority


def test_remote_consumer_claims_mailbox_and_completes_canonical_turn(tmp_path):
    mailbox = DurableSessionMailbox(tmp_path / "mailbox.sqlite")
    mailbox.enqueue("session-a", "request-a", "hello", 1)
    authority = RemoteHostAuthority(
        device_id="host",
        mailbox=mailbox,
        authorize=lambda *_: True,
    )
    seen = []

    def runner(command, on_event):
        seen.append(command)
        on_event({"type": "message.delta", "payload": {"delta": "hi"}})
        on_event({"type": "turn.succeeded", "payload": {"content": "hi"}})

    consumer = RemoteAgentMailboxConsumer(
        lambda _session_id: authority,
        pending_sessions=lambda: mailbox.pending_sessions(),
        runner=runner,
    )
    assert consumer.drain_once() == 1
    assert seen[0].request_id == "request-a"
    assert mailbox.status("session-a", "request-a") == "completed"


def test_remote_consumer_fails_mailbox_when_canonical_runner_rejects(tmp_path):
    mailbox = DurableSessionMailbox(tmp_path / "mailbox.sqlite")
    mailbox.enqueue("session-a", "request-a", "hello", 1)
    authority = RemoteHostAuthority(
        device_id="host",
        mailbox=mailbox,
        authorize=lambda *_: True,
    )

    def runner(_command, _on_event):
        raise RuntimeError("agent unavailable")

    consumer = RemoteAgentMailboxConsumer(
        lambda _session_id: authority,
        pending_sessions=lambda: mailbox.pending_sessions(),
        runner=runner,
    )
    assert consumer.drain_once() == 1
    assert mailbox.status("session-a", "request-a") == "failed"

