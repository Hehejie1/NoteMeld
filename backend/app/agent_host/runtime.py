from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

SDK_VERSION = "0.1.0"
SCHEMA_VERSION = "1"
ABI_VERSION = 2


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
    abi_version: int | None

    @classmethod
    def load(
        cls,
        *,
        binding_path: str | os.PathLike[str] | None = None,
        mode: str | None = None,
    ) -> "AgentSdkRuntime":
        selected = (mode or "rust").strip().lower()
        # The Rust SDK is the only supported Agent runtime.  Keeping a silent
        # Python/oracle fallback here creates a second state machine and can
        # make UI/CLI turns disagree about events and terminal status.
        if selected in {"python", "python-oracle", "legacy"}:
            raise AgentSdkUnavailable("legacy Python Agent runtime is removed; install the Rust SDK")
        if selected != "rust":
            raise AgentSdkUnavailable("unsupported agent runtime mode")
        try:
            binding = cls._load_binding(binding_path or "packaged")
            sdk_version = str(getattr(binding, "SDK_VERSION", ""))
            schema_version = str(getattr(binding, "SCHEMA_VERSION", ""))
            abi_version = getattr(binding, "ABI_VERSION", None)
            if abi_version is None:
                try:
                    abi_version = getattr(importlib.import_module("notemeld_agent_sdk"), "ABI_VERSION", None)
                except Exception:
                    abi_version = None
            try:
                abi_version = int(abi_version)
            except (TypeError, ValueError):
                raise AgentSdkUnavailable("SDK ABI version mismatch")
            if sdk_version != SDK_VERSION:
                raise AgentSdkUnavailable("SDK version mismatch")
            if schema_version != SCHEMA_VERSION:
                raise AgentSdkUnavailable("schema version mismatch")
            if abi_version != ABI_VERSION:
                raise AgentSdkUnavailable("SDK ABI version mismatch")
            return cls(binding, "rust", sdk_version, schema_version, abi_version)
        except AgentSdkUnavailable:
            raise
        except Exception as error:  # noqa: BLE001 - startup must fail closed
            raise AgentSdkUnavailable(_safe_reason(error)) from error

    @staticmethod
    def _load_binding(path: str | os.PathLike[str]) -> ModuleType:
        requested = str(path)
        if requested == "development":
            raise AgentSdkUnavailable("development SDK source loading is disabled; install the standalone wheel")
        if requested not in {"packaged"}:
            candidate = Path(requested).expanduser().resolve()
            if candidate.is_dir():
                raise AgentSdkUnavailable("SDK source directories are unsupported; install the standalone wheel")
            if candidate.is_file():
                # A native library path is permitted for artifact smoke tests, but
                # Python modules still come from the installed standalone package.
                os.environ.setdefault("NOTEMELD_AGENT_SDK_LIBRARY", str(candidate))
        # The package is installed from the standalone artifact and is importable
        # in the source venv or packaged sidecar.
        return importlib.import_module("notemeld_agent_sdk.runtime")

    @property
    def is_rollback(self) -> bool:
        return False
