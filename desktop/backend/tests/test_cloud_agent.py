import httpx
import pytest

from cloud.agent import CloudAgentError, CanonicalSdkAgentRunner, DeterministicAgentRunner, OpenAICompatibleAgentRunner, create_agent_runner


def test_deterministic_cloud_agent_runner_is_explicit_fallback():
    runner = DeterministicAgentRunner()
    result = runner.complete(input_text="hello", messages=[])
    assert result.content == "Cloud Agent received: hello"
    assert result.model == "deterministic-cloud-agent"


def test_production_factory_never_returns_deterministic_or_provider_only_runner(monkeypatch):
    settings = type("Settings", (), {
        "deployment_env": "production",
        "agent_base_url": None,
        "agent_model": "model-a",
        "agent_api_key": None,
        "agent_timeout_seconds": 10,
    })()
    with pytest.raises(RuntimeError, match="configured agent provider"):
        create_agent_runner(settings)

    settings.agent_base_url = "https://provider.example/v1"
    with pytest.raises(RuntimeError, match="canonical Agent SDK library"):
        create_agent_runner(settings)

    monkeypatch.setenv("NOTEMELD_AGENT_SDK_LIBRARY", "/does/not/exist/libnotemeld_agent.so")
    with pytest.raises(RuntimeError, match="canonical Agent SDK native library"):
        create_agent_runner(settings)


def test_provider_backed_development_acceptance_uses_canonical_runtime(monkeypatch):
    settings = type("Settings", (), {
        "deployment_env": "development",
        "agent_base_url": "http://127.0.0.1:19090/v1",
        "agent_model": "model-a",
        "agent_api_key": None,
        "agent_timeout_seconds": 10,
    })()
    monkeypatch.setenv("NOTEMELD_AGENT_SDK_LIBRARY", "/tmp/pinned/libnotemeld_agent.dylib")
    sentinel = object()
    monkeypatch.setattr("cloud.agent.CanonicalSdkAgentRunner", lambda **_: sentinel)

    assert create_agent_runner(settings) is sentinel


def test_canonical_bootstrap_does_not_require_environment_provider(monkeypatch):
    settings = type("Settings", (), {
        "deployment_env": "development",
        "agent_base_url": None,
        "agent_model": "model-a",
        "agent_api_key": None,
        "agent_timeout_seconds": 10,
    })()
    monkeypatch.setenv("NOTEMELD_AGENT_SDK_LIBRARY", "/tmp/pinned/libnotemeld_agent.dylib")
    sentinel = object()
    monkeypatch.setattr("cloud.agent.CanonicalSdkAgentRunner", lambda **kwargs: (sentinel, kwargs))

    runner, kwargs = create_agent_runner(settings)

    assert runner is sentinel
    assert kwargs["base_url"] == ""


def test_openai_compatible_runner_posts_provider_contract():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content
        return httpx.Response(200, json={"model": "model-a", "choices": [{"finish_reason": "stop", "message": {"content": "answer"}}]})

    runner = OpenAICompatibleAgentRunner(
        base_url="https://provider.example/v1/",
        model="model-a",
        api_key="secret-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = runner.complete(input_text="ignored", messages=[{"role": "user", "content": "hello"}])
    assert result.content == "answer" and result.model == "model-a"
    assert seen["url"] == "https://provider.example/v1/chat/completions"
    assert seen["auth"] == "Bearer secret-key"
    assert b"secret-key" not in seen["body"]


def test_openai_compatible_runner_accepts_provider_model_alias():
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(
        200,
        json={"model": "auto", "choices": [{"finish_reason": "stop", "message": {"content": "answer"}}]},
    )))
    runner = OpenAICompatibleAgentRunner(base_url="https://provider.example/v1", model="ark-code-latest", api_key=None, client=client)

    result = runner.complete(input_text="ignored", messages=[{"role": "user", "content": "hello"}])

    assert result.content == "answer"
    assert result.model == "ark-code-latest"


def test_openai_compatible_runner_redacts_provider_failures():
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(500, text="provider secret payload")))
    runner = OpenAICompatibleAgentRunner(base_url="https://provider.example", model="model-a", api_key=None, client=client)
    try:
        runner.complete(input_text="hello", messages=[])
    except CloudAgentError as exc:
        assert str(exc) == "cloud agent provider request failed"
    else:
        raise AssertionError("expected CloudAgentError")
    client.close()


def test_openai_compatible_runner_retries_transient_provider_failure():
    attempts = []

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(503, headers={"retry-after": "0"}, text="temporary outage")
        return httpx.Response(200, json={"model": "model-a", "choices": [{"finish_reason": "stop", "message": {"content": "recovered"}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    runner = OpenAICompatibleAgentRunner(base_url="https://provider.example", model="model-a", api_key=None, client=client, max_retries=2)
    assert runner.complete(input_text="hello", messages=[]).content == "recovered"
    assert len(attempts) == 2
    client.close()


def test_openai_compatible_runner_executes_bounded_workspace_tool_round():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(200, json={"model": "model-a", "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "workspace.list", "arguments": "{\"prefix\": \"docs\"}"}}]}}]})
        return httpx.Response(200, json={"model": "model-a", "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Here are the files."}}]})

    runner = OpenAICompatibleAgentRunner(base_url="https://provider.example", model="model-a", api_key=None, client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = runner.complete(
        input_text="list docs",
        messages=[{"role": "user", "content": "list docs"}],
        tools=[{"name": "workspace.list", "description": "list", "parameters": {"type": "object"}}],
        tool_handler=lambda name, args: {"ok": True, "name": name, "files": [{"path": args["prefix"] + "/a.md"}]},
    )
    assert result.content == "Here are the files."
    assert requests[1]["messages"][-1]["role"] == "tool"


def test_openai_compatible_runner_rejects_missing_provider_model():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                    json={"model": "", "choices": [{"finish_reason": "stop", "message": {"content": "answer"}}]},
            )
        )
    )
    runner = OpenAICompatibleAgentRunner(base_url="https://provider.example", model="model-a", api_key=None, client=client)
    try:
        runner.complete(input_text="hello", messages=[])
    except CloudAgentError as exc:
        assert str(exc) == "cloud agent provider request failed"
    else:
        raise AssertionError("expected CloudAgentError")
    client.close()


def test_openai_compatible_runner_rejects_truncated_terminal_answer():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={"model": "model-a", "choices": [{"finish_reason": "length", "message": {"content": "partial"}}]},
            )
        )
    )
    runner = OpenAICompatibleAgentRunner(base_url="https://provider.example", model="model-a", api_key=None, client=client)
    try:
        runner.complete(input_text="hello", messages=[])
    except CloudAgentError as exc:
        assert str(exc) == "cloud agent provider request failed"
    else:
        raise AssertionError("expected CloudAgentError")
    client.close()


def test_canonical_sdk_model_driver_forwards_tool_descriptors_to_provider():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"model": "model-a", "choices": [{"finish_reason": "stop", "message": {"content": "answer"}}]})

    runner = object.__new__(CanonicalSdkAgentRunner)
    runner.base_url = "https://provider.example/v1"
    runner.model = "model-a"
    runner.api_key = None
    runner.timeout_seconds = 10
    runner._client = httpx.Client(transport=httpx.MockTransport(handler))
    result = runner._model_driver({
        "payload": {
            "messages": [{"role": "user", "content": "list docs"}],
            "tools": [{"name": "workspace.list", "description": "list", "parameters": {"type": "object"}, "risk": "safe"}],
        }
    })
    assert result["ok"] is True
    assert seen["body"]["tools"] == [{"type": "function", "function": {"name": "workspace.list", "description": "list", "parameters": {"type": "object"}}}]
    runner._client.close()


def test_canonical_sdk_model_driver_retries_transient_provider_failure():
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, headers={"retry-after": "0"}, text="temporary outage")
        return httpx.Response(200, json={"model": "model-a", "choices": [{"finish_reason": "stop", "message": {"content": "answer"}}]})

    runner = object.__new__(CanonicalSdkAgentRunner)
    runner.base_url = "https://provider.example/v1"
    runner.model = "model-a"
    runner.api_key = None
    runner.timeout_seconds = 10
    runner.max_retries = 1
    runner._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = runner._model_driver({"payload": {"messages": [{"role": "user", "content": "hello"}]}})
        assert result["ok"] is True
        assert attempts == 2
    finally:
        runner._client.close()


@pytest.mark.parametrize(
    "response_json",
    [
        {"model": "model-a", "choices": [{"finish_reason": "length", "message": {"content": "partial"}}]},
        {"model": "model-a", "choices": [{"finish_reason": "stop", "message": {"content": ""}}]},
        {"model": "model-a", "choices": [{"finish_reason": "stop", "message": {"content": None, "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "workspace.list", "arguments": "{}"}}]}}]},
        {"model": "model-a", "choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "workspace.list", "arguments": "not-json"}}]}}]},
    ],
)
def test_canonical_sdk_model_driver_rejects_non_terminal_or_malformed_provider_responses(response_json):
    runner = object.__new__(CanonicalSdkAgentRunner)
    runner.base_url = "https://provider.example/v1"
    runner.model = "model-a"
    runner.api_key = None
    runner.timeout_seconds = 10
    runner._client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=response_json)))
    try:
        with pytest.raises(CloudAgentError, match="cloud agent provider request failed"):
            runner._model_driver({"payload": {"messages": [{"role": "user", "content": "hello"}]}})
    finally:
        runner._client.close()
