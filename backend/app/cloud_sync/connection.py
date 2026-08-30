from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from typing import Callable, Any
from urllib.parse import quote, urlparse, urlunparse

from .network import is_lan_address


@dataclass(frozen=True)
class ConnectionCandidate:
    transport: str
    url: str


def validate_cloud_base_url(value: str) -> str:
    """Validate a cloud URL before sending credentials over the network."""
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise ValueError("cloud base URL must be an absolute HTTP(S) URL without credentials or query parameters")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme == "http" and hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("remote cloud base URL must use HTTPS")
    return value.strip().rstrip("/")


def connection_candidates(cloud_base_url: str, session_id: str, lan_endpoints: list[str] | None = None) -> list[ConnectionCandidate]:
    base = validate_cloud_base_url(cloud_base_url)
    parsed = urlparse(base)
    result = []
    for endpoint in lan_endpoints or []:
        normalized = endpoint.strip()
        if not normalized:
            continue
        host, separator, port_text = normalized.rpartition(":")
        try:
            address = ipaddress.ip_address(host.strip("[]"))
            port = int(port_text)
        except ValueError as exc:
            raise ValueError("invalid LAN endpoint") from exc
        if (
            not separator
            or (address.version == 6 and not host.startswith("["))
            or "%" in host
            or not 1 <= port <= 65535
            or not is_lan_address(address)
        ):
            raise ValueError("LAN endpoint must use a private or local address")
        result.append(ConnectionCandidate("lan", f"ws://{normalized}/v1/lan/connect/{quote(session_id, safe='')}"))
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
