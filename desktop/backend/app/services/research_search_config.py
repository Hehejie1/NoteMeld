from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.utils.storage_paths import research_search_config_path


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled_scopes": ["academic", "github"],
    "web_provider": "disabled",
    "searxng_endpoint": "",
    "tavily_api_key": "",
    "github_token": "",
    "timeout_seconds": 15,
}

MANDATORY_LEARNING_SCOPES = ("academic", "github")


class ResearchSearchConfigManager:
    def __init__(self, path: Path | None = None):
        self.path = Path(path).resolve() if path is not None else research_search_config_path()

    def get_config(self) -> dict[str, Any]:
        payload = dict(DEFAULT_CONFIG)
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    payload.update(saved)
            except Exception:
                pass
        return payload

    def get_public_config(self) -> dict[str, Any]:
        payload = self.get_config()
        payload.pop("tavily_api_key", None)
        payload.pop("github_token", None)
        payload.pop("enabled_scopes", None)
        stored = self.get_config()
        payload["tavily_api_key_set"] = bool(stored.get("tavily_api_key"))
        payload["github_token_set"] = bool(stored.get("github_token"))
        return payload

    def get_learning_scopes(
        self, requested_scopes: list[str] | None = None
    ) -> list[str]:
        """Return the non-optional learning research scopes in stable order.

        Older callers may still send ``enabled_scopes`` or an explicit list. Those
        values can no longer disable academic/GitHub research. Web research is
        included only when its configured provider is actually usable.
        """

        del requested_scopes
        scopes = list(MANDATORY_LEARNING_SCOPES)
        config = self.get_config()
        web_provider = str(config.get("web_provider") or "disabled")
        searxng_endpoint = str(config.get("searxng_endpoint") or "").strip()
        parsed_searxng = urlparse(searxng_endpoint)
        searxng_is_usable = (
            parsed_searxng.scheme in {"http", "https"}
            and bool(parsed_searxng.netloc)
        )
        web_is_usable = (
            web_provider == "searxng"
            and searxng_is_usable
        ) or (
            web_provider == "tavily"
            and bool(str(config.get("tavily_api_key") or "").strip())
        )
        if web_is_usable:
            scopes.append("web")
        return scopes

    def update_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        payload = self.get_config()
        for key, value in updates.items():
            if key in {"tavily_api_key", "github_token"} and value == "":
                continue
            if key == "clear_tavily_api_key" and value:
                payload["tavily_api_key"] = ""
                continue
            if key == "clear_github_token" and value:
                payload["github_token"] = ""
                continue
            if key in DEFAULT_CONFIG:
                payload[key] = value
        self._write(payload)
        return self.get_public_config()

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
                tmp_name = handle.name
            Path(tmp_name).replace(self.path)
        finally:
            if tmp_name:
                Path(tmp_name).unlink(missing_ok=True)
