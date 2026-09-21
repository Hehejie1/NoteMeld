from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Callable, TypeVar

from app.models.learning_canvas import LearningCanvas
from app.utils.storage_paths import workspaces_root


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}
_MutationResult = TypeVar("_MutationResult")


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


class LearningCanvasStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root).resolve() if root is not None else workspaces_root()

    @staticmethod
    def _validate_id(value: str, field: str) -> str:
        normalized = str(value or "")
        if not _SAFE_ID.fullmatch(normalized):
            raise ValueError(f"非法 {field}: {value!r}")
        return normalized

    def path_for(self, conversation_id: str, canvas_id: str) -> Path:
        cid = self._validate_id(conversation_id, "conversation_id")
        canvas = self._validate_id(canvas_id, "canvas_id")
        base = (self.root / cid / "canvases").resolve()
        target = (base / f"{canvas}.json").resolve()
        if not str(target).startswith(str(base) + os.sep):
            raise ValueError("learning canvas path traversal detected")
        return target

    def save(self, canvas: LearningCanvas) -> LearningCanvas:
        path = self.path_for(canvas.conversation_id, canvas.canvas_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock_for(path):
            self._write_unlocked(path, canvas)
        return canvas

    def update(
        self,
        conversation_id: str,
        canvas_id: str,
        mutate: Callable[[LearningCanvas], _MutationResult],
    ) -> tuple[LearningCanvas, _MutationResult]:
        """在同一把 canvas 锁内完成 load → mutate → atomic save。"""
        path = self.path_for(conversation_id, canvas_id)
        with _lock_for(path):
            canvas = self._load_unlocked(path, canvas_id)
            result = mutate(canvas)
            self._write_unlocked(path, canvas)
        return canvas, result

    def load(self, conversation_id: str, canvas_id: str) -> LearningCanvas:
        path = self.path_for(conversation_id, canvas_id)
        return self._load_unlocked(path, canvas_id)

    @staticmethod
    def _load_unlocked(path: Path, canvas_id: str) -> LearningCanvas:
        if not path.exists():
            raise FileNotFoundError(canvas_id)
        return LearningCanvas.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_unlocked(path: Path, canvas: LearningCanvas) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = canvas.model_dump(mode="json")
        tmp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
                tmp_name = handle.name
            Path(tmp_name).replace(path)
        finally:
            if tmp_name:
                Path(tmp_name).unlink(missing_ok=True)

    def latest(self, conversation_id: str) -> LearningCanvas:
        cid = self._validate_id(conversation_id, "conversation_id")
        canvas_dir = (self.root / cid / "canvases").resolve()
        if not canvas_dir.exists():
            raise FileNotFoundError(conversation_id)
        candidates = [path for path in canvas_dir.glob("*.json") if path.is_file()]
        if not candidates:
            raise FileNotFoundError(conversation_id)
        latest_path = max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))
        return LearningCanvas.model_validate_json(latest_path.read_text(encoding="utf-8"))

    def list_all(self, limit: int = 50) -> list[LearningCanvas]:
        """Return persisted canvases for the learning app overview.

        A corrupt or partially-written canvas is skipped here; the detail
        endpoint remains strict so a caller never receives fabricated state.
        """
        bounded_limit = max(1, min(int(limit), 100))
        if not self.root.exists():
            return []
        items: list[tuple[int, LearningCanvas]] = []
        for path in self.root.glob("*/canvases/*.json"):
            if not path.is_file():
                continue
            try:
                canvas = LearningCanvas.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            items.append((path.stat().st_mtime_ns, canvas))
        items.sort(key=lambda item: (item[0], item[1].canvas_id), reverse=True)
        return [canvas for _, canvas in items[:bounded_limit]]
