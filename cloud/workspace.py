from __future__ import annotations

import os
from pathlib import Path


class WorkspaceError(ValueError):
    pass


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, logical_path: str) -> Path:
        if not logical_path or "\x00" in logical_path:
            raise WorkspaceError("invalid workspace path")
        candidate = (self.root / logical_path).resolve(strict=False)
        if os.path.commonpath((str(self.root), str(candidate))) != str(self.root):
            raise WorkspaceError("workspace path escapes root")
        return candidate

    def read_text(self, logical_path: str) -> str:
        path = self.path(logical_path)
        if path.is_symlink() or not path.is_file():
            raise WorkspaceError("workspace file is unavailable")
        return path.read_text(encoding="utf-8")

    def write_text(self, logical_path: str, content: str) -> None:
        path = self.path(logical_path)
        if path.exists() and path.is_symlink():
            raise WorkspaceError("symlink writes are forbidden")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        temporary.replace(path)
