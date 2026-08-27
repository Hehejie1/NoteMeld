from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.applications.manifest import SUPPORTED_RUNTIME_KINDS


class ApplicationRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class RuntimeContext:
    app_id: str
    instance_id: str
    run_id: str
    platform: str = "desktop"


class ApplicationRuntime:
    """Controlled lifecycle seam. It never starts a public listener."""

    def start(self, manifest: dict[str, Any], context: RuntimeContext) -> dict[str, Any]:
        self.check_policy(manifest, context)
        kind = (manifest.get("runtime") or {}).get("kind")
        if kind not in SUPPORTED_RUNTIME_KINDS:
            raise ApplicationRuntimeError("unsupported_runtime", "application runtime is unsupported")
        return {"status": "running", "runtime_kind": kind, "public_listener": False}

    def invoke(self, manifest: dict[str, Any], context: RuntimeContext, method: str, input_data: Any) -> dict[str, Any]:
        self.check_policy(manifest, context)
        if not isinstance(method, str) or not method.strip():
            raise ApplicationRuntimeError("invalid_invocation", "runtime method is required")
        return {"accepted": True, "method": method, "input": input_data}

    def cancel(self, _manifest: dict[str, Any], _context: RuntimeContext) -> dict[str, Any]:
        return {"accepted": True}

    def stop(self, _manifest: dict[str, Any], _context: RuntimeContext) -> dict[str, Any]:
        return {"status": "stopped"}

    @staticmethod
    def check_policy(manifest: dict[str, Any], context: RuntimeContext) -> None:
        if (manifest.get("platforms") or {}).get(context.platform) != "supported":
            raise ApplicationRuntimeError("platform_unsupported", "application does not support this platform")
        runtime = manifest.get("runtime") or {}
        if runtime.get("public_listener") is True or runtime.get("listen"):
            raise ApplicationRuntimeError("public_listener_denied", "applications cannot expose a listener")
