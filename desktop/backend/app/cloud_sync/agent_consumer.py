"""Consume remote Host commands through the canonical NoteMeld Agent v1 path.

This module deliberately owns only mailbox admission and delivery bookkeeping.
The actual turn is created in ``agent_store`` and executed by the same
``NativeAgentExecutor`` used by the HTTP Agent API.
"""
from __future__ import annotations

import threading
import uuid
import time
from typing import Any, Callable

from .protocol import SessionCommand
from .remote_host import RemoteHostAuthority


EventSink = Callable[[SessionCommand, dict[str, Any]], None]
CommandRunner = Callable[[SessionCommand, Callable[[dict[str, Any]], None]], None]


def run_with_canonical_agent(
    command: SessionCommand,
    event_sink: Callable[[dict[str, Any]], None],
) -> None:
    """Submit one command to the existing HTTP Agent v1 implementation.

    Imports are intentionally lazy: cloud-sync unit tests and deployments that
    do not configure a remote Host must not initialize the native SDK merely by
    importing this module.
    """
    from app.agent_host.entry import get_agent_host_entry
    from app.db.model_dao import get_all_models
    from app.routers.agent import _executor, select_model

    entry = get_agent_host_entry()
    if entry.get_session(command.session_id) is None:
        entry.create_session(session_id=command.session_id, title="Remote session")
    selected_model = select_model(
        None,
        command.session_id,
        [str(row.get("model_name") or "") for row in get_all_models()],
    )
    turn = entry.create_turn(
        command.session_id,
        model_name=selected_model,
        idempotency_key=f"remote:{command.request_id}",
    )
    turn_id = str(turn["turn_id"])
    user_message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"notemeld:{turn_id}:user"))
    assistant_message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"notemeld:{turn_id}:assistant"))
    _executor.start(
        session_id=command.session_id,
        turn_id=turn_id,
        content=command.input_text,
        model_name=selected_model,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        event_sink=event_sink,
    )


class RemoteAgentMailboxConsumer:
    """Continuously drain admitted remote commands into canonical Agent turns."""

    def __init__(
        self,
        authority_for: Callable[[str], RemoteHostAuthority],
        *,
        pending_sessions: Callable[[], list[dict[str, Any]]],
        runner: CommandRunner | None = None,
        event_sink: EventSink | None = None,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        if poll_interval_seconds <= 0 or poll_interval_seconds > 60:
            raise ValueError("poll interval must be between 0 and 60 seconds")
        self._authority_for = authority_for
        self._pending_sessions = pending_sessions
        self._runner = runner or run_with_canonical_agent
        self._event_sink = event_sink
        self._poll_interval = poll_interval_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="notemeld-remote-agent-mailbox",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))
        self._thread = None

    def wake(self) -> None:
        self._wake.set()

    def drain_once(self) -> int:
        claimed = 0
        for item in self._authority_for_sessions():
            authority = self._authority_for(item["session_id"])
            command = authority.claim(item["session_id"])
            if command is None:
                continue
            claimed += 1
            self._dispatch(authority, command)
        return claimed

    def _authority_for_sessions(self) -> list[dict[str, Any]]:
        return list(self._pending_sessions())

    def _dispatch(self, authority: RemoteHostAuthority, command: SessionCommand) -> None:
        def on_event(event: dict[str, Any]) -> None:
            if self._event_sink is not None:
                self._event_sink(command, event)
            event_type = str(event.get("type") or "")
            if event_type in {"turn.succeeded", "turn.failed", "turn.cancelled", "turn.interrupted"}:
                self._finish_after_agent_projection(authority, command, event_type, event)

        try:
            self._runner(command, on_event)
        except Exception:
            authority.fail(command.session_id, command.request_id)

    @staticmethod
    def _finish_after_agent_projection(
        authority: RemoteHostAuthority,
        command: SessionCommand,
        event_type: str,
        event: dict[str, Any],
    ) -> None:
        """Release the mailbox only after the canonical Turn is terminal."""
        turn_id = str(event.get("turn_id") or "")
        if turn_id:
            try:
                from app.agent_host.entry import get_agent_host_entry

                entry = get_agent_host_entry()
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    turn = entry.get_turn(turn_id)
                    if turn is not None and entry.is_terminal(turn):
                        break
                    time.sleep(0.01)
            except Exception:
                # The Agent event is still authoritative for the outcome, but
                # the mailbox remains failed rather than being left admitted
                # if the projection cannot be inspected.
                event_type = "turn.failed"
        if event_type == "turn.succeeded":
            authority.complete(command.session_id, command.request_id)
        else:
            authority.fail(command.session_id, command.request_id)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.drain_once()
            except Exception:
                # A single malformed/recovering session must not stop other
                # remote sessions from being admitted after the next tick.
                pass
            self._wake.wait(self._poll_interval)
            self._wake.clear()
