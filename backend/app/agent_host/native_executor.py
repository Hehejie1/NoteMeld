from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

from app.agent_host.drivers.model import NoteMeldModelDriver
from app.agent_host.host import AgentSdkHost, get_agent_sdk_host
from app.ai import create_models
from app.db.model_dao import get_all_models
from app.services import agent_store
from app.services.conversation_store import get_conversation, update_message
from app.utils.logger import get_logger


_TERMINAL = {
    "turn.succeeded": "succeeded",
    "turn.failed": "failed",
    "turn.cancelled": "cancelled",
    "turn.interrupted": "interrupted",
}

logger = get_logger(__name__)


def _resolve_saved_model(model_name: str | None) -> tuple[Any, Any]:
    rows = get_all_models()
    candidates = [row for row in rows if not model_name or row.get("model_name") == model_name]
    if not candidates:
        raise ValueError("请先配置可用模型")
    row = candidates[0]
    models = create_models()
    model = models.get_model(str(row["provider_id"]), str(row["model_name"]))
    if model is None:
        raise ValueError("模型配置不存在或已失效")
    return models, model


class NativeAgentExecutor:
    """Run one persisted Agent v1 turn through the standalone Rust SDK."""

    def __init__(
        self,
        *,
        event_sink: Callable[[dict[str, Any]], Any] | None = None,
        finish_turn: Callable[..., Any] | None = None,
        library: str | None = None,
    ) -> None:
        self.event_sink = event_sink
        self.finish_turn = finish_turn
        self.library = library

    def start(self, turn_id: str, session_id: str, content: str, *, model_name: str | None = None,
              assistant_message_id: str | None = None) -> threading.Thread:
        worker = threading.Thread(
            target=self.run_sync,
            args=(turn_id, session_id, content),
            kwargs={"model_name": model_name, "assistant_message_id": assistant_message_id},
            name=f"notemeld-agent-{turn_id[:8]}",
            daemon=True,
        )
        worker.start()
        return worker

    def run_sync(self, turn_id: str, session_id: str, content: str, *, model_name: str | None = None,
                 assistant_message_id: str | None = None) -> None:
        terminal: dict[str, Any] | None = None
        assistant_content = ""
        try:
            models, model = _resolve_saved_model(model_name)
            model_override = {
                "provider_id": str(getattr(model, "provider_id", "")),
                "model_name": str(getattr(model, "name", model_name) or ""),
            }

            async def call_driver(request: dict[str, Any]) -> dict[str, Any]:
                kind = request.get("kind")
                if kind == "model.stream":
                    result = await NoteMeldModelDriver(models, model).stream(request)
                    if result.get("ok"):
                        return {"schema_version": "1", "ok": True, "result": {
                            "chunks": result.get("chunks", []),
                            "completion": {
                                "content": result.get("content", ""),
                                "tool_calls": result.get("tool_calls", []),
                                "finish_reason": result.get("finish_reason", "stop"),
                                "usage": result.get("usage", {}),
                            },
                        }}
                    return {"schema_version": "1", **result}
                return {"schema_version": "1", "ok": False,
                        "error": {"code": "invalid_input", "message": "当前能力尚未接入"}}

            def on_event(event: dict[str, Any]) -> None:
                nonlocal terminal, assistant_content
                event_type = str(event.get("type") or "")
                if self.event_sink is not None:
                    self.event_sink(event)
                if event_type in _TERMINAL:
                    terminal = event
                    if assistant_message_id:
                        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
                        update_message(session_id, assistant_message_id, {
                            "status": "completed" if event_type == "turn.succeeded" else "failed",
                            "content": assistant_content,
                            "error": event_type != "turn.succeeded",
                            "meta": {"turn_id": turn_id, "error": error},
                        })
                else:
                    if event_type == "message.delta":
                        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                        assistant_content += str(payload.get("delta") or payload.get("content") or "")
                        if assistant_message_id:
                            update_message(session_id, assistant_message_id, {"content": assistant_content, "status": "streaming"})
                    agent_store.append_event(
                        turn_id,
                        event,
                        sequence=event.get("sequence"),
                        event_type=event_type,
                    )

            def driver(request: dict[str, Any]) -> dict[str, Any]:
                return asyncio.run(call_driver(request))

            host: AgentSdkHost = AgentSdkHost(binding_path=self.library) if self.library else get_agent_sdk_host()
            conversation = get_conversation(session_id) or {}
            history = [
                {"role": str(message.get("role") or ""), "content": str(message.get("content") or "")}
                for message in conversation.get("messages", [])
                if str(message.get("role") or "") in {"user", "assistant", "tool"}
                and str(message.get("content") or "")
            ][-40:]
            if history and history[-1] == {"role": "user", "content": content}:
                history.pop()
            handle = host.submit(
                turn_id,
                {
                    "schema_version": "1",
                    "request_id": turn_id,
                    "session_id": session_id,
                    "input": {"text": content, "attachments": [], "context_refs": []},
                    "history": history,
                    "model_override": model_override,
                    "approval_mode": "interactive",
                },
                driver=driver,
                on_event=on_event,
            )
            host.runtime.wait(handle.token, 30_000)
            host.forget(turn_id)
            if terminal is None:
                raise RuntimeError("Agent SDK did not emit a terminal event")
            status = _TERMINAL[str(terminal["type"])]
            payload = terminal.get("payload") if isinstance(terminal.get("payload"), dict) else {}
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            self._finish(turn_id, session_id, status, terminal, error)
        except Exception as error:  # noqa: BLE001 - terminal boundary
            # Keep the public event deliberately redacted, but retain the
            # exception class/message in the sidecar log so packaged startup
            # and native driver integration failures are diagnosable.
            logger.exception("Agent SDK turn failed at host boundary: turn_id=%s", turn_id)
            event = {"type": "turn.failed", "payload": {"error": {"code": "sdk_internal_error", "message": "Agent 执行失败"}}}
            if self.event_sink is not None:
                self.event_sink(event)
            self._finish(turn_id, session_id, "failed", event, event["payload"]["error"])

    def _finish(self, turn_id: str, session_id: str, status: str, event: dict[str, Any], error: dict[str, Any]) -> None:
        callback = self.finish_turn
        if callback is not None:
            callback(
                session_id,
                turn_id,
                status,
                event,
                error_code=error.get("code"),
                error_message=error.get("message"),
                terminal_event_type=event.get("type", "terminal"),
            )
        else:
            agent_store.transition_turn(
                turn_id,
                status,
                error_code=error.get("code"),
                error_message=error.get("message"),
                terminal_event=event,
                terminal_event_type=event.get("type", "terminal"),
            )
