from __future__ import annotations

import ctypes
import hashlib
import importlib
import json
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Any

from app.agent_host.sdk_artifact_pin import (
    ABI_VERSION as PINNED_ABI_VERSION,
    ARTIFACT_MANIFEST_SHA256,
    NATIVE_LIBRARY_SHA256,
    PYTHON_WHEEL_SHA256,
    SCHEMA_VERSION as PINNED_SCHEMA_VERSION,
    SDK_SOURCE_COMMIT,
    SDK_VERSION as PINNED_SDK_VERSION,
)

SDK_VERSION = PINNED_SDK_VERSION
SCHEMA_VERSION = PINNED_SCHEMA_VERSION
# The standalone SDK publishes abi-v1.json in every wheel/native artifact.
# abi-v2.json is a future contract and is not part of the current release.
ABI_VERSION = PINNED_ABI_VERSION
_ARTIFACT_METADATA = "notemeld-agent-sdk.json"
_ABI_CONTRACT = f"abi-v{ABI_VERSION}.json"


class AgentSdkUnavailable(RuntimeError):
    """Raised when the configured SDK cannot be loaded safely."""


def _safe_reason(_error: Exception) -> str:
    # Never echo dependency errors: loader failures may contain a local path,
    # environment value, provider configuration, or payload fragment.
    return "Agent SDK binding initialization failed"


@dataclass(frozen=True)
class AgentSdkRuntime:
    binding: ModuleType | None
    mode: str
    sdk_version: str | None
    schema_version: str | None
    abi_version: int | None
    native_library: str | None = None
    source_commit: str | None = None
    artifact_manifest_sha256: str | None = None

    @classmethod
    def load(
        cls,
        *,
        binding_path: str | os.PathLike[str] | None = None,
        mode: str | None = None,
    ) -> "AgentSdkRuntime":
        selected = (mode or "rust").strip().lower()
        # Reject legacy modes before touching any loader. There is no second
        # runtime to call when the standalone SDK is unavailable.
        if selected in {"python", "python-oracle", "legacy"}:
            raise AgentSdkUnavailable("legacy Python Agent runtime is removed; install the Rust SDK")
        if selected != "rust":
            raise AgentSdkUnavailable("unsupported agent runtime mode")

        requested = binding_path or "packaged"
        try:
            binding = cls._load_binding(requested)
            contract, metadata = cls._read_artifact_contract(binding)
            sdk_version = str(getattr(binding, "SDK_VERSION", ""))
            schema_version = str(getattr(binding, "SCHEMA_VERSION", ""))
            try:
                abi_version = int(contract["abi_version"])
            except (KeyError, TypeError, ValueError) as error:
                raise AgentSdkUnavailable("Agent SDK ABI version mismatch") from error

            if sdk_version != SDK_VERSION or contract.get("sdk_version") != SDK_VERSION:
                raise AgentSdkUnavailable("Agent SDK version mismatch")
            if schema_version != SCHEMA_VERSION or contract.get("schema_version") != SCHEMA_VERSION:
                raise AgentSdkUnavailable("Agent SDK schema version mismatch")
            if abi_version != ABI_VERSION:
                raise AgentSdkUnavailable("Agent SDK ABI version mismatch")

            target = metadata["target_triples"][0]
            expected_manifest = ARTIFACT_MANIFEST_SHA256.get(target)
            if metadata.get("source_commit") not in (None, SDK_SOURCE_COMMIT):
                raise AgentSdkUnavailable("Agent SDK source commit mismatch")
            if metadata.get("artifact_manifest_sha256") not in (None, expected_manifest):
                raise AgentSdkUnavailable("Agent SDK artifact hash mismatch")

            native_library = cls._probe_native_artifact(binding, requested, contract)
            expected_native = NATIVE_LIBRARY_SHA256.get(target)
            if expected_native is None or native_library is None:
                raise AgentSdkUnavailable("Agent SDK artifact hash mismatch")
            if cls._sha256(Path(native_library)) != expected_native:
                raise AgentSdkUnavailable("Agent SDK artifact hash mismatch")
            configured_wheel = os.getenv("NOTEMELD_AGENT_SDK_WHEEL", "").strip()
            if configured_wheel:
                expected_wheel = PYTHON_WHEEL_SHA256.get(target)
                if expected_wheel is None or not Path(configured_wheel).is_file():
                    raise AgentSdkUnavailable("Agent SDK artifact hash mismatch")
                if cls._sha256(Path(configured_wheel)) != expected_wheel:
                    raise AgentSdkUnavailable("Agent SDK artifact hash mismatch")
            return cls(
                binding=binding,
                mode="rust",
                sdk_version=sdk_version,
                schema_version=schema_version,
                abi_version=abi_version,
                native_library=native_library,
                source_commit=metadata.get("source_commit", SDK_SOURCE_COMMIT),
                artifact_manifest_sha256=metadata.get("artifact_manifest_sha256", expected_manifest),
            )
        except AgentSdkUnavailable:
            raise
        except ModuleNotFoundError as error:
            missing_name = str(error.name or "")
            if missing_name == "notemeld_agent_sdk" or missing_name.startswith("notemeld_agent_sdk."):
                raise AgentSdkUnavailable("Agent SDK is not installed") from error
            raise AgentSdkUnavailable(_safe_reason(error)) from error
        except Exception as error:  # noqa: BLE001 - startup must fail closed
            raise AgentSdkUnavailable(_safe_reason(error)) from error

    @staticmethod
    def _load_binding(path: str | os.PathLike[str]) -> ModuleType:
        requested = str(path)
        if requested == "development":
            raise AgentSdkUnavailable("development SDK source loading is disabled; install the standalone wheel")
        if requested != "packaged":
            candidate = Path(requested).expanduser().resolve()
            if candidate.is_dir():
                raise AgentSdkUnavailable("SDK source directories are unsupported; install the standalone wheel")
            if not candidate.is_file():
                raise AgentSdkUnavailable("Agent SDK native artifact is missing")
        # Normal package import is the only Python binding source. The wheel's
        # versioned resources and native library are validated separately.
        return importlib.import_module("notemeld_agent_sdk.runtime")

    @staticmethod
    def _read_artifact_contract(binding: ModuleType) -> tuple[dict[str, Any], dict[str, Any]]:
        package_name = str(getattr(binding, "__package__", "") or "")
        if package_name != "notemeld_agent_sdk":
            raise AgentSdkUnavailable("Agent SDK artifact metadata is missing or invalid")
        try:
            package = resources.files(package_name)
            metadata = json.loads(package.joinpath(_ARTIFACT_METADATA).read_text(encoding="utf-8"))
            contract = json.loads(package.joinpath(_ABI_CONTRACT).read_text(encoding="utf-8"))
        except (FileNotFoundError, ModuleNotFoundError, OSError, TypeError, ValueError) as error:
            raise AgentSdkUnavailable("Agent SDK artifact metadata is missing or invalid") from error

        if not isinstance(metadata, dict) or not isinstance(contract, dict):
            raise AgentSdkUnavailable("Agent SDK artifact metadata is missing or invalid")
        if metadata.get("sdk_version") != SDK_VERSION:
            raise AgentSdkUnavailable("Agent SDK version mismatch")
        if metadata.get("schema_version") != SCHEMA_VERSION:
            raise AgentSdkUnavailable("Agent SDK schema version mismatch")
        if metadata.get("binding_version") != SDK_VERSION:
            raise AgentSdkUnavailable("Agent SDK binding version mismatch")
        if metadata.get("source_commit") not in (None, SDK_SOURCE_COMMIT):
            raise AgentSdkUnavailable("Agent SDK source commit mismatch")
        targets = metadata.get("target_triples")
        if (
            not isinstance(targets, list)
            or not targets
            or any(not isinstance(item, str) or not item for item in targets)
        ):
            raise AgentSdkUnavailable("Agent SDK artifact metadata is missing or invalid")
        return contract, metadata

    @staticmethod
    def _probe_native_artifact(
        binding: ModuleType,
        path: str | os.PathLike[str],
        contract: dict[str, Any],
    ) -> str | None:
        requested = str(path)
        if requested == "packaged":
            resolver = getattr(binding, "_packaged_native_library", None)
            if not callable(resolver):
                raise AgentSdkUnavailable("Agent SDK native artifact is missing")
            native = resolver()
            if native is None:
                raise AgentSdkUnavailable("Agent SDK native artifact is missing")
            native_path = Path(str(native))
            explicit_path = str(native_path)
        else:
            native_path = Path(requested).expanduser().resolve()
            explicit_path = str(native_path)
        if not native_path.is_file():
            raise AgentSdkUnavailable("Agent SDK native artifact is missing")

        functions = contract.get("functions")
        if not isinstance(functions, list):
            raise AgentSdkUnavailable("Agent SDK ABI version mismatch")
        contract_symbols = {
            item.get("name") for item in functions
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        signatures = getattr(binding, "ABI_SIGNATURES", None)
        if not isinstance(signatures, dict) or contract_symbols != set(signatures):
            raise AgentSdkUnavailable("Agent SDK ABI version mismatch")

        try:
            native_lib = ctypes.CDLL(str(native_path))
        except OSError as error:
            raise AgentSdkUnavailable("Agent SDK native artifact could not be loaded") from error
        try:
            for symbol in contract_symbols:
                getattr(native_lib, symbol)
        except AttributeError as error:
            raise AgentSdkUnavailable("Agent SDK ABI version mismatch") from error

        try:
            native_lib.notemeld_agent_sdk_version.restype = ctypes.c_char_p
            native_lib.notemeld_agent_schema_version.restype = ctypes.c_char_p
            native_sdk_version = native_lib.notemeld_agent_sdk_version().decode("utf-8")
            native_schema_version = native_lib.notemeld_agent_schema_version().decode("utf-8")
        except (AttributeError, UnicodeDecodeError) as error:
            raise AgentSdkUnavailable("Agent SDK ABI version mismatch") from error
        if native_sdk_version != SDK_VERSION:
            raise AgentSdkUnavailable("Agent SDK version mismatch")
        if native_schema_version != SCHEMA_VERSION:
            raise AgentSdkUnavailable("Agent SDK schema version mismatch")
        return explicit_path

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @property
    def is_rollback(self) -> bool:
        return False
