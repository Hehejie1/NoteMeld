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
        self._drivers: dict[int, Callable[[dict[str, Any]], Mapping[str, Any]]] = {}
        self._event_handlers: dict[str, Callable[[dict[str, Any]], None]] = {}
        self._pending_drivers: dict[str, Callable[[dict[str, Any]], Mapping[str, Any]]] = {}
        self._pending_events: dict[str, Callable[[dict[str, Any]], None]] = {}
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
            # The native runtime is created once. Per-turn callbacks are routed
            # by the token included in ABI v2 driver requests.
            self._runtime = factory(driver=self._dispatch_driver, on_event=self._dispatch_event)
            return self

    def _dispatch_driver(self, request: dict[str, Any]) -> Mapping[str, Any]:
        token = int(request.get("turn_token") or 0)
        with self._lock:
            driver = self._drivers.get(token)
            if driver is None:
                driver = self._pending_drivers.get(str(request.get("turn_id") or ""))
        if driver is None:
            return {"schema_version": "1", "ok": False, "error": {"code": "turn_not_found", "message": "turn driver unavailable"}}
        return driver(request)

    def _dispatch_event(self, event: dict[str, Any]) -> None:
        turn_id = str(event.get("turn_id") or "")
        with self._lock:
            handler = self._event_handlers.get(turn_id)
            if handler is None:
                handler = self._pending_events.get(turn_id)
        if handler is not None:
            handler(event)

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

    def submit(
        self,
        turn_id: str,
        request: Mapping[str, Any],
        *,
        driver: Callable[[dict[str, Any]], Mapping[str, Any]],
        on_event: Callable[[dict[str, Any]], None],
    ) -> NativeTurnHandle:
        with self._lock:
            runtime = self.runtime
            request_id = str(request.get("request_id") or turn_id)
            self._pending_drivers[request_id] = driver
            self._pending_events[turn_id] = on_event
            token = int(runtime.submit_turn(dict(request)))
            if not token:
                self._pending_drivers.pop(request_id, None)
                self._pending_events.pop(turn_id, None)
                raise AgentSdkUnavailable("native turn submission failed")
            handle = NativeTurnHandle(turn_id, token)
            self._handles[turn_id] = handle
            self._drivers[token] = driver
            self._event_handlers[turn_id] = on_event
            self._pending_drivers.pop(request_id, None)
            self._pending_events.pop(turn_id, None)
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

    def resolve_approval(self, approval_id: str, decision: str) -> None:
        resolver = getattr(self.runtime, "resolve_approval", None)
        if not callable(resolver):
            raise AgentSdkUnavailable("installed Agent SDK does not expose approval control")
        resolver(approval_id, decision)

    def forget(self, turn_id: str) -> None:
        with self._lock:
            handle = self._handles.pop(turn_id, None)
            self._event_handlers.pop(turn_id, None)
            if handle is not None:
                self._drivers.pop(handle.token, None)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            runtime, self._runtime = self._runtime, None
            self._handles.clear()
            self._drivers.clear()
            self._event_handlers.clear()
            self._pending_drivers.clear()
            self._pending_events.clear()
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
