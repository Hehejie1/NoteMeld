import os
import secrets

from fastapi import Header, HTTPException, Request, status


SESSION_TOKEN_HEADER = "X-NoteMeld-Session"


def configured_session_token() -> str:
    return os.getenv("NOTEMELD_DESKTOP_SESSION_TOKEN", "").strip()


def require_session_token(
    request: Request,
    session_token: str = Header(default="", alias=SESSION_TOKEN_HEADER),
) -> None:
    expected = configured_session_token()
    if not expected or request.method.upper() == "OPTIONS":
        return

    if session_token and secrets.compare_digest(session_token, expected):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid NoteMeld desktop session",
    )
