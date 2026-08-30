from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any
from urllib.parse import quote, urlparse, urlunparse


@dataclass(frozen=True)
class ConnectionCandidate:
    transport: str
    url: str


def connection_candidates(cloud_base_url: str, session_id: str, lan_endpoints: list[str] | None = None) -> list[ConnectionCandidate]:
    base = cloud_base_url.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("cloud base URL must be HTTP(S)")
    result = [ConnectionCandidate("lan", f"ws://{endpoint.strip()}/v1/relay/connect/{quote(session_id, safe='')}") for endpoint in (lan_endpoints or []) if endpoint.strip()]
    relay_scheme = "wss" if parsed.scheme == "https" else "ws"
    result.append(ConnectionCandidate("relay", urlunparse((relay_scheme, parsed.netloc, f"/v1/relay/connect/{quote(session_id, safe='')}", "", "", ""))))
    return result


def connect_with_fallback(candidates: list[ConnectionCandidate], connect: Callable[[ConnectionCandidate, float], Any], timeout_seconds: float = 3.0) -> tuple[Any, ConnectionCandidate]:
    if timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    last_error: Exception = RuntimeError("no connection candidates")
    for candidate in candidates:
        try:
            return connect(candidate, timeout_seconds), candidate
        except Exception as exc:  # noqa: BLE001 - fallback must try the next transport
            last_error = exc
    raise last_error
