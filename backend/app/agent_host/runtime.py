from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

SDK_VERSION = "0.1.0"
SCHEMA_VERSION = "1"


class AgentSdkUnavailable(RuntimeError):
    """Raised when the configured SDK cannot be loaded safely."""


def _safe_reason(error: Exception) -> str:
    # Provider configuration and payloads must never cross the startup boundary.
    text = str(error).lower()
    if any(token in text for token in ("api_key", "apikey", "authorization", "bearer", "token")):
        return "SDK binding initialization failed"
    return "SDK binding initialization failed: " + str(error)[:160]


@dataclass(frozen=True)
class AgentSdkRuntime:
    binding: ModuleType | None
    mode: str
    sdk_version: str | None
    schema_version: str | None

    @classmethod
    def load(
        cls,
        *,
        binding_path: str | os.PathLike[str] | None = None,
        mode: str | None = None,
    ) -> "AgentSdkRuntime":
        selected = (mode or os.getenv("NOTEMELD_AGENT_MODE") or "rust").strip().lower()
        if selected in {"python", "python-oracle", "legacy"}:
            raise AgentSdkUnavailable("legacy Python agent runtime is disabled")
        if selected != "rust":
            raise AgentSdkUnavailable("unsupported agent runtime mode")
        try:
            binding = cls._load_binding(binding_path or "packaged")
            sdk_version = str(getattr(binding, "SDK_VERSION", ""))
            schema_version = str(getattr(binding, "SCHEMA_VERSION", ""))
            if sdk_version != SDK_VERSION:
                raise AgentSdkUnavailable("SDK version mismatch")
            if schema_version != SCHEMA_VERSION:
                raise AgentSdkUnavailable("schema version mismatch")
            return cls(binding, "rust", sdk_version, schema_version)
        except AgentSdkUnavailable:
            raise
        except Exception as error:  # noqa: BLE001 - startup must fail closed
            raise AgentSdkUnavailable(_safe_reason(error)) from error

    @staticmethod
    def _load_binding(path: str | os.PathLike[str]) -> ModuleType:
        requested = str(path)
        if requested not in {"development", "packaged"}:
            candidate = Path(requested)
            if candidate.is_dir():
                python_root = candidate / "bindings" / "python"
                if (python_root / "notemeld_agent_sdk").is_dir():
                    os.environ.setdefault("NOTEMELD_AGENT_SDK_PYTHON_PATH", str(python_root))
                else:
                    os.environ.setdefault("NOTEMELD_AGENT_SDK_LIBRARY", str(candidate))
        if requested == "development":
            configured_root = os.getenv("NOTEMELD_AGENT_SDK_PYTHON_PATH", "").strip()
            if configured_root:
                source_root = Path(configured_root).expanduser().resolve()
                if not (source_root / "notemeld_agent_sdk").is_dir():
                    raise AgentSdkUnavailable("external SDK Python path is invalid")
                if str(source_root) not in sys.path:
                    sys.path.insert(0, str(source_root))
        # The package is installed in production and is importable in the sidecar.
        return importlib.import_module("notemeld_agent_sdk.runtime")
