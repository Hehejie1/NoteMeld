"""Export deterministic Python agent-core traces for SDK conformance tests.

The legacy Python core does not assign persisted session/turn/event IDs or
timestamps.  This test-only exporter supplies stable fixture identities while
leaving the core implementation untouched.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from tests.agent_core._base import EventRecorder, FakeModel, FakeModels, build_agent_tool, build_tool_call


SCHEMA_VERSION = "notemeld.agent.conformance.v1"
SCENARIOS = ("simple_answer", "parallel_tools", "abort", "steer", "max_turns")
FIXTURE_DIR = Path(__file__).resolve().parents[3] / "agent-sdk" / "fixtures" / "conformance"


def _tool_result(value: Any) -> dict[str, Any]:
    """Return the public ToolResult fields without Pydantic-version coupling."""
    if isinstance(value, dict):
        return {
            "call_id": value.get("call_id", ""),
            "content": value.get("content", []),
            "details": value.get("details", {}),
            "is_error": bool(value.get("is_error", False)),
        }
    return {
        "call_id": value.call_id,
        "content": value.content,
        "details": value.details,
        "is_error": value.is_error,
    }


def _message(message: Any) -> dict[str, Any]:
    return {
        "role": message.role,
        "content": message.content,
        "message_type": message.message_type,
        "tool_call_id": message.tool_call_id,
        "is_error": message.is_error,
        "tool_calls": message.tool_calls,
        "meta": message.meta,
    }


def _error(error: Any) -> dict[str, Any] | None:
    if error is None:
        return None
    return {"code": error.code, "message": error.message, "details": error.details}


def _final_state(agent: Any) -> dict[str, Any]:
    error = _error(agent.error)
    return {
        "status": "aborted" if error and error["code"] == "aborted" else "failed" if error else "completed",
        "turn_count": agent.turn_count,
        "error": error,
        "messages": [_message(message) for message in agent.messages],
    }


def _payload(event: Any, agent: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field in ("turn", "role", "delta", "tool_call", "call_id", "tool_name", "details"):
        value = getattr(event, field)
        if value is not None:
            payload[field] = value
    if event.result is not None:
        payload["result"] = _tool_result(event.result)
    if event.tool_results is not None:
        payload["tool_results"] = [_tool_result(result) for result in event.tool_results]
    if event.error is not None:
        payload["error"] = _error(event.error)
    if event.extra:
        payload["extra"] = event.extra
    if event.type.value == "agent_end":
        payload["final_state"] = _final_state(agent)
    return payload


def _row(scenario: str, sequence: int, event: Any, agent: Any) -> dict[str, Any]:
    turn_key = f"{event.turn:03d}" if event.turn is not None else "root"
    return {
        "schema_version": SCHEMA_VERSION,
        "scenario": scenario,
        "session_id": f"oracle-session-{scenario}",
        "turn_id": f"oracle-turn-{scenario}-{turn_key}",
        "event_id": f"oracle-event-{scenario}-{sequence:03d}",
        "sequence": sequence,
        "timestamp": f"2000-01-01T00:00:{sequence - 1:02d}Z",
        "type": event.type.value,
        "payload": _payload(event, agent),
    }


async def _run_simple_answer():
    from app.agent.core import Agent, AgentState

    recorder = EventRecorder()
    agent = Agent(
        initial_state=AgentState(system_prompt="fixture oracle", model=FakeModel()),
        models=FakeModels(turns=["oracle answer"]),
    )
    agent.subscribe(recorder)
    await agent.prompt("answer simply")
    await agent.wait_for_idle()
    return recorder.events, agent


async def _run_parallel_tools():
    from app.agent.core import Agent, AgentState

    fast_finished = asyncio.Event()

    async def slow(call_id, params, signal, on_update):  # noqa: ARG001
        await fast_finished.wait()
        return {"content": [{"type": "text", "text": "slow result"}], "details": {"name": "slow"}}

    async def fast(call_id, params, signal, on_update):  # noqa: ARG001
        fast_finished.set()
        return {"content": [{"type": "text", "text": "fast result"}], "details": {"name": "fast"}}

    recorder = EventRecorder()
    agent = Agent(
        initial_state=AgentState(
            model=FakeModel(),
            tools=[
                build_agent_tool("slow", mode="parallel", execute=slow),
                build_agent_tool("fast", mode="parallel", execute=fast),
            ],
        ),
        tool_execution="parallel",
        models=FakeModels(turns=[
            [build_tool_call("slow-call", "slow", {}), build_tool_call("fast-call", "fast", {})],
            "parallel complete",
        ]),
    )
    agent.subscribe(recorder)
    await agent.prompt("run tools in parallel")
    await agent.wait_for_idle()
    return recorder.events, agent


async def _run_abort():
    from app.agent.core import Agent, AgentState

    tool_started = asyncio.Event()

    async def wait_for_abort(call_id, params, signal, on_update):  # noqa: ARG001
        tool_started.set()
        await signal.wait()
        return {
            "content": [{"type": "text", "text": "tool observed abort"}],
            "details": {"aborted": signal.aborted},
        }

    recorder = EventRecorder()
    agent = Agent(
        initial_state=AgentState(model=FakeModel(), tools=[build_agent_tool("wait", mode="parallel", execute=wait_for_abort)]),
        models=FakeModels(turns=[[build_tool_call("abort-call", "wait", {})], "not reached"]),
    )
    agent.subscribe(recorder)
    task = asyncio.create_task(agent.prompt("begin cancellable work"))
    await tool_started.wait()
    await agent.abort("fixture abort")
    await task
    await agent.wait_for_idle()
    return recorder.events, agent


async def _run_steer():
    from app.agent.core import Agent, AgentState

    tool_started = asyncio.Event()
    release_tool = asyncio.Event()

    async def hold(call_id, params, signal, on_update):  # noqa: ARG001
        tool_started.set()
        await release_tool.wait()
        return {"content": [{"type": "text", "text": "corrected result"}]}

    recorder = EventRecorder()
    agent = Agent(
        initial_state=AgentState(model=FakeModel(), tools=[build_agent_tool("hold", mode="parallel", execute=hold)]),
        models=FakeModels(turns=[
            [build_tool_call("steer-call", "hold", {"query": "original"})],
            "steer acknowledged",
        ]),
    )
    agent.subscribe(recorder)
    task = asyncio.create_task(agent.prompt("start original query"))
    await tool_started.wait()
    await agent.steer("use the corrected query")
    release_tool.set()
    await task
    await agent.wait_for_idle()
    return recorder.events, agent


async def _run_max_turns():
    from app.agent.core import Agent, AgentState

    async def repeat(call_id, params, signal, on_update):  # noqa: ARG001
        return {"content": [{"type": "text", "text": f"completed {call_id}"}]}

    def another_call(turn, context):  # noqa: ARG001
        return [build_tool_call(f"max-call-{turn + 1}", "repeat", {})]

    recorder = EventRecorder()
    agent = Agent(
        initial_state=AgentState(model=FakeModel(), tools=[build_agent_tool("repeat", mode="parallel", execute=repeat)]),
        max_turns=3,
        models=FakeModels(turns=[another_call, another_call, another_call]),
    )
    agent.subscribe(recorder)
    await agent.prompt("continue until the turn limit")
    await agent.wait_for_idle()
    return recorder.events, agent


_RUNNERS = {
    "simple_answer": _run_simple_answer,
    "parallel_tools": _run_parallel_tools,
    "abort": _run_abort,
    "steer": _run_steer,
    "max_turns": _run_max_turns,
}


async def collect_oracle_rows(scenario: str) -> list[dict[str, Any]]:
    """Run one existing fake-driver scenario and normalize its emitted events."""
    if scenario not in _RUNNERS:
        raise ValueError(f"unknown oracle scenario: {scenario}")
    events, agent = await _RUNNERS[scenario]()
    return [_row(scenario, sequence, event, agent) for sequence, event in enumerate(events, start=1)]


def write_oracle_fixtures() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for scenario in SCENARIOS:
        rows = asyncio.run(collect_oracle_rows(scenario))
        target = FIXTURE_DIR / f"{scenario}.jsonl"
        target.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )


if __name__ == "__main__":
    write_oracle_fixtures()
