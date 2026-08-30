import httpx

from app.cloud_sync.client import CloudClient, CloudClientError


def test_cloud_client_login_and_session_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/auth/login":
            return httpx.Response(200, json={"code": 0, "msg": "success", "data": {"token": "nmt_test", "user_id": "u1"}})
        assert request.headers["authorization"] == "Bearer nmt_test"
        if request.url.path == "/v1/cloud/sessions":
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


def test_cloud_client_imports_local_snapshot():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/cloud/sessions/import"
        assert b'"source_session_id":"s1"' in request.content
        return httpx.Response(200, json={"code": 0, "msg": "success", "data": {"id": "cloud-1", "kind": "cloud_native"}})

    client = CloudClient("https://cloud.test", token="nmt_test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.import_session({"request_id": "r1", "source_session_id": "s1", "source_device_id": "desktop-1"})
    assert result["id"] == "cloud-1"
    client.close()


def test_cloud_client_quotes_workspace_paths():
    seen = []
    transport = httpx.MockTransport(lambda request: (seen.append(str(request.url)) or httpx.Response(200, json={"code": 0, "msg": "success", "data": {"ok": True}})))
    client = CloudClient("https://cloud.test", token="nmt_test", client=httpx.Client(transport=transport))
    client.read_workspace_file("default", "folder/a file?#.md")
    assert seen == ["https://cloud.test/v1/workspaces/default/files/folder/a%20file%3F%23.md"]
    client.close()


def test_cloud_client_rotates_and_clears_token():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/auth/rotate":
            assert request.headers["authorization"] == "Bearer nmt_old"
            return httpx.Response(200, json={"code": 0, "msg": "success", "data": {"token": "nmt_new"}})
        assert request.headers["authorization"] == "Bearer nmt_new"
        return httpx.Response(200, json={"code": 0, "msg": "success", "data": {"revoked": True}})

    client = CloudClient("https://cloud.test", token="nmt_old", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.rotate_token()["token"] == "nmt_new"
    assert client.revoke_token()["revoked"] is True
    assert client.token is None
    client.close()


def test_cloud_client_persists_token_store_across_instances():
    class Store:
        value = None
        def load(self): return self.value
        def save(self, token): self.value = token
        def clear(self): self.value = None

    store = Store()
    client = CloudClient("https://cloud.test", token="nmt_initial", token_store=store, client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 0, "msg": "success", "data": {"revoked": True}}))))
    client.revoke_token()
    assert store.value is None
    client.close()


def test_cloud_client_device_proof_contract():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.content))
        if request.url.path.endswith("/challenge"):
            return httpx.Response(200, json={"code": 0, "msg": "success", "data": {"challenge": "challenge-value"}})
        return httpx.Response(200, json={"code": 0, "msg": "success", "data": {"verified_until": 123}})

    client = CloudClient("https://cloud.test", token="nmt_test", device_id="device-a", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.request_device_challenge()["challenge"] == "challenge-value"
    assert client.verify_device_challenge("challenge-value", "signature-value")["verified_until"] == 123
    assert seen[0][1] == "/v1/devices/device-a/challenge"
    assert seen[1][1] == "/v1/devices/device-a/challenge/verify"
    client.close()


def test_cloud_client_extended_control_plane_contracts():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.raw_path, request.content))
        return httpx.Response(200, json={"code": 0, "msg": "success", "data": [] if request.method == "GET" else {"ok": True}})

    client = CloudClient("https://cloud.test", token="nmt_test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    client.revoke_device("device/id")
    client.rotate_device_key("device/id", "public-key")
    client.list_grants()
    client.delete_session("session/id")
    client.command_status("session/id", "command/id")
    client.list_commands("session/id", after=3, limit=7)
    client.list_share_tokens("session/id")
    client.revoke_share_token("share/id")
    assert [item[:2] for item in seen] == [
        ("DELETE", b"/v1/devices/device%2Fid"),
        ("POST", b"/v1/devices/device%2Fid/rotate-key"),
        ("GET", b"/v1/grants"),
        ("DELETE", b"/v1/cloud/sessions/session%2Fid"),
        ("GET", b"/v1/cloud/sessions/session%2Fid/commands/command%2Fid"),
        ("GET", b"/v1/cloud/sessions/session%2Fid/commands?after=3&limit=7"),
        ("GET", b"/v1/share-tokens?session_id=session%2Fid"),
        ("POST", b"/v1/share-tokens/share%2Fid/revoke"),
    ]
    client.close()


def test_cloud_client_admin_and_personal_token_contracts():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        raw_path = request.url.raw_path.decode().split("?", 1)[0]
        seen.append((request.method, raw_path, request.url.query, request.content))
        return httpx.Response(200, json={"code": 0, "msg": "success", "data": [] if request.method == "GET" else {"ok": True}})

    client = CloudClient("https://cloud.test", token="nmt_admin", client=httpx.Client(transport=httpx.MockTransport(handler)))
    client.list_personal_tokens()
    client.create_personal_token([], expires_at=123)
    client.revoke_personal_token("token/id")
    client.list_users()
    client.create_user("alice", "alice-password-123")
    client.update_user("user/id", disabled=True)
    client.delete_user("user/id")
    client.list_audits(25)
    assert [entry[:2] for entry in seen] == [
        ("GET", "/v1/auth/tokens"),
        ("POST", "/v1/auth/tokens"),
        ("POST", "/v1/auth/tokens/token%2Fid/revoke"),
        ("GET", "/v1/admin/users"),
        ("POST", "/v1/admin/users"),
        ("PUT", "/v1/admin/users/user%2Fid"),
        ("DELETE", "/v1/admin/users/user%2Fid"),
        ("GET", "/v1/admin/audits"),
    ]
    assert b'"scopes":[]' in seen[1][3] and b'"expires_at":123' in seen[1][3]
    assert seen[-1][2] == b"limit=25"
    client.close()
