import os
import queue
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bindings" / "python"))

from notemeld_agent_sdk import Runtime  # noqa: E402
from notemeld_agent_sdk.runtime import ABI_SIGNATURES  # noqa: E402


def fake_driver(request):
    assert request["schema_version"] == "1"
    assert request["kind"] == "model.stream"
    return {
        "ok": True,
        "result": {
            "chunks": [{"type": "content_delta", "delta": "native hello"}],
            "completion": {
                "content": "native hello",
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {
                    "input_tokens": 2,
                    "output_tokens": 2,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                },
            },
        },
    }


def test_python_binding_loads_native_library_and_observes_terminal_event():
    library = os.environ["NOTEMELD_AGENT_SDK_LIBRARY"]
    with Runtime(library, driver=fake_driver) as runtime:
        for name, (restype, argtypes) in ABI_SIGNATURES.items():
            function = getattr(runtime._lib, name)
            assert function.restype is restype
            assert tuple(function.argtypes) == argtypes
        turn = runtime.submit_turn(
            {
                "schema_version": "1",
                "request_id": "33333333-3333-4333-8333-333333333333",
                "session_id": "python-smoke",
                "input": {"text": "hello", "attachments": [], "context_refs": []},
                "model_override": None,
                "approval_mode": "interactive",
            }
        )
        runtime.wait(turn, 5_000)
        events = []
        while True:
            try:
                events.append(runtime.events.get_nowait())
            except queue.Empty:
                break
        assert events[-1]["type"] == "turn.succeeded"
        assert all(event["schema_version"] == "1" for event in events)
