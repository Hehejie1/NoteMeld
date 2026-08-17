"""Process-scoped owner for the native Agent SDK runtime.

The HTTP layer must not construct a native runtime per turn.  This small host
owns one binding/runtime for the lifetime of the FastAPI process and keeps the
native turn token associated with its product turn id for control calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Mapping

from .runtime import AgentSdkRuntime, AgentSdkUnavailable


@dataclass(frozen=True)
class NativeTurnHandle:
    turn_id: str
    token: int


class AgentSdkHost:
    def __init__(self, *, binding_path: str | None = None, runtime_factory: Callable[..., Any] | None = None) -> None:
        self.binding_path = binding_path
        self.runtime_factory = runtime_factory
        self._loaded: AgentSdkRuntime | None = None
        self._runtime: Any | None = None
        self._handles: dict[str, NativeTurnHandle] = {}
        self._lock = RLock()
        self._closed = False

    @property
    def started(self) -> bool:
        return self._runtime is not None and not self._closed

    def start(self, *, driver: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None,
              on_event: Callable[[dict[str, Any]], None] | None = None) -> "AgentSdkHost":
        with self._lock:
            if self.started:
                return self
            if self._closed:
                raise AgentSdkUnavailable("Agent SDK Host has been closed")
            loaded = AgentSdkRuntime.load(binding_path=self.binding_path or "packaged")
            if loaded.binding is None:
                raise AgentSdkUnavailable("Rust SDK binding unavailable")
            factory = self.runtime_factory or loaded.binding.Runtime
            self._loaded = loaded
            # Driver and event callbacks are installed by the product executor;
            # the runtime is still created once and shared by all turns.
            kwargs: dict[str, Any] = {}
            if driver is not None:
                kwargs["driver"] = driver
            if on_event is not None:
                kwargs["on_event"] = on_event
            self._runtime = factory(**kwargs)
            return self

    @property
    def runtime(self) -> Any:
        if not self.started:
            self.start()
        assert self._runtime is not None
        return self._runtime

    def register(self, turn_id: str, token: int) -> NativeTurnHandle:
        with self._lock:
            if not self.started:
                self.start()
            handle = NativeTurnHandle(turn_id, int(token))
            self._handles[turn_id] = handle
            return handle

    def handle(self, turn_id: str) -> NativeTurnHandle | None:
        with self._lock:
            return self._handles.get(turn_id)

    def cancel(self, turn_id: str) -> None:
        handle = self.handle(turn_id)
        if handle is None:
            raise KeyError(turn_id)
        self.runtime.cancel(handle.token)

    def steer(self, turn_id: str, payload: Mapping[str, Any]) -> None:
        handle = self.handle(turn_id)
        if handle is None:
            raise KeyError(turn_id)
        self.runtime.steer(handle.token, payload)

    def forget(self, turn_id: str) -> None:
        with self._lock:
            self._handles.pop(turn_id, None)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            runtime, self._runtime = self._runtime, None
            self._handles.clear()
            self._closed = True
        if runtime is not None:
            runtime.close()


_host: AgentSdkHost | None = None
_host_lock = RLock()


def get_agent_sdk_host() -> AgentSdkHost:
    global _host
    with _host_lock:
        if _host is None or _host._closed:
            _host = AgentSdkHost()
        return _host


def close_agent_sdk_host() -> None:
    global _host
    with _host_lock:
        if _host is not None:
            _host.close()
            _host = None
