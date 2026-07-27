from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from app.services.wiki_store import WikiStore
from app.utils.logger import get_logger


logger = get_logger(__name__)


class WikiRebuildService:
    def __init__(self, output_dir: Path, worker_name_prefix: str = "wiki-rebuild"):
        self.output_dir = Path(output_dir)
        self.worker_name_prefix = worker_name_prefix
        self._lock = threading.RLock()
        self._generation = 0
        self._pending = False
        self._running = False
        self._current_cancel: Optional[threading.Event] = None
        self._last_gpt = None
        self._worker: Optional[threading.Thread] = None

    @property
    def current_generation(self) -> int:
        with self._lock:
            return self._generation

    def request_rebuild(self, gpt=None, reason: str = "contribution_updated") -> dict:
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._last_gpt = gpt
            self._pending = True
            if self._current_cancel is not None:
                self._current_cancel.set()
            payload = self._write_status(
                "pending",
                generation=generation,
                detail="已请求重建完整 Wiki",
                reason=reason,
            )
            if not self._running:
                self._running = True
                self._worker = threading.Thread(
                    target=self._run_loop,
                    name=f"{self.worker_name_prefix}-{generation}",
                    daemon=True,
                )
                self._worker.start()
            return payload

    def wait_idle(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time_monotonic() + timeout
        while True:
            with self._lock:
                idle = not self._running and not self._pending
            if idle:
                return True
            if deadline is not None and time_monotonic() >= deadline:
                return False
            threading.Event().wait(0.01)

    def _run_loop(self) -> None:
        while True:
            with self._lock:
                if not self._pending:
                    self._running = False
                    self._current_cancel = None
                    return
                self._pending = False
                generation = self._generation
                gpt = self._last_gpt
                cancel_event = threading.Event()
                self._current_cancel = cancel_event

            try:
                self._write_status("running", generation=generation, stage="materialize", detail="正在重建完整 Wiki")
                store = WikiStore(base_dir=self.output_dir / "wiki")
                setattr(store, "current_generation", generation)
                graph = store.rebuild_from_contributions(
                    gpt=gpt,
                    cancel_check=lambda: cancel_event.is_set() or self.current_generation != generation,
                )
                if cancel_event.is_set() or self.current_generation != generation:
                    self._write_status("canceled", generation=generation, stage="materialize", detail="已有更新请求，当前重建已中断")
                    continue
                self._write_status(
                    "success",
                    generation=generation,
                    stage="materialize",
                    detail="完整 Wiki 重建完成",
                    extra={"node_count": len(graph.get("nodes", [])), "edge_count": len(graph.get("edges", []))},
                )
            except Exception as exc:
                logger.error("Wiki rebuild failed: %s", exc, exc_info=True)
                if cancel_event.is_set() or self.current_generation != generation:
                    self._write_status("canceled", generation=generation, stage="materialize", detail="已有更新请求，失败结果已丢弃")
                    continue
                self._write_status(
                    "failed",
                    generation=generation,
                    stage="materialize",
                    error=str(exc),
                    reason="rebuild_error",
                    detail=str(exc),
                    recoverable=True,
                )

    def _write_status(
        self,
        status: str,
        *,
        generation: int,
        stage: str = "",
        error: str = "",
        reason: str = "",
        detail: str = "",
        recoverable: bool = False,
        extra: Optional[dict] = None,
    ) -> dict:
        payload = {
            "status": status,
            "generation": generation,
            "stage": stage,
            "error": error,
            "reason": reason,
            "detail": detail or error,
            "recoverable": recoverable,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            payload.update(extra)
        path = self.output_dir / "wiki_rebuild_job.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
        return payload


def time_monotonic() -> float:
    import time

    return time.monotonic()


_SERVICES: dict[Path, WikiRebuildService] = {}
_SERVICES_LOCK = threading.RLock()


def get_wiki_rebuild_service(output_dir: Path) -> WikiRebuildService:
    key = Path(output_dir)
    with _SERVICES_LOCK:
        service = _SERVICES.get(key)
        if service is None:
            service = WikiRebuildService(output_dir=key)
            _SERVICES[key] = service
        return service


def request_wiki_rebuild(output_dir: Path, gpt=None, reason: str = "contribution_updated") -> dict:
    return get_wiki_rebuild_service(output_dir).request_rebuild(gpt=gpt, reason=reason)
