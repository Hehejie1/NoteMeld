from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.applications.manifest import SUPPORTED_RUNTIME_KINDS, default_application_package_root, runtime_kind_for_platform


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


APPLICATION_SDK_VERSION = "1.0.0"


class ApplicationRuntime:
    """Host-owned runtime adapters for desktop processes and Web workers.

    A desktop application process communicates over inherited stdin/stdout and
    never receives a listening socket. Web remains an invocation seam: the
    deployment-specific worker provider can be attached without changing the
    Application Run or SDK protocol.
    """

    def __init__(self, package_root: Path | None = None):
        self.package_root = (package_root or default_application_package_root()).resolve()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._stderr: dict[str, deque[str]] = {}

    def start(self, manifest: dict[str, Any], context: RuntimeContext) -> dict[str, Any]:
        self.check_policy(manifest, context)
        kind = runtime_kind_for_platform(manifest, context.platform)
        if kind not in SUPPORTED_RUNTIME_KINDS:
            raise ApplicationRuntimeError("unsupported_runtime", "application runtime is unsupported")
        if kind == "process-jsonl":
            self._start_process(manifest, context)
        return {"status": "running", "runtime_kind": kind, "public_listener": False}

    def invoke(self, manifest: dict[str, Any], context: RuntimeContext, method: str, input_data: Any) -> dict[str, Any]:
        self.check_policy(manifest, context)
        if not isinstance(method, str) or not method.strip():
            raise ApplicationRuntimeError("invalid_invocation", "runtime method is required")
        kind = runtime_kind_for_platform(manifest, context.platform)
        if kind == "process-jsonl":
            process = self._processes.get(context.run_id)
            if process is None or process.poll() is not None:
                raise ApplicationRuntimeError("runtime_unavailable", "application process is not running")
            request = {
                "protocol": "notemeld.application.v1",
                "request_id": str(uuid.uuid4()),
                "app_id": context.app_id,
                "instance_id": context.instance_id,
                "run_id": context.run_id,
                "sdk_version": APPLICATION_SDK_VERSION,
                "type": "invoke",
                "method": method,
                "input": input_data,
            }
            try:
                assert process.stdin is not None
                process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                process.stdin.flush()
                response = self._read_json_line(process, timeout=5)
            except ApplicationRuntimeError:
                raise
            except (BrokenPipeError, OSError, ValueError) as exc:
                raise ApplicationRuntimeError("runtime_transport_error", "application process transport failed") from exc
            if (
                response.get("protocol") != "notemeld.application.v1"
                or response.get("type") != "result"
                or response.get("request_id") != request["request_id"]
                or response.get("app_id") != context.app_id
                or response.get("instance_id") != context.instance_id
                or response.get("run_id") != context.run_id
                or response.get("sdk_version") != APPLICATION_SDK_VERSION
            ):
                raise ApplicationRuntimeError("runtime_protocol_error", "application process returned a mismatched request")
            return response
        return {"accepted": True, "method": method, "input": input_data}

    def cancel(self, _manifest: dict[str, Any], context: RuntimeContext) -> dict[str, Any]:
        self._terminate(context.run_id)
        return {"accepted": True}

    def stop(self, _manifest: dict[str, Any], context: RuntimeContext) -> dict[str, Any]:
        self._terminate(context.run_id)
        return {"status": "stopped"}

    def status(self, run_id: str) -> str | None:
        """Return a process-backed run status, or None for worker adapters."""
        process = self._processes.get(run_id)
        if process is None:
            return None
        return "running" if process.poll() is None else "interrupted"

    def _start_process(self, manifest: dict[str, Any], context: RuntimeContext) -> None:
        runtime = manifest.get("runtime") or {}
        command = runtime.get("command") or {}
        entry = command.get("program") or runtime.get("entry")
        if not entry:
            raise ApplicationRuntimeError("missing_runtime_entry", "process runtime entry is required")
        package_dir = (self.package_root / manifest["id"]).resolve()
        executable = (package_dir / entry).resolve()
        try:
            executable.relative_to(package_dir)
        except ValueError as exc:
            raise ApplicationRuntimeError("unsafe_runtime_entry", "runtime entry is outside the application package") from exc
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ApplicationRuntimeError("missing_runtime_entry", "runtime entry is not executable")
        try:
            args = [str(executable), *command.get("args", [])]
            env = {"PATH": os.environ.get("PATH", "")}
            for key, value in command.get("env", {}).items():
                if key.startswith("NOTEMELD_APP_"):
                    env[key] = value
            process = subprocess.Popen(
                args,
                cwd=str(package_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
        except OSError as exc:
            raise ApplicationRuntimeError("runtime_start_failed", "application process could not be started") from exc
        self._processes[context.run_id] = process
        self._stderr[context.run_id] = deque(maxlen=200)
        threading.Thread(target=self._capture_stderr, args=(context.run_id, process), daemon=True).start()
        if process.poll() is not None:
            self._processes.pop(context.run_id, None)
            raise ApplicationRuntimeError("runtime_start_failed", "application process exited during startup")
        hello = {
            "protocol": "notemeld.application.v1",
            "type": "hello",
            "request_id": str(uuid.uuid4()),
            "app_id": context.app_id,
            "instance_id": context.instance_id,
            "run_id": context.run_id,
            "sdk_version": APPLICATION_SDK_VERSION,
        }
        try:
            assert process.stdin is not None
            process.stdin.write(json.dumps(hello, ensure_ascii=False) + "\n")
            process.stdin.flush()
            ready = self._read_json_line(process, timeout=5)
        except ApplicationRuntimeError:
            self._terminate(context.run_id)
            raise
        except (BrokenPipeError, OSError, ValueError) as exc:
            self._terminate(context.run_id)
            raise ApplicationRuntimeError("runtime_transport_error", "application process handshake failed") from exc
        if (
            ready.get("protocol") != "notemeld.application.v1"
            or ready.get("type") != "ready"
            or ready.get("request_id") != hello["request_id"]
            or ready.get("app_id") != context.app_id
            or ready.get("instance_id") != context.instance_id
            or ready.get("run_id") != context.run_id
            or ready.get("sdk_version") != APPLICATION_SDK_VERSION
        ):
            self._terminate(context.run_id)
            raise ApplicationRuntimeError("runtime_protocol_error", "application process handshake was invalid")

    @staticmethod
    def _read_json_line(process: subprocess.Popen[str], timeout: float) -> dict[str, Any]:
        if process.stdout is None:
            raise ApplicationRuntimeError("runtime_protocol_error", "application process has no stdout")
        lines: queue.Queue[str] = queue.Queue(maxsize=1)

        def read_line() -> None:
            try:
                lines.put(process.stdout.readline())
            except OSError:
                lines.put("")

        reader = threading.Thread(target=read_line, daemon=True)
        reader.start()
        try:
            line = lines.get(timeout=timeout)
        except queue.Empty as exc:
            raise ApplicationRuntimeError("runtime_timeout", "application process did not respond in time") from exc
        try:
            value = json.loads(line)
        except (TypeError, ValueError) as exc:
            raise ApplicationRuntimeError("runtime_protocol_error", "application process returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise ApplicationRuntimeError("runtime_protocol_error", "application process returned an invalid frame")
        return value

    def _terminate(self, run_id: str) -> None:
        process = self._processes.pop(run_id, None)
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def logs(self, run_id: str) -> list[str]:
        return list(self._stderr.get(run_id, ()))

    def _capture_stderr(self, run_id: str, process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            self._stderr.setdefault(run_id, deque(maxlen=200)).append(line.rstrip())

    @staticmethod
    def check_policy(manifest: dict[str, Any], context: RuntimeContext) -> None:
        if (manifest.get("platforms") or {}).get(context.platform) != "supported":
            raise ApplicationRuntimeError("platform_unsupported", "application does not support this platform")
        runtime = manifest.get("runtime") or {}
        if runtime.get("public_listener") is True or runtime.get("listen"):
            raise ApplicationRuntimeError("public_listener_denied", "applications cannot expose a listener")
