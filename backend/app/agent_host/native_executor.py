from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Callable

from app.agent_host.drivers.model import NoteMeldModelDriver
from app.agent_host.drivers.tools import NoteMeldToolDriver
from app.agent_host.drivers.storage import ConversationHistoryStore
from app.agent_host.host import AgentSdkHost, get_agent_sdk_host
from app.agent_host.knowledge_provider import NoteMeldKnowledgeProvider
from app.ai import create_models
from app.db.model_dao import get_all_models
from app.services import agent_store
from app.services.conversation_store import append_message, update_message
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


def _safe_model_config(model: Any) -> dict[str, Any]:
    capabilities = getattr(model, "capabilities", None)
    return {
        "provider_id": str(getattr(model, "provider_id", "") or ""),
        "model_name": str(getattr(model, "name", "") or ""),
        "context_window_tokens": int(getattr(model, "context_window_tokens", 4096) or 4096),
        "capabilities": {
            "supports_vision": bool(getattr(model, "supports_vision", False)),
            "supports_stream": bool(getattr(model, "supports_stream", True)),
            "supports_tool_calling": getattr(capabilities, "supports_tool_calling", None),
        },
    }


def _complete_driver_messages(
    raw_messages: Any,
    *,
    history: list[dict[str, Any]],
    current_text: str,
) -> list[dict[str, Any]]:
    """Keep SDK messages authoritative, with an ABI-v1 first-round fallback.

    Current native artifacts send the complete canonical message list. Older
    ABI-v1 artifacts may send only the current user message on the first model
    call; prefix the already loaded Conversation snapshot only for that exact
    shape. Empty model requests fail closed at the caller.
    """
    if not isinstance(raw_messages, list):
        return []
    messages = [dict(item) for item in raw_messages if isinstance(item, dict)]
    if len(messages) != 1 or not history:
        return messages
    only = messages[0]
    content = only.get("content")
    is_current_user = only.get("role") == "user" and (
        content == current_text
        or isinstance(content, dict) and str(content.get("text") or "") == current_text
    )
    return [*history, only] if is_current_user else messages


def _is_model_history_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    role = str(item.get("role") or "")
    if role not in {"system", "user", "assistant", "tool"}:
        return False
    content = item.get("content")
    if content is not None and str(content):
        return True
    if role == "assistant" and item.get("tool_calls"):
        return True
    return role == "tool" and bool(item.get("tool_call_id"))


class NativeAgentExecutor:
    """Run one persisted Agent v1 turn through the standalone Rust SDK."""

    def __init__(
        self,
        *,
        event_sink: Callable[[dict[str, Any]], Any] | None = None,
        finish_turn: Callable[..., Any] | None = None,
        library: str | None = None,
        tool_driver: NoteMeldToolDriver | None = None,
    ) -> None:
        self.event_sink = event_sink
        self.finish_turn = finish_turn
        self.library = library
        self.tool_driver = tool_driver

    def start(self, turn_id: str, session_id: str, content: str, *, model_name: str | None = None,
              user_message_id: str | None = None, assistant_message_id: str | None = None, asset_content: str | None = None,
              attachments: list[dict[str, Any]] | None = None,
              context_refs: list[dict[str, Any]] | None = None,
              event_sink: Callable[[dict[str, Any]], Any] | None = None) -> threading.Thread:
        worker = threading.Thread(
            target=self.run_sync,
            args=(turn_id, session_id, content),
            kwargs={
                "model_name": model_name,
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
                "asset_content": asset_content,
                "attachments": attachments,
                "context_refs": context_refs,
                "event_sink": event_sink,
            },
            name=f"notemeld-agent-{turn_id[:8]}",
            daemon=True,
        )
        worker.start()
        return worker

    def run_sync(self, turn_id: str, session_id: str, content: str, *, model_name: str | None = None,
                 user_message_id: str | None = None, assistant_message_id: str | None = None, asset_content: str | None = None,
                 attachments: list[dict[str, Any]] | None = None,
                 context_refs: list[dict[str, Any]] | None = None,
                 event_sink: Callable[[dict[str, Any]], Any] | None = None) -> None:
        terminal: dict[str, Any] | None = None
        assistant_content = ""
        sink = event_sink or self.event_sink
        history_store = ConversationHistoryStore()
        try:
            self._seed_conversation_messages(
                session_id=session_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                content=content,
            )
            models, model = _resolve_saved_model(model_name)
            knowledge_provider = NoteMeldKnowledgeProvider()
            model_override = {
                "provider_id": str(getattr(model, "provider_id", "")),
                "model_name": str(getattr(model, "name", model_name) or ""),
            }
            model_config = _safe_model_config(model)
            model_driver = NoteMeldModelDriver(
                models,
                model,
                options={
                    "usage_context": {
                        "phase": "agent",
                        "task_id": turn_id,
                        "request_meta": {"session_id": session_id, "turn_id": turn_id},
                    },
                },
            )

            async def call_driver(request: dict[str, Any]) -> dict[str, Any]:
                kind = request.get("kind")
                driver_payload = request.get("payload")
                if not isinstance(driver_payload, dict):
                    driver_payload = request
                if kind == "model.stream":
                    model_request = dict(driver_payload)
                    model_request["messages"] = _complete_driver_messages(
                        driver_payload.get("messages"),
                        history=history,
                        current_text=content,
                    )
                    if not model_request["messages"]:
                        return {
                            "schema_version": "1",
                            "ok": False,
                            "error": {
                                "code": "invalid_input",
                                "message": "模型请求缺少消息上下文",
                                "details": {},
                            },
                        }
                    model_request.update({
                        "model": model_config,
                        "model_override": model_override,
                        "input": normalized_input,
                        "context_refs": normalized_context_refs,
                        "tools": tool_descriptors,
                        "generation_config": {},
                    })
                    result = await model_driver.stream(model_request)
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
                if kind == "tool.describe":
                    names = driver_payload.get("names", []) if isinstance(driver_payload, dict) else []
                    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
                        return {"schema_version": "1", "ok": False,
                                "error": {"code": "invalid_input", "message": "工具名称必须是字符串数组"}}
                    try:
                        provider = self.tool_driver.registry if self.tool_driver is not None else knowledge_provider
                        descriptors = provider.describe(names)
                        if asyncio.iscoroutine(descriptors):
                            descriptors = await descriptors
                    except ValueError as error:
                        return {"schema_version": "1", "ok": False,
                                "error": {"code": "invalid_input", "message": str(error)}}
                    except Exception:  # noqa: BLE001 - product capability boundary
                        logger.exception("Agent SDK product tool discovery failed")
                        return {"schema_version": "1", "ok": False,
                                "error": {"code": "tool_failed", "message": "工具发现失败"}}
                    return {"schema_version": "1", "ok": True, "result": {"tools": descriptors}}
                if kind == "tool.invoke":
                    driver = self.tool_driver or NoteMeldToolDriver(provider=knowledge_provider)
                    if driver is None:
                        return {"schema_version": "1", "ok": False,
                                "error": {"code": "tool_failed", "message": "产品工具驱动未配置"}}
                    arguments = driver_payload.get("arguments", {})
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = None
                    if not isinstance(arguments, dict):
                        return {"schema_version": "1", "ok": False,
                                "error": {"code": "invalid_input", "message": "工具参数必须是对象"}}
                    try:
                        output = await driver.invoke(
                            {
                                "call_id": driver_payload.get("call_id"),
                                "tool_name": driver_payload.get("tool_name"),
                                "arguments": arguments,
                            },
                            {
                                "session_id": driver_payload.get("session_id") or session_id,
                                "turn_id": driver_payload.get("turn_id") or turn_id,
                            },
                        )
                    except ValueError as error:
                        return {"schema_version": "1", "ok": False,
                                "error": {"code": "invalid_input", "message": str(error)}}
                    except Exception:  # noqa: BLE001 - product tool boundary
                        logger.exception("Agent SDK product tool failed")
                        return {"schema_version": "1", "ok": False,
                                "error": {"code": "tool_failed", "message": "工具执行失败"}}
                    return {"schema_version": "1", "ok": True, "result": {"output": output}}
                return {"schema_version": "1", "ok": False,
                        "error": {"code": "invalid_input", "message": "当前能力尚未接入"}}

            def on_event(event: dict[str, Any]) -> None:
                nonlocal terminal, assistant_content
                event_type = str(event.get("type") or "")
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                if event_type in _TERMINAL:
                    terminal = event
                    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
                    if assistant_message_id:
                        self._safe_update_message(session_id, assistant_message_id, {
                            "status": "completed" if event_type == "turn.succeeded" else "failed",
                            "content": assistant_content,
                            "error": event_type != "turn.succeeded",
                            "meta": {"turn_id": turn_id, "error": error},
                        })
                    if sink is not None:
                        sink(event)
                else:
                    if event_type == "message.started":
                        if assistant_message_id and str(payload.get("role") or "").lower() == "assistant":
                            self._safe_update_message(session_id, assistant_message_id, {
                                "status": "running",
                                "content": str(payload.get("content") or ""),
                            })
                    elif event_type == "message.delta":
                        assistant_content += str(payload.get("delta") or payload.get("content") or "")
                        if assistant_message_id:
                            self._safe_update_message(session_id, assistant_message_id, {"content": assistant_content, "status": "streaming"})
                    elif event_type == "message.completed":
                        content_payload = payload.get("content")
                        if content_payload is not None:
                            assistant_content = str(content_payload)
                            if assistant_message_id:
                                self._safe_update_message(session_id, assistant_message_id, {"content": assistant_content, "status": "streaming"})
                    elif event_type == "usage.updated":
                        if assistant_message_id and payload:
                            self._safe_update_message(session_id, assistant_message_id, {"meta": {"usage": payload}})

                    try:
                        agent_store.append_event(
                            turn_id,
                            payload,
                            sequence=event.get("sequence"),
                            event_type=event_type,
                        )
                    except agent_store.TurnTerminalError:
                        logger.debug(
                            "skip appending event for terminal turn=%s type=%s",
                            turn_id,
                            event_type,
                        )
                    if sink is not None:
                        sink(event)

            def driver(request: dict[str, Any]) -> dict[str, Any]:
                return asyncio.run(call_driver(request))

            def _coerce_tool_schema(value: Any) -> list[dict[str, Any]]:
                if not isinstance(value, list):
                    return []
                result: list[dict[str, Any]] = []
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "").strip()
                    if not name:
                        continue
                    descriptor = {
                        "name": name,
                        "description": str(item.get("description") or ""),
                        "input_schema": item.get("input_schema") or {"type": "object"},
                    }
                    result.append(descriptor)
                return result

            def _coerce_history_item(item: Any) -> dict[str, Any] | None:
                if not isinstance(item, dict):
                    return None
                role = str(item.get("role") or "")
                if role not in {"system", "user", "assistant", "tool"}:
                    return None
                content = item.get("content")
                if content is None and role not in {"assistant", "tool"}:
                    return None
                payload = {
                    "role": role,
                    "content": (
                        json.dumps(content, ensure_ascii=False)
                        if isinstance(content, (dict, list))
                        else "" if content is None else str(content)
                    ),
                }
                if item.get("tool_calls") is not None:
                    payload["tool_calls"] = item.get("tool_calls")
                if item.get("tool_call_id") is not None:
                    payload["tool_call_id"] = item.get("tool_call_id")
                return payload

            host: AgentSdkHost = AgentSdkHost(binding_path=self.library) if self.library else get_agent_sdk_host()
            normalized_context_refs = context_refs if isinstance(context_refs, list) else []
            normalized_attachments: list[dict[str, Any]] = []
            for attachment in attachments or []:
                if isinstance(attachment, dict):
                    normalized_attachments.append({
                        "type": str(attachment.get("type") or "text"),
                        "content": str(attachment.get("content") or ""),
                    })
            if asset_content:
                normalized_attachments.append({"type": "text", "content": str(asset_content)})
            history = [
                item
                for item in history_store.load_history(session_id)
                if _is_model_history_item(item)
            ]
            if history and history[-1] == {"role": "user", "content": content}:
                history.pop()
            tool_provider = self.tool_driver.registry if self.tool_driver is not None else knowledge_provider
            tool_descriptors: list[dict[str, Any]] = []
            try:
                describe_result = tool_provider.describe([])
                if asyncio.iscoroutine(describe_result):
                    describe_result = asyncio.run(describe_result)
                tool_descriptors = _coerce_tool_schema(describe_result)
            except Exception:
                logger.exception("Tool discovery unavailable while building SDK turn request")
                tool_descriptors = []
            normalized_input = {
                "text": content,
                "attachments": normalized_attachments,
                "context_refs": normalized_context_refs,
                "history": history,
                "tools": tool_descriptors,
            }
            sdk_messages = [_coerce_history_item(item) for item in history]
            sdk_messages = [item for item in sdk_messages if item is not None]
            sdk_messages.append({"role": "user", "content": content})
            handle = host.submit(
                turn_id,
                {
                    "schema_version": "1",
                    "request_id": turn_id,
                    "session_id": session_id,
                    "input": normalized_input,
                    "history": history,
                    "messages": sdk_messages,
                    "tools": tool_descriptors,
                    "model": model_config,
                    "model_override": model_override,
                    "approval_mode": "interactive",
                },
                driver=driver,
                on_event=on_event,
            )
            # Cancel may arrive between HTTP turn creation and native
            # registration. Re-check the durable intent immediately after the
            # token exists so the command always reaches the same native turn.
            current = agent_store.get_turn(turn_id)
            if current is not None and str(current.get("status")) == "cancelling":
                host.cancel(turn_id)
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
            if sink is not None:
                sink(event)
            self._finish(turn_id, session_id, "failed", event, event["payload"]["error"])

    def _seed_conversation_messages(
        self,
        session_id: str,
        user_message_id: str | None,
        assistant_message_id: str | None,
        content: str,
    ) -> None:
        # Route/CLI should remain intent-only. Host owns the canonical message
        # projection so conversations remain a single source of truth.
        if user_message_id:
            append_message(session_id, {
                "id": user_message_id,
                "role": "user",
                "message_type": "user_input",
                "content": content,
                "status": "completed",
            })
        if assistant_message_id:
            append_message(session_id, {
                "id": assistant_message_id,
                "role": "assistant",
                "message_type": "assistant_text",
                "content": "",
                "status": "streaming",
            })

    def _safe_update_message(self, session_id: str, message_id: str, patch: dict[str, Any]) -> None:
        try:
            update_message(session_id, message_id, patch)
        except ValueError as error:
            logger.debug("skip message projection because message not ready: session=%s message=%s err=%s", session_id, message_id, error)
        except Exception:  # noqa: BLE001 - projection boundary
            logger.exception("message projection failed for session=%s message=%s", session_id, message_id)

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
