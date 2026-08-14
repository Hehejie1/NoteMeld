"""共享 fixture：fake models / fake tools / event recorder / async runner。

P1 agent-core 所有单测统一使用 unittest 基类 + asyncio.run() 跑异步，
不依赖 pytest-asyncio 插件，保持与 backend/tests/ai 一致。
"""

from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import dataclass, field
from typing import AsyncIterator

from app.ai.provider import LLMContext
from app.ai.stream import StreamEvent, CompleteResult


# ---------------------------------------------------------------------------
# 模块级 tool factory helper
# ---------------------------------------------------------------------------

def build_agent_tool(name, description="desc", params=None, mode="parallel", execute=None):
    from app.agent.core.tool import AgentTool
    if execute is None:
        async def _default(call_id, args, signal, on_update):
            return {"content": [{"type": "text", "text": f"result-{name}-{call_id}"}]}
        execute = _default
    return AgentTool(
        name=name, description=description,
        parameters=params or {"type": "object", "properties": {}},
        execution_mode=mode, execute=execute,
    )


def build_tool_call(call_id, name, args_dict=None):
    args = "" if args_dict is None else json.dumps(args_dict)
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": args}}


# ---------------------------------------------------------------------------
# Fake Model + Models：模仿 notemeld-ai 的 Model/Models 接口
# ---------------------------------------------------------------------------

@dataclass
class FakeModel:
    name: str = "fake-model"
    provider_id: str = "fake-prov"
    provider_name: str = "Fake"

    @property
    def provider(self):
        return self

    @property
    def capabilities(self):
        return type("Caps", (), {"supports_tool_calling": True})()


@dataclass
class FakeModels:
    """可编程的 fake Models。

    ``turns`` 项可以是：
    - str：纯文本回复
    - list[dict]：每个 dict 是一个 tool_call 结构，``{"id","type":"function","function":{...}}``
    - callable(turn_index, LLMContext) → 上述任一类型
    - Exception：作为错误事件返回
    """

    turns: list = field(default_factory=list)
    call_count: int = 0

    def get_model(self, provider_id=None, model_name=None) -> FakeModel:  # noqa: ARG002
        return FakeModel()

    async def complete(self, model, ctx: LLMContext, options=None, signal=None) -> CompleteResult:  # noqa: ARG002
        return self._next_result(model, ctx)

    async def stream(self, model, ctx: LLMContext, options=None, signal=None) -> AsyncIterator[StreamEvent]:  # noqa: ARG002
        events = self._next_events(model, ctx)
        for evt in events:
            yield evt

    # -- internal --------------------------------------------------------
    def _resolve_behavior(self, ctx: LLMContext):
        i = self.call_count
        self.call_count += 1
        if not self.turns:
            return ""
        b = self.turns[i] if i < len(self.turns) else self.turns[-1]
        if callable(b):
            b = b(i, ctx)
        return b

    def _next_result(self, model, ctx: LLMContext) -> CompleteResult:  # noqa: ARG002
        b = self._resolve_behavior(ctx)
        result = CompleteResult()
        if isinstance(b, str):
            result.content = b
        elif isinstance(b, list) and b and isinstance(b[0], dict) and "function" in b[0]:
            result.tool_calls = [dict(x) for x in b]
        elif isinstance(b, CompleteResult):
            return b
        return result

    def _next_events(self, model, ctx: LLMContext) -> list:  # noqa: ARG002
        b = self._resolve_behavior(ctx)

        if isinstance(b, list) and b and isinstance(b[0], StreamEvent):
            return list(b)

        if isinstance(b, str):
            evts = [StreamEvent.start(), StreamEvent.text_start()]
            chunk = 4
            for i in range(0, len(b), chunk):
                evts.append(StreamEvent.text_delta(b[i:i + chunk]))
            evts.append(StreamEvent.text_end())
            evts.append(StreamEvent.done())
            return evts

        if isinstance(b, list) and b and isinstance(b[0], dict) and "function" in b[0]:
            evts = [StreamEvent.start(), StreamEvent.text_start(), StreamEvent.text_end()]
            for tc in b:
                fn = tc.get("function") or {}
                cid = tc.get("id") or f"call-{self.call_count - 1}-{fn.get('name')}"
                name = fn.get("name", "")
                args = fn.get("arguments", "") or ""
                evts.append(StreamEvent.toolcall_start(cid, name))
                if args:
                    evts.append(StreamEvent.toolcall_delta(cid, args))
                evts.append(StreamEvent.toolcall_end(cid, name, args))
            evts.append(StreamEvent.done())
            return evts

        if isinstance(b, Exception):
            return [StreamEvent.start(), StreamEvent.error(b)]

        return [StreamEvent.start(), StreamEvent.text_start(), StreamEvent.text_end(), StreamEvent.done()]


# ---------------------------------------------------------------------------
# Event recorder
# ---------------------------------------------------------------------------

class EventRecorder:
    def __init__(self):
        self.events = []

    async def __call__(self, evt):
        self.events.append(evt)

    def types(self):
        return [e.type.value for e in self.events]


# ---------------------------------------------------------------------------
# 基类：unittests 统一跑 asyncio.run()
# ---------------------------------------------------------------------------

class AgentCoreTestCase(unittest.TestCase):
    """统一基类：提供 _run(coro)、make_tool、make_tool_call、recorder 等 helper。

    使用 ``_run = asyncio.run`` 同步执行，不依赖 pytest-asyncio 插件。
    """

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    @staticmethod
    def make_tool(name, description="desc", params=None, mode="parallel", execute=None):
        return build_agent_tool(name, description, params, mode, execute)

    @staticmethod
    def make_tool_call(call_id, name, args_dict=None):
        return build_tool_call(call_id, name, args_dict)

    @staticmethod
    def recorder():
        return EventRecorder()


__all__ = [
    "FakeModel", "FakeModels", "EventRecorder", "AgentCoreTestCase", "LLMContext",
    "build_agent_tool", "build_tool_call",
]
