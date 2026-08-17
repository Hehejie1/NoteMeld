from __future__ import annotations

from types import SimpleNamespace

from app.agent_host.host import AgentSdkHost


def test_host_creates_one_runtime_and_routes_turn_callbacks(monkeypatch):
    captured = {}

    class FakeRuntime:
        def __init__(self, *, driver, on_event):
            captured["driver"] = driver
            captured["on_event"] = on_event
            captured["submit_count"] = 0

        def submit_turn(self, _request):
            captured["submit_count"] += 1
            return captured["submit_count"]

        def wait(self, _token, _timeout):
            return None

        def cancel(self, _token):
            captured["cancelled"] = True

        def steer(self, _token, payload):
            captured["steered"] = payload

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(
        "app.agent_host.host.AgentSdkRuntime.load",
        lambda **_: SimpleNamespace(binding=SimpleNamespace(Runtime=FakeRuntime)),
    )
    host = AgentSdkHost()
    received = []
    driver_result = {"schema_version": "1", "ok": True}
    handle = host.submit(
        "turn-1",
        {"request_id": "turn-1"},
        driver=lambda request: received.append(request) or driver_result,
        on_event=received.append,
    )
    assert handle.token == 1
    assert host.runtime is host.runtime
    assert captured["submit_count"] == 1
    assert captured["driver"]({"turn_token": 1, "kind": "model.stream"}) == driver_result
    captured["on_event"]({"turn_id": "turn-1", "type": "turn.started"})
    assert received[-1]["type"] == "turn.started"
    host.cancel("turn-1")
    host.steer("turn-1", {"text": "continue"})
    assert captured["cancelled"] is True
    assert captured["steered"] == {"text": "continue"}
    host.forget("turn-1")
    host.close()
    assert captured["closed"] is True
