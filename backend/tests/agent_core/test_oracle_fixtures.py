"""Cross-language conformance fixtures emitted by the Python Agent oracle."""
from __future__ import annotations

import json
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parents[3] / "agent-sdk" / "fixtures" / "conformance"
EXPECTED_FIXTURES = {
    "simple_answer.jsonl",
    "parallel_tools.jsonl",
    "abort.jsonl",
    "steer.jsonl",
    "max_turns.jsonl",
}
REQUIRED_FIELDS = {
    "schema_version",
    "scenario",
    "session_id",
    "turn_id",
    "event_id",
    "sequence",
    "timestamp",
    "type",
    "payload",
}


def _rows(name: str) -> list[dict]:
    return [json.loads(line) for line in (FIXTURE_DIR / f"{name}.jsonl").read_text().splitlines()]


def test_oracle_fixtures_are_gapless():
    """A missing or reordered persisted event must fail Rust conformance."""
    assert {path.name for path in FIXTURE_DIR.glob("*.jsonl")} == EXPECTED_FIXTURES

    for path in FIXTURE_DIR.glob("*.jsonl"):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert rows, f"{path.name} must contain oracle events"
        assert all(REQUIRED_FIELDS <= row.keys() for row in rows)
        assert {row["scenario"] for row in rows} == {path.stem}
        assert [row["sequence"] for row in rows] == list(range(1, len(rows) + 1))
        assert {row["schema_version"] for row in rows} == {"notemeld.agent.conformance.v1"}
        assert {row["session_id"] for row in rows} == {f"oracle-session-{path.stem}"}
        assert all(row["event_id"] == f"oracle-event-{path.stem}-{row['sequence']:03d}" for row in rows)


def test_oracle_fixtures_preserve_terminal_outcomes_and_tool_order():
    """A port must preserve the legacy core's observable control-flow contracts."""
    simple = _rows("simple_answer")
    assert simple[-1]["type"] == "agent_end"
    assert simple[-1]["payload"]["final_state"]["status"] == "completed"
    assert simple[-1]["payload"]["final_state"]["messages"][-1]["content"] == "oracle answer"

    parallel = _rows("parallel_tools")
    tool_ends = [row["payload"]["result"]["details"]["name"] for row in parallel if row["type"] == "tool_execution_end"]
    assert tool_ends == ["fast", "slow"]
    first_turn_end = next(row for row in parallel if row["type"] == "turn_end")
    assert [result["call_id"] for result in first_turn_end["payload"]["tool_results"]] == ["slow-call", "fast-call"]

    abort = _rows("abort")[-1]["payload"]["final_state"]
    assert abort["status"] == "aborted"
    assert abort["error"] == {"code": "aborted", "message": "fixture abort", "details": {}}

    steer_messages = _rows("steer")[-1]["payload"]["final_state"]["messages"]
    assert [message["role"] for message in steer_messages] == ["user", "assistant", "user", "toolResult", "assistant"]
    assert steer_messages[2]["meta"] == {"steer": True}
    assert steer_messages[2]["content"] == "use the corrected query"

    max_turns = _rows("max_turns")[-1]["payload"]["final_state"]
    assert max_turns["status"] == "failed"
    assert max_turns["error"] == {
        "code": "max_turns_reached",
        "message": "reached max_turns=3",
        "details": {"turn_count": 3},
    }
