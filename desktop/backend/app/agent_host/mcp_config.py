"""Product MCP configuration persistence; no legacy Agent tool imports."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

from app.utils.storage_paths import note_output_dir

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LOCK = threading.Lock()


def _path() -> Path:
    return note_output_dir() / "settings" / "mcp_servers.json"


def load_mcp_servers() -> dict[str, dict]:
    path = _path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    values = raw.get("servers") if isinstance(raw, dict) and "servers" in raw else raw
    if not isinstance(values, dict):
        return {}
    return {key: value for key, value in values.items() if _ID.fullmatch(str(key)) and isinstance(value, dict)}


def save_mcp_servers(servers: dict[str, dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "servers": servers}
    temporary = None
    with _LOCK:
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".mcp-", delete=False) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = handle.name
            Path(temporary).replace(path)
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)


def list_enabled_mcp_servers() -> dict[str, dict]:
    return {key: value for key, value in load_mcp_servers().items() if value.get("enabled") is True}
