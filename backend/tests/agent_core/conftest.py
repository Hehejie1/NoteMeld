"""共享 fixture：fake models / fake tools / event recorder。

所有 agent-core 单测统一使用 FakeModels + FakeModel，不依赖真实 LLM 或 SQLite。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import pytest

from app.ai.provider import LLMContext
from app.ai.stream import StreamEvent, StreamEventType, CompleteResult


# ---------------------------------------------------------------------------
# Fake Model + Models：模仿 notemeld-ai 的 Model/Models 接口
# ---------------------------------------------------------------------------

@dataclass
class FakeModel:
    name: str = "fake-model"
    provider_id: str = "fake-prov"
    provider_name: str = "Fake"

    @property
    def provider(self):  # Models.stream 内部访问 _provider 也兼容
        return self

    @property
    def capabilities(self):
        return type("Caps", (), {"supports_tool_calling": True})()


@dataclass
class FakeModels:
    """可编程的 fake Models，支持多 turn：

    ``turns`` 里每一项是一个 callable(turn_count, llm_ctx) → 行为：
    - 返回 str → complete() 返回该内容，tool_calls 为空
    - 返回 list[dict] → complete() 返回空文本，tool_calls 为该列表
    - 返回 StreamEvent 列表 → stream() 产出对应事件序列
    """

    turns: list = field(default_factory=list)
    call_count: int = 0

    def get_model(self, provider_id=None, model_name=None) -> FakeModel:
        return FakeModel()

    # ---- complete() -----------------------------------------------------
    async def complete(
        self,
        model,
        ctx: LLMContext,
        options: dict | None = None,
        signal=None,
    ) -> CompleteResult:
        turn = self.call_count
        self.call_count += 1
        behavior = self.turns[turn] if turn < len(self.turns) else self.turns[-1]
        if callable(behavior):
            behavior = behavior(turn, ctx)
        result = CompleteResult()
        if isinstance(behavior, str):
            result.content = behavior
        elif isinstance(behavior, list) and all(isinstance(x, dict) for x in behavior):
            result.tool_calls = behavior
        elif isinstance(behavior, CompleteResult):
            return behavior
        return result

    # ---- stream() -------------------------------------------------------
    async def stream(
        self,
        model,
        ctx: LLMContext,
        options: dict | None = None,
        signal=None,
    ) -> AsyncIterator[StreamEvent]:
        turn = self.call_count
        self.call_count += 1
        behavior = self.turns[turn] if turn < len(self.turns) else self.turns[-1]
        if callable(behavior):
            behavior = behavior(turn, ctx)

        # 行为 a) 预生成的 StreamEvent 列表
        if isinstance(behavior, list) and behavior and isinstance(behavior[0], StreamEvent):
            for evt in behavior:
                if signal and isinstance(signal, asyncio.Event) and signal.is_set():
                    break
                yield evt
            return

        # 行为 b) str 文本 → 模拟流式 delta
        if isinstance(behavior, str):
            yield StreamEvent.start()
            yield StreamEvent.text_start()
            # 4 字符一片断，便于测试 message_update
            chunk_size = 4
            s = behavior
            for i in range(0, len(s), chunk_size):
                yield StreamEvent.text_delta(s[i:i + chunk_size])
            yield StreamEvent.text_end()
            yield StreamEvent.done()
            return

        # 行为 c) tool_calls list[dict] → 模拟 toolcall_start/delta/end
        if isinstance(behavior, list) and behavior and "function" in behavior[0]:
            yield StreamEvent.start()
            yield StreamEvent.text_start()
            yield StreamEvent.text_end()
            for tc in behavior:
                fn = tc.get("function") or {}
                call_id = tc.get("id", "call-x")
                name = fn.get("name", "")
                args = fn.get("arguments", "") or ""
                yield StreamEvent.toolcall_start(call_id, name)
                if args:
                    yield StreamEvent.toolcall_delta(call_id, args)
                yield StreamEvent.toolcall_end(call_id, name, args)
            yield StreamEvent.done()
            return

        if isinstance(behavior, Exception):
            yield StreamEvent.start()
            yield StreamEvent.error(behavior)
            return

        # 默认：空文本
        yield StreamEvent.start()
        yield StreamEvent.text_start()
        yield StreamEvent.text_end()
        yield StreamEvent.done()


# ---------------------------------------------------------------------------
# Event recorder：订阅 Agent 事件，用于序列断言
# ---------------------------------------------------------------------------

class EventRecorder:
    def __init__(self):
        self.events: list = []

    async def __call__(self, evt):
        self.events.append(evt)

    def types(self):
        return [e.type.value for e in self.events]

    def filter(self, etype):
        return [e for e in self.events if e.type == etype]


# ---------------------------------------------------------------------------
# Fake tool builder
# ---------------------------------------------------------------------------

def make_tool(name, description="desc", params=None, execution_mode="parallel", execute=None):
    from app.agent.core.tool import AgentTool
    if execute is None:
        async def _default(call_id, args, signal, on_update):
            return {"content": [{"type": "text", "text": f"result-{name}-{call_id}"}]}
        execute = _default
    return AgentTool(
        name=name,
        description=description,
        parameters=params or {"type": "object", "properties": {}},
        execution_mode=execution_mode,
        execute=execute,
    )


def make_tool_call(call_id, name, args_dict=None):
    args = "" if args_dict is None else __import__("json").dumps(args_dict)
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": args}}


@pytest.fixture
def recorder():
    return EventRecorder()


@pytest.fixture
def fake_models_cls():
    return FakeModels
