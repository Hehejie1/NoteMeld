import httpx

from app.cloud_sync.client import CloudClient, CloudClientError


def test_cloud_client_login_and_session_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/auth/login":
            return httpx.Response(200, json={"code": 0, "msg": "success", "data": {"token": "nmt_test", "user_id": "u1"}})
        assert request.headers["authorization"] == "Bearer nmt_test"
        if request.url.path == "/v1/sessions":
            assert request.headers["x-device-id"] == "device-a"
            return httpx.Response(200, json={"code": 0, "msg": "success", "data": {"id": "s1", "kind": "cloud_native"}})
        raise AssertionError(request.url.path)

    transport = httpx.MockTransport(handler)
    client = CloudClient("https://cloud.test", device_id="device-a", client=httpx.Client(transport=transport))
    assert client.login("password", account_id="u1")["token"] == "nmt_test"
    assert client.create_session("cloud_native")["id"] == "s1"
    client.close()


def test_cloud_client_projects_errors():
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={"code": 401, "msg": "invalid token"}))
    client = CloudClient("https://cloud.test", token="nmt_bad", client=httpx.Client(transport=transport))
    try:
        client.snapshot("s1")
    except CloudClientError as exc:
        assert exc.status_code == 401 and "invalid token" in str(exc)
    else:
        raise AssertionError("expected CloudClientError")
    client.close()


def test_cloud_client_quotes_workspace_paths():
    seen = []
    transport = httpx.MockTransport(lambda request: (seen.append(str(request.url)) or httpx.Response(200, json={"code": 0, "msg": "success", "data": {"ok": True}})))
    client = CloudClient("https://cloud.test", token="nmt_test", client=httpx.Client(transport=transport))
    client.read_workspace_file("default", "folder/a file?#.md")
    assert seen == ["https://cloud.test/v1/workspaces/default/files/folder/a%20file%3F%23.md"]
    client.close()
