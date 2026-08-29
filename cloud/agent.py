from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Protocol

import httpx


class CloudAgentError(RuntimeError):
    """A provider failure safe to expose at the cloud API boundary."""


@dataclass(frozen=True)
class AgentResult:
    content: str
    model: str


class CloudAgentRunner(Protocol):
    def complete(self, *, input_text: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, tool_handler: Callable[[str, dict[str, Any]], Any] | None = None) -> AgentResult:
        ...


class DeterministicAgentRunner:
    def __init__(self, model: str = "deterministic-cloud-agent"):
        self.model = model

    def complete(self, *, input_text: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, tool_handler: Callable[[str, dict[str, Any]], Any] | None = None) -> AgentResult:
        del messages
        del tools, tool_handler
        return AgentResult(content=f"Cloud Agent received: {input_text}", model=self.model)

    def close(self) -> None:
        return None


class OpenAICompatibleAgentRunner:
    def __init__(self, *, base_url: str, model: str, api_key: str | None, timeout_seconds: float = 120.0, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def complete(self, *, input_text: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None, tool_handler: Callable[[str, dict[str, Any]], Any] | None = None) -> AgentResult:
        del input_text
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        conversation = [dict(message) for message in messages]
        try:
            for _ in range(8):
                request_json: dict[str, Any] = {"model": self.model, "messages": conversation, "stream": False}
                if tools:
                    request_json["tools"] = [{"type": "function", "function": tool} for tool in tools]
                response = self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=request_json,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                body = response.json()
                message = body["choices"][0]["message"]
                if not isinstance(message, dict):
                    raise ValueError("invalid provider message")
                tool_calls = message.get("tool_calls")
                if tool_calls:
                    if not tool_handler or not isinstance(tool_calls, list) or len(tool_calls) > 16:
                        raise ValueError("provider requested unavailable tools")
                    conversation.append({"role": "assistant", "content": message.get("content"), "tool_calls": tool_calls})
                    for call in tool_calls:
                        if not isinstance(call, dict) or call.get("type") != "function":
                            raise ValueError("invalid provider tool call")
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
                content = message.get("content")
                if not isinstance(content, str) or not content:
                    raise ValueError("empty provider response")
                if len(content) > 100_000:
                    raise ValueError("provider response exceeds limit")
                return AgentResult(content=content, model=self.model)
            raise ValueError("provider tool loop exceeded limit")
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise CloudAgentError("cloud agent provider request failed") from exc


def create_agent_runner(settings: Any) -> CloudAgentRunner:
    if settings.agent_base_url:
        return OpenAICompatibleAgentRunner(
            base_url=settings.agent_base_url,
            model=settings.agent_model,
            api_key=settings.agent_api_key,
            timeout_seconds=settings.agent_timeout_seconds,
        )
    return DeterministicAgentRunner()
