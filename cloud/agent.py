from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import httpx


class CloudAgentError(RuntimeError):
    """A provider failure safe to expose at the cloud API boundary."""


@dataclass(frozen=True)
class AgentResult:
    content: str
    model: str


class CloudAgentRunner(Protocol):
    def complete(self, *, input_text: str, messages: list[dict[str, str]]) -> AgentResult:
        ...


class DeterministicAgentRunner:
    def __init__(self, model: str = "deterministic-cloud-agent"):
        self.model = model

    def complete(self, *, input_text: str, messages: list[dict[str, str]]) -> AgentResult:
        del messages
        return AgentResult(content=f"Cloud Agent received: {input_text}", model=self.model)


class OpenAICompatibleAgentRunner:
    def __init__(self, *, base_url: str, model: str, api_key: str | None, timeout_seconds: float = 120.0, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def complete(self, *, input_text: str, messages: list[dict[str, str]]) -> AgentResult:
        del input_text
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": self.model, "messages": messages, "stream": False},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content:
                raise ValueError("empty provider response")
            if len(content) > 100_000:
                raise ValueError("provider response exceeds limit")
            return AgentResult(content=content, model=self.model)
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
