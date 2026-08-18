from __future__ import annotations

import asyncio
from typing import Any, Callable, Mapping


class NoteMeldToolDriver:
    """Thin SDK ToolDriver adapter over a product capability provider."""

    def __init__(self, registry: Any = None, *, provider: Any = None):
        self.registry = registry or provider
        if self.registry is None:
            raise ValueError("tool registry or provider is required")

    async def describe(self, names: list[str]) -> list[dict[str, Any]]:
        return await self.registry.describe(names)

    async def invoke(
        self,
        call: Mapping[str, Any],
        context: Mapping[str, Any],
        on_progress: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        name = str(call.get("tool_name") or call.get("name") or "").strip()
        if not name:
            raise ValueError("tool name is required")
        call_id = str(call.get("call_id") or call.get("id") or "")
        if not call_id:
            raise ValueError("tool call id is required")
        arguments = call.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        get_tool = getattr(self.registry, "get_tool", None)
        if callable(get_tool) and get_tool(name) is None:
            raise ValueError(f"unknown tool: {name}")
        progress = on_progress or (lambda _event: None)

        async def update(payload: dict[str, Any]) -> None:
            result = progress(payload)
            if asyncio.iscoroutine(result):
                await result

        class Signal:
            aborted = False

        result = await self.registry.invoke(
            name,
            arguments,
            call_id,
            Signal(),
            update,
        )
        if isinstance(result, dict) and "call_id" not in result:
            result = {
                "call_id": call_id,
                "content": [{"type": "json", "json": result}],
                "structured_content": result,
            }
        if hasattr(result, "model_dump"):
            return result.model_dump()
        return dict(result)
