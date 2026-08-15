"""Thin ctypes translation layer over the versioned NoteMeld Agent C ABI."""

from __future__ import annotations

import ctypes
import json
import os
import queue
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

SDK_VERSION = "0.1.0"
SCHEMA_VERSION = "1"

FFI_OK = 0
FFI_UNSUPPORTED = -6
FFI_TIMEOUT = -10


class AgentSdkError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_char_p)
_RELEASE_CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
_CONTEXTS: dict[int, "_CallbackBox"] = {}
_CONTEXTS_LOCK = threading.Lock()


class _CallbackBox:
    def __init__(self, lib: ctypes.CDLL, handle: int, driver: Callable[..., Any], on_event: Callable[..., Any] | None) -> None:
        self.lib = lib
        self.handle = handle
        self.driver = driver
        self.on_event = on_event
        self.events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1024)


def _box(context: int | None) -> _CallbackBox | None:
    with _CONTEXTS_LOCK:
        return _CONTEXTS.get(int(context or 0))


@_CALLBACK
def _receive_event(context: int, payload: bytes) -> int:
    try:
        box = _box(context)
        if box is None:
            return -1
        event = json.loads(payload.decode("utf-8"))
        if event.get("schema_version") != SCHEMA_VERSION:
            return -2
        try:
            box.events.put_nowait(event)
        except queue.Full:
            if event.get("type") not in {"turn.succeeded", "turn.failed", "turn.cancelled", "turn.interrupted"}:
                return FFI_OK
            box.events.get_nowait()
            box.events.put_nowait(event)
        if box.on_event is not None:
            box.on_event(event)
        return FFI_OK
    except Exception:
        return -9


@_CALLBACK
def _receive_driver_request(context: int, payload: bytes) -> int:
    box = _box(context)
    if box is None:
        return -1
    try:
        request = json.loads(payload.decode("utf-8"))
        call_id = int(request["call_id"])
        result = dict(box.driver(request))
        result.setdefault("schema_version", SCHEMA_VERSION)
    except Exception:
        if "call_id" not in locals():
            return -2
        result = {"schema_version": SCHEMA_VERSION, "ok": False,
                  "error": {"code": "sdk_internal_error", "message": "host driver failed"}}
    return int(box.lib.notemeld_agent_complete_driver_call(box.handle, call_id, _json_bytes(result)))


@_RELEASE_CALLBACK
def _release_context(context: int) -> None:
    with _CONTEXTS_LOCK:
        _CONTEXTS.pop(int(context or 0), None)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class Runtime:
    def __init__(
        self,
        native_library: str | os.PathLike[str] | None = None,
        *,
        driver: Callable[[dict[str, Any]], Mapping[str, Any]],
        on_event: Callable[[dict[str, Any]], None] | None = None,
        max_turns: int = 16,
    ) -> None:
        library = native_library or os.environ.get("NOTEMELD_AGENT_SDK_LIBRARY")
        if not library:
            raise AgentSdkError(-2, "native library path is required")
        path = Path(library).expanduser()
        if not path.is_file():
            raise AgentSdkError(-2, "native library does not exist")
        self._lib = ctypes.CDLL(str(path))
        self._configure_abi()
        if self._lib.notemeld_agent_sdk_version().decode() != SDK_VERSION:
            raise AgentSdkError(-2, "SDK version mismatch")
        if self._lib.notemeld_agent_schema_version().decode() != SCHEMA_VERSION:
            raise AgentSdkError(-2, "schema version mismatch")
        self._closed = False
        config = _json_bytes({"schema_version": SCHEMA_VERSION, "max_turns": max_turns})
        self._handle = self._lib.notemeld_agent_runtime_new(config)
        if not self._handle:
            raise AgentSdkError(-9, "native runtime creation failed")
        box = _CallbackBox(self._lib, self._handle, driver, on_event)
        self.events = box.events
        self._context = id(box)
        with _CONTEXTS_LOCK:
            _CONTEXTS[self._context] = box
        code = self._lib.notemeld_agent_runtime_set_callbacks(
            self._handle,
            _receive_event,
            self._context,
            _receive_driver_request,
            self._context,
            _release_context,
            self._context,
        )
        if code != FFI_OK:
            with _CONTEXTS_LOCK:
                _CONTEXTS.pop(self._context, None)
            self._lib.notemeld_agent_runtime_free(self._handle)
            self._handle = None
            self._check(code, "callback registration failed")

    def _configure_abi(self) -> None:
        lib = self._lib
        lib.notemeld_agent_sdk_version.restype = ctypes.c_char_p
        lib.notemeld_agent_schema_version.restype = ctypes.c_char_p
        lib.notemeld_agent_runtime_new.argtypes = [ctypes.c_char_p]
        lib.notemeld_agent_runtime_new.restype = ctypes.c_void_p
        lib.notemeld_agent_runtime_set_callbacks.argtypes = [
            ctypes.c_void_p,
            _CALLBACK,
            ctypes.c_void_p,
            _CALLBACK,
            ctypes.c_void_p,
            _RELEASE_CALLBACK,
            ctypes.c_void_p,
        ]
        lib.notemeld_agent_runtime_set_callbacks.restype = ctypes.c_int32
        lib.notemeld_agent_submit_turn.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.notemeld_agent_submit_turn.restype = ctypes.c_uint64
        lib.notemeld_agent_complete_driver_call.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.c_char_p,
        ]
        lib.notemeld_agent_complete_driver_call.restype = ctypes.c_int32
        lib.notemeld_agent_cancel_turn.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
        lib.notemeld_agent_cancel_turn.restype = ctypes.c_int32
        lib.notemeld_agent_steer_turn.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_char_p]
        lib.notemeld_agent_steer_turn.restype = ctypes.c_int32
        lib.notemeld_agent_wait_turn.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64]
        lib.notemeld_agent_wait_turn.restype = ctypes.c_int32
        lib.notemeld_agent_last_error_json.argtypes = [ctypes.c_void_p]
        lib.notemeld_agent_last_error_json.restype = ctypes.c_void_p
        lib.notemeld_agent_string_free.argtypes = [ctypes.c_void_p]
        lib.notemeld_agent_runtime_free.argtypes = [ctypes.c_void_p]

    def submit_turn(self, request: Mapping[str, Any]) -> int:
        self._ensure_open()
        turn = int(self._lib.notemeld_agent_submit_turn(self._handle, _json_bytes(request)))
        if not turn:
            raise self._last_error("turn submission failed")
        return turn

    def wait(self, turn_token: int, timeout_ms: int = 30_000) -> None:
        self._ensure_open()
        self._check(
            int(self._lib.notemeld_agent_wait_turn(self._handle, turn_token, timeout_ms)),
            "turn wait failed",
        )

    def cancel(self, turn_token: int) -> None:
        self._ensure_open()
        self._check(int(self._lib.notemeld_agent_cancel_turn(self._handle, turn_token)), "cancel failed")

    def steer(self, turn_token: int, payload: Mapping[str, Any]) -> None:
        self._ensure_open()
        code = int(self._lib.notemeld_agent_steer_turn(self._handle, turn_token, _json_bytes(payload)))
        self._check(code, "steer is unsupported by the fixed-loop v1 runtime")

    def _last_error(self, fallback: str) -> AgentSdkError:
        pointer = self._lib.notemeld_agent_last_error_json(self._handle)
        if not pointer:
            return AgentSdkError(-9, fallback)
        try:
            error = json.loads(ctypes.string_at(pointer).decode("utf-8"))
            return AgentSdkError(-9, str(error.get("message", fallback)))
        finally:
            self._lib.notemeld_agent_string_free(pointer)

    @staticmethod
    def _check(code: int, message: str) -> None:
        if code != FFI_OK:
            raise AgentSdkError(code, message)

    def _ensure_open(self) -> None:
        if self._closed:
            raise AgentSdkError(-1, "runtime is closed")

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._lib.notemeld_agent_runtime_free(self._handle)
            self._handle = None

    def __enter__(self) -> "Runtime":
        self._ensure_open()
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
