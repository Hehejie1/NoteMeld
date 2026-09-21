from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Callable, Protocol

import httpx


LOGGER = logging.getLogger(__name__)


class CloudAgentError(RuntimeError):
    """A provider failure safe to expose at the cloud API boundary."""


@dataclass(frozen=True)
class AgentResult:
    content: str
    model: str
    usage: dict[str, int] | None = None


class CloudAgentRunner(Protocol):
    def complete(self, *, input_text: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, tool_handler: Callable[[str, dict[str, Any]], Any] | None = None, on_approval: Callable[[dict[str, Any]], None] | None = None) -> AgentResult:
        ...


class DeterministicAgentRunner:
    def __init__(self, model: str = "deterministic-cloud-agent"):
        self.model = model

    def complete(self, *, input_text: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, tool_handler: Callable[[str, dict[str, Any]], Any] | None = None, on_approval: Callable[[dict[str, Any]], None] | None = None) -> AgentResult:
        del messages
        del tools, tool_handler, on_approval
        return AgentResult(content=f"Cloud Agent received: {input_text}", model=self.model)

    def close(self) -> None:
        return None


class OpenAICompatibleAgentRunner:
    def __init__(self, *, base_url: str, model: str, api_key: str | None, timeout_seconds: float = 120.0, client: httpx.Client | None = None, max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, min(max_retries, 3))
        # Provider traffic must follow the configured endpoint directly.  In
        # particular, a local development provider on loopback must not be
        # rerouted through a developer's ambient HTTP(S) proxy; production
        # egress policy belongs to the Cloud deployment, not process-global
        # proxy environment variables.
        self._client = client or httpx.Client(timeout=timeout_seconds, trust_env=False)

    def close(self) -> None:
        self._client.close()

    def complete(self, *, input_text: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, tool_handler: Callable[[str, dict[str, Any]], Any] | None = None, on_approval: Callable[[dict[str, Any]], None] | None = None) -> AgentResult:
        del input_text, on_approval
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        conversation = [dict(message) for message in messages]
        try:
            for _ in range(8):
                request_json: dict[str, Any] = {"model": self.model, "messages": conversation, "stream": False}
                if tools:
                    request_json["tools"] = [{"type": "function", "function": tool} for tool in tools]
                response: httpx.Response | None = None
                for attempt in range(self.max_retries + 1):
                    response = self._client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=request_json,
                        timeout=self.timeout_seconds,
                    )
                    transient = response.status_code in {408, 429} or 500 <= response.status_code <= 504
                    if not transient or attempt >= self.max_retries:
                        break
                    retry_after = response.headers.get("retry-after")
                    try:
                        delay = min(2.0, max(0.0, float(retry_after))) if retry_after is not None else min(2.0, 0.25 * (2 ** attempt))
                    except ValueError:
                        delay = min(2.0, 0.25 * (2 ** attempt))
                    time.sleep(delay)
                assert response is not None
                response.raise_for_status()
                if len(response.content) > 4 * 1024 * 1024:
                    raise ValueError("provider response exceeds limit")
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError("invalid provider response")
                reported_model = body.get("model")
                if not isinstance(reported_model, str) or not reported_model:
                    raise ValueError("provider model mismatch")
                choices = body.get("choices")
                if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                    raise ValueError("invalid provider choices")
                choice = choices[0]
                finish_reason = choice.get("finish_reason")
                message = choice.get("message")
                if not isinstance(message, dict):
                    raise ValueError("invalid provider message")
                tool_calls = message.get("tool_calls")
                if tool_calls:
                    if finish_reason != "tool_calls" or not tool_handler or not isinstance(tool_calls, list) or len(tool_calls) > 16:
                        raise ValueError("provider requested unavailable tools")
                    conversation.append({"role": "assistant", "content": message.get("content"), "tool_calls": tool_calls})
                    call_ids: set[str] = set()
                    for call in tool_calls:
                        if not isinstance(call, dict) or call.get("type") != "function" or not isinstance(call.get("id"), str) or not call["id"]:
                            raise ValueError("invalid provider tool call")
                        if call["id"] in call_ids:
                            raise ValueError("duplicate provider tool call")
                        call_ids.add(call["id"])
                        function = call.get("function")
                        if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                            raise ValueError("invalid provider tool call")
                        try:
                            arguments = function.get("arguments", {})
                            if isinstance(arguments, str):
                                arguments = json.loads(arguments)
                            if not isinstance(arguments, dict):
                                raise ValueError("invalid tool arguments")
                            output = tool_handler(function["name"], arguments)
                        except Exception as exc:  # noqa: BLE001 - tool failures are model-visible, not provider failures
                            output = {"ok": False, "error": {"code": "tool_failed", "message": "workspace tool unavailable"}}
                            del exc
                        conversation.append({"role": "tool", "tool_call_id": str(call.get("id") or ""), "content": json.dumps(output, ensure_ascii=False) if not isinstance(output, str) else output})
                    continue
                if finish_reason != "stop":
                    raise ValueError("provider did not finish normally")
                content = message.get("content")
                if not isinstance(content, str) or not content:
                    raise ValueError("empty provider response")
                if len(content) > 100_000:
                    raise ValueError("provider response exceeds limit")
                usage = body.get("usage") if isinstance(body.get("usage"), dict) else None
                normalized_usage = {key: value for key, value in (usage or {}).items() if key in {"prompt_tokens", "completion_tokens", "total_tokens"} and type(value) is int}
                return AgentResult(content=content, model=self.model, usage=normalized_usage)
            raise ValueError("provider tool loop exceeded limit")
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise CloudAgentError("cloud agent provider request failed") from exc


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("retry-after")
    try:
        return min(2.0, max(0.0, float(retry_after))) if retry_after is not None else min(2.0, 0.25 * (2 ** attempt))
    except ValueError:
        return min(2.0, 0.25 * (2 ** attempt))


class AnthropicMessagesRunner:
    """Anthropic Messages API (/v1/messages)，x-api-key + anthropic-version。

    v1 仅转换 messages 最小子集（文本对话），不转发工具调用。
    """

    def __init__(self, *, base_url: str, model: str, api_key: str | None, timeout_seconds: float = 120.0, client: httpx.Client | None = None, max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, min(max_retries, 3))
        self._client = client or httpx.Client(timeout=timeout_seconds, trust_env=False)

    def close(self) -> None:
        self._client.close()

    def complete(self, *, input_text: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, tool_handler: Callable[[str, dict[str, Any]], Any] | None = None, on_approval: Callable[[dict[str, Any]], None] | None = None) -> AgentResult:
        del input_text, tools, tool_handler, on_approval
        if not self.api_key:
            raise CloudAgentError("cloud agent provider request failed")
        # Anthropic 要求 system 独立字段，且 messages 必须 user/assistant 交替
        system_parts: list[str] = []
        conversation: list[dict[str, str]] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            if role == "system":
                system_parts.append(text)
            elif role in {"user", "assistant"}:
                conversation.append({"role": role, "content": text})
        if not conversation or conversation[-1]["role"] != "user":
            conversation.append({"role": "user", "content": ""})
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        request_json: dict[str, Any] = {"model": self.model, "max_tokens": 4096, "messages": conversation}
        if system_parts:
            request_json["system"] = "\n".join(system_parts)
        try:
            response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                response = self._client.post(
                    f"{self.base_url}/v1/messages",
                    headers=headers,
                    json=request_json,
                    timeout=self.timeout_seconds,
                )
                transient = response.status_code in {408, 429} or 500 <= response.status_code <= 504
                if not transient or attempt >= self.max_retries:
                    break
                time.sleep(_retry_delay(response, attempt))
            assert response is not None
            response.raise_for_status()
            if len(response.content) > 4 * 1024 * 1024:
                raise ValueError("provider response exceeds limit")
            body = response.json()
            if not isinstance(body, dict) or body.get("role") != "assistant":
                raise ValueError("invalid provider response")
            if body.get("stop_reason") not in {"end_turn", "stop_sequence", "max_tokens"}:
                raise ValueError("provider did not finish normally")
            content_blocks = body.get("content")
            if not isinstance(content_blocks, list):
                raise ValueError("invalid provider content")
            text_parts = [
                block.get("text", "")
                for block in content_blocks
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            content = "".join(part for part in text_parts if isinstance(part, str))
            if not content:
                raise ValueError("empty provider response")
            usage = body.get("usage") if isinstance(body.get("usage"), dict) else None
            normalized_usage = None
            if usage:
                prompt_tokens = usage.get("input_tokens")
                completion_tokens = usage.get("output_tokens")
                if type(prompt_tokens) is int and type(completion_tokens) is int:
                    normalized_usage = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    }
            return AgentResult(content=content, model=self.model, usage=normalized_usage)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AssertionError) as exc:
            raise CloudAgentError("cloud agent provider request failed") from exc


class OllamaAgentRunner:
    """本地 Ollama (/api/chat)，无鉴权，stream=false。"""

    def __init__(self, *, base_url: str, model: str, api_key: str | None = None, timeout_seconds: float = 120.0, client: httpx.Client | None = None, max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, min(max_retries, 3))
        self._client = client or httpx.Client(timeout=timeout_seconds, trust_env=False)

    def close(self) -> None:
        self._client.close()

    def complete(self, *, input_text: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, tool_handler: Callable[[str, dict[str, Any]], Any] | None = None, on_approval: Callable[[dict[str, Any]], None] | None = None) -> AgentResult:
        del input_text, tools, tool_handler, on_approval
        conversation = []
        for message in messages:
            role = message.get("role")
            if role not in {"user", "assistant", "system"}:
                continue
            content = message.get("content", "")
            conversation.append({"role": role, "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)})
        request_json = {"model": self.model, "messages": conversation, "stream": False}
        try:
            response: httpx.Response | None = None
            for attempt in range(self.max_retries + 1):
                response = self._client.post(
                    f"{self.base_url}/api/chat",
                    headers={"Content-Type": "application/json"},
                    json=request_json,
                    timeout=self.timeout_seconds,
                )
                transient = response.status_code in {408, 429} or 500 <= response.status_code <= 504
                if not transient or attempt >= self.max_retries:
                    break
                time.sleep(_retry_delay(response, attempt))
            assert response is not None
            response.raise_for_status()
            if len(response.content) > 4 * 1024 * 1024:
                raise ValueError("provider response exceeds limit")
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("invalid provider response")
            message = body.get("message")
            if not isinstance(message, dict):
                raise ValueError("invalid provider message")
            content = message.get("content")
            if not isinstance(content, str) or not content:
                raise ValueError("empty provider response")
            return AgentResult(content=content, model=body.get("model") or self.model, usage=None)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AssertionError) as exc:
            raise CloudAgentError("cloud agent provider request failed") from exc


class CanonicalSdkAgentRunner:
    """Cloud adapter for the Rust SDK runtime.

    The SDK owns turn state, tool sequencing and terminal events. This class
    only translates the SDK driver callback to the configured provider and
    Cloud's existing tool capability boundary.
    """

    def __init__(
        self,
        *,
        native_library: str,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float = 120.0,
        max_retries: int = 2,
    ):
        try:
            from notemeld_agent_sdk import Runtime
        except ImportError as exc:  # pragma: no cover - exercised by production readiness
            raise RuntimeError("canonical Agent SDK Python binding is unavailable") from exc
        if not native_library or not os.path.isfile(native_library):
            raise RuntimeError("canonical Agent SDK native library is unavailable")
        self._Runtime = Runtime
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, min(max_retries, 3))
        self._client = httpx.Client(timeout=timeout_seconds, trust_env=False)
        self._runtimes: set[Any] = set()
        self._approval_runtimes: dict[str, Any] = {}
        self._lock = threading.Lock()
        self.native_library = native_library

    def close(self) -> None:
        with self._lock:
            runtimes = list(self._runtimes)
            self._runtimes.clear()
        for runtime in runtimes:
            runtime.close()
        with self._lock:
            self._approval_runtimes.clear()
        self._client.close()

    def resolve_approval(self, approval_id: str, decision: str) -> None:
        with self._lock:
            runtime = self._approval_runtimes.get(approval_id)
        if runtime is None:
            raise CloudAgentError("native approval runtime is unavailable")
        runtime.resolve_approval(approval_id, decision)

    def _model_driver(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url:
            raise CloudAgentError("cloud agent provider is not configured")
        payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            return {"ok": False, "error": {"code": "invalid_input", "message": "model request is missing messages"}}
        # The canonical SDK deliberately keeps message content provider-neutral:
        # assistant tool calls and tool results are embedded in `content`. The
        # Cloud provider adapter must translate that shape to OpenAI-compatible
        # wire messages before calling the configured provider.
        provider_messages: list[dict[str, Any]] = []
        for message in messages:
            if not isinstance(message, dict) or not isinstance(message.get("role"), str):
                return {"ok": False, "error": {"code": "invalid_input", "message": "model request contains an invalid message"}}
            role = message["role"]
            content = message.get("content", "")
            if role == "assistant" and isinstance(content, dict) and isinstance(content.get("tool_calls"), list):
                tool_calls = []
                for call in content["tool_calls"]:
                    if not isinstance(call, dict) or not isinstance(call.get("call_id"), str) or not isinstance(call.get("tool_name"), str) or not isinstance(call.get("arguments"), dict):
                        return {"ok": False, "error": {"code": "invalid_input", "message": "model request contains an invalid tool call"}}
                    tool_calls.append({
                        "id": call["call_id"],
                        "type": "function",
                        "function": {"name": call["tool_name"], "arguments": json.dumps(call["arguments"], separators=(",", ":"))},
                    })
                provider_messages.append({"role": "assistant", "content": content.get("content", ""), "tool_calls": tool_calls})
            elif role == "tool" and isinstance(content, dict):
                call_id = content.get("call_id")
                if not isinstance(call_id, str) or not call_id:
                    return {"ok": False, "error": {"code": "invalid_input", "message": "model request contains an invalid tool result"}}
                result_content = content.get("content", "")
                provider_messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result_content, ensure_ascii=False, separators=(",", ":"))})
            else:
                provider_messages.append({"role": role, "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, separators=(",", ":"))})
        raw_tools = payload.get("tools")
        tools = raw_tools if isinstance(raw_tools, list) else []
        provider_tools = []
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                return {"ok": False, "error": {"code": "invalid_input", "message": "model request contains an invalid tool"}}
            schema = tool.get("parameters", tool.get("input_schema", {"type": "object"}))
            if not isinstance(schema, dict):
                return {"ok": False, "error": {"code": "invalid_input", "message": "model request contains an invalid tool schema"}}
            provider_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": schema,
                },
            })
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        provider_payload: dict[str, Any] = {"model": self.model, "messages": provider_messages, "stream": False}
        if provider_tools:
            provider_payload["tools"] = provider_tools
        response: httpx.Response | None = None
        try:
            for attempt in range(getattr(self, "max_retries", 2) + 1):
                response = self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=provider_payload,
                    timeout=self.timeout_seconds,
                )
                transient = response.status_code in {408, 429} or 500 <= response.status_code <= 504
                if not transient or attempt >= getattr(self, "max_retries", 2):
                    break
                retry_after = response.headers.get("retry-after")
                try:
                    delay = min(2.0, max(0.0, float(retry_after))) if retry_after is not None else min(2.0, 0.25 * (2 ** attempt))
                except ValueError:
                    delay = min(2.0, 0.25 * (2 ** attempt))
                time.sleep(delay)
            assert response is not None
            response.raise_for_status()
        except (httpx.HTTPError, AssertionError) as exc:
            raise CloudAgentError("cloud agent provider request failed") from exc
        if len(response.content) > 4 * 1024 * 1024:
            raise CloudAgentError("cloud agent provider request failed")
        try:
            body = response.json()
        except (ValueError, TypeError) as exc:
            raise CloudAgentError("cloud agent provider request failed") from exc
        if not isinstance(body, dict) or not isinstance(body.get("model"), str) or not body["model"]:
            raise CloudAgentError("cloud agent provider request failed")
        choices = body.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise CloudAgentError("cloud agent provider request failed")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            raise CloudAgentError("cloud agent provider request failed")
        tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
        if len(tool_calls) > 16:
            raise CloudAgentError("cloud agent provider request failed")
        finish_reason = choice.get("finish_reason")
        if tool_calls and finish_reason != "tool_calls":
            raise CloudAgentError("cloud agent provider request failed")
        if not tool_calls and finish_reason != "stop":
            raise CloudAgentError("cloud agent provider request failed")
        normalized_calls = []
        call_ids: set[str] = set()
        for call in tool_calls:
            if not isinstance(call, dict) or call.get("type") != "function":
                raise CloudAgentError("cloud agent provider request failed")
            call_id = call.get("id")
            if not isinstance(call_id, str) or not call_id or call_id in call_ids:
                raise CloudAgentError("cloud agent provider request failed")
            call_ids.add(call_id)
            function = call.get("function")
            if not isinstance(function, dict) or not isinstance(function.get("name"), str) or not function["name"]:
                raise CloudAgentError("cloud agent provider request failed")
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except (TypeError, ValueError) as exc:
                    raise CloudAgentError("cloud agent provider request failed") from exc
            if not isinstance(arguments, dict):
                raise CloudAgentError("cloud agent provider request failed")
            normalized_calls.append({
                "call_id": call_id,
                "tool_name": function["name"],
                "arguments": arguments,
            })
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        content = message.get("content") if isinstance(message.get("content"), str) else ""
        if finish_reason == "stop" and (not content or len(content) > 100_000):
            raise CloudAgentError("cloud agent provider request failed")
        return {"ok": True, "result": {
            "chunks": ([{"type": "content_delta", "delta": content}] if content else []),
            "completion": {
                "content": content,
                "tool_calls": normalized_calls,
                "finish_reason": finish_reason,
                "usage": {
                    "input_tokens": usage.get("prompt_tokens", 0) if type(usage.get("prompt_tokens", 0)) is int else 0,
                    "output_tokens": usage.get("completion_tokens", 0) if type(usage.get("completion_tokens", 0)) is int else 0,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                },
            },
        }}

    def complete(self, *, input_text: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, tool_handler: Callable[[str, dict[str, Any]], Any] | None = None, on_approval: Callable[[dict[str, Any]], None] | None = None) -> AgentResult:
        events: list[dict[str, Any]] = []
        event_lock = threading.Lock()

        sdk_tools: list[dict[str, Any]] = []
        for tool in tools or []:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                raise CloudAgentError("cloud agent tool descriptor is invalid")
            schema = tool.get("input_schema", tool.get("parameters", {"type": "object"}))
            if not isinstance(schema, dict):
                raise CloudAgentError("cloud agent tool descriptor is invalid")
            descriptor = {
                "name": tool["name"],
                "description": str(tool.get("description", "")),
                "input_schema": schema,
                # These fields are consumed by the canonical runtime's
                # approval manager via `extra.tools`; they are intentionally
                # not forwarded to the OpenAI-compatible provider schema.
                "risk": tool.get("risk", "high"),
                "safe": bool(tool.get("safe", False)),
            }
            if isinstance(tool.get("policy"), dict):
                descriptor["policy"] = tool["policy"]
            sdk_tools.append(descriptor)

        def record_event(event: dict[str, Any]) -> None:
            with event_lock:
                events.append(event)
            if event.get("type") == "approval.required" and on_approval is not None:
                payload = event.get("payload")
                if isinstance(payload, dict):
                    approval_id = payload.get("approval_id")
                    if isinstance(approval_id, str) and approval_id:
                        with self._lock:
                            self._approval_runtimes[approval_id] = runtime
                    on_approval(dict(payload))

        def driver(request: dict[str, Any]) -> dict[str, Any]:
            kind = request.get("kind")
            if kind == "model.stream":
                return self._model_driver(request)
            if kind == "tool.invoke":
                payload = request.get("payload") if isinstance(request.get("payload"), dict) else {}
                name = payload.get("tool_name")
                arguments = payload.get("arguments")
                if not isinstance(name, str) or not isinstance(arguments, dict) or tool_handler is None:
                    return {"ok": False, "error": {"code": "unknown_tool", "message": "tool is unavailable"}}
                try:
                    return {"ok": True, "result": {"output": tool_handler(name, arguments)}}
                except Exception:
                    return {"ok": True, "result": {"output": {"ok": False, "error": {"code": "tool_failed", "message": "workspace tool unavailable"}}}}
            if kind == "tool.describe":
                return {"ok": True, "result": {"tools": []}}
            return {"ok": False, "error": {"code": "invalid_input", "message": "unsupported driver operation"}}

        runtime = self._Runtime(
            native_library=self.native_library,
            driver=driver,
            on_event=record_event,
        )
        with self._lock:
            self._runtimes.add(runtime)
        try:
            request = {
                "schema_version": "1",
                "request_id": str(uuid.uuid4()),
                "session_id": str(uuid.uuid4()),
                "input": {"text": input_text, "attachments": [], "context_refs": []},
                "tools": sdk_tools,
                "model_override": None,
                "approval_mode": "interactive",
                # The canonical runtime consumes model tools from the top-level
                # field, while its approval policy and durable context reader
                # use the host-owned `extra` envelope. Keep both views in sync
                # at this boundary instead of silently dropping capabilities.
                "extra": {"tools": sdk_tools, "history": messages[:-1] if messages and messages[-1].get("role") == "user" and messages[-1].get("content") == input_text else messages},
            }
            token = runtime.submit_turn(request)
            try:
                # Provider calls use the normal request timeout, but an
                # approval may legitimately remain pending for several
                # minutes. Keep the same native runtime alive until the
                # approval TTL has elapsed instead of converting that pause
                # into a provider failure.
                runtime.wait(token, max(int(self.timeout_seconds * 1000), 360_000))
            except Exception:
                with event_lock:
                    event_types = [event.get("type") for event in events]
                native_error = None
                last_error = getattr(runtime, "_last_error", None)
                if callable(last_error):
                    try:
                        native_error = str(last_error("turn wait failed"))
                    except Exception:
                        native_error = "unavailable"
                LOGGER.error("canonical cloud turn failed; events=%s native_error=%s", event_types, native_error)
                raise
            with event_lock:
                snapshot = list(events)
            terminal = next((event for event in reversed(snapshot) if event.get("type") == "turn.succeeded"), None)
            if not terminal:
                LOGGER.error("canonical cloud turn ended without success; events=%s payloads=%s", [event.get("type") for event in snapshot], [event.get("payload") for event in snapshot if event.get("type") == "turn.failed"])
                raise CloudAgentError("canonical Agent runtime did not succeed")
            content = "".join(
                event.get("payload", {}).get("delta", "")
                for event in snapshot
                if event.get("type") == "message.delta"
            )
            usage_payload = terminal.get("payload", {}).get("usage")
            usage = usage_payload if isinstance(usage_payload, dict) else None
            return AgentResult(content=content, model=self.model, usage=usage)
        finally:
            with self._lock:
                self._runtimes.discard(runtime)
                for approval_id, approval_runtime in list(self._approval_runtimes.items()):
                    if approval_runtime is runtime:
                        self._approval_runtimes.pop(approval_id, None)
            runtime.close()


def create_agent_runner(settings: Any) -> CloudAgentRunner:
    # DeterministicAgentRunner is a test/development fixture only.  Keep this
    # guard at the factory boundary so a production app cannot become ready by
    # silently losing its provider configuration.
    native_library = os.getenv("NOTEMELD_AGENT_SDK_LIBRARY", "")
    # The SDK runtime is selected by the immutable artifact, not by an
    # environment-only provider. The provider is normally resolved per
    # session from the authoritative Cloud model registry; an empty base URL
    # is therefore valid for the bootstrap runner and fails closed if used
    # before a model is configured.
    if native_library:
        return CanonicalSdkAgentRunner(
            native_library=native_library,
            base_url=settings.agent_base_url or "",
            model=settings.agent_model,
            api_key=settings.agent_api_key,
            timeout_seconds=settings.agent_timeout_seconds,
            max_retries=getattr(settings, "agent_max_retries", 2),
        )
    if getattr(settings, "deployment_env", "development") == "production":
        if not settings.agent_base_url:
            raise RuntimeError("production cloud requires a configured agent provider")
        raise RuntimeError("production cloud requires the canonical Agent SDK library")
    if settings.agent_base_url:
        return OpenAICompatibleAgentRunner(
            base_url=settings.agent_base_url,
            model=settings.agent_model,
            api_key=settings.agent_api_key,
            timeout_seconds=settings.agent_timeout_seconds,
            max_retries=getattr(settings, "agent_max_retries", 2),
        )
    return DeterministicAgentRunner()
