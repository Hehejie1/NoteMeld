from app.agent_host.compat import agent_event_to_legacy, legacy_sse_frame


def test_message_delta_maps_to_legacy_delta_frame():
    event = {"type": "message.delta", "payload": {"delta": "hello"}}

    assert agent_event_to_legacy(event, answer="hello") == {
        "type": "delta",
        "content": "hello",
    }


def test_success_terminal_maps_to_done_with_answer_and_sources():
    event = {
        "type": "turn.succeeded",
        "payload": {"sources": [{"id": "source-1"}]},
    }

    assert agent_event_to_legacy(event, answer="hello") == {
        "type": "done",
        "answer": "hello",
        "sources": [{"id": "source-1"}],
    }


def test_failure_terminal_maps_to_stable_error_frame():
    event = {
        "type": "turn.failed",
        "payload": {"error": {"code": "model_unavailable", "message": "safe"}},
    }

    assert agent_event_to_legacy(event, answer="") == {
        "type": "error",
        "message": "safe",
    }


def test_legacy_sse_frame_is_valid_sse_data():
    assert legacy_sse_frame({"type": "delta", "content": "中"}) == (
        'data: {"type": "delta", "content": "中"}\n\n'
    )
