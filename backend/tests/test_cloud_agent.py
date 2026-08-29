import httpx

from cloud.agent import CloudAgentError, DeterministicAgentRunner, OpenAICompatibleAgentRunner


def test_deterministic_cloud_agent_runner_is_explicit_fallback():
    runner = DeterministicAgentRunner()
    result = runner.complete(input_text="hello", messages=[])
    assert result.content == "Cloud Agent received: hello"
    assert result.model == "deterministic-cloud-agent"


def test_openai_compatible_runner_posts_provider_contract():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = request.content
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer"}}]})

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


def test_openai_compatible_runner_redacts_provider_failures():
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(500, text="provider secret payload")))
    runner = OpenAICompatibleAgentRunner(base_url="https://provider.example", model="model-a", api_key=None, client=client)
    try:
        runner.complete(input_text="hello", messages=[])
    except CloudAgentError as exc:
        assert str(exc) == "cloud agent provider request failed"
    else:
        raise AssertionError("expected CloudAgentError")
