import os

from fastapi import HTTPException, Request


LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def validate_mcp_request(request: Request) -> None:
    host = request.client.host if request.client else ""
    require_token = os.getenv("NOTEMELD_MCP_REQUIRE_TOKEN", "").lower() == "true"
    if host in LOCAL_HOSTS and not require_token:
        return

    expected_token = os.getenv("NOTEMELD_MCP_TOKEN", "")
    provided = request.headers.get("authorization", "")
    if expected_token and provided == f"Bearer {expected_token}":
        return

    raise HTTPException(status_code=401, detail="MCP token required")
