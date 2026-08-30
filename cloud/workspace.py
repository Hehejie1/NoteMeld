from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path


class WorkspaceError(ValueError):
    pass


class Workspace:
    def __init__(self, root: Path):
        absolute_root = root.absolute()
        current = absolute_root
        while True:
            if current.is_symlink():
                raise WorkspaceError("workspace root symlink traversal is forbidden")
            if current.parent == current:
                break
            current = current.parent
        self.root = absolute_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._cleanup_interrupted_writes()

    def _cleanup_interrupted_writes(self) -> None:
        """Remove only temporary files produced by this workspace writer."""
        generated = re.compile(r"^\..+\.\d+(?:\.copy)?\.tmp$")
        for path in self.root.rglob("*"):
            if path.is_file() and generated.match(path.name):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    def path(self, logical_path: str) -> Path:
        if not logical_path or "\x00" in logical_path:
            raise WorkspaceError("invalid workspace path")
        if "\\" in logical_path or ":" in logical_path or logical_path.startswith("/"):
            raise WorkspaceError("invalid workspace path")
        parts = logical_path.split("/")
        if len(parts) > 32 or any(part in {"", ".", ".."} for part in parts):
            raise WorkspaceError("invalid workspace path")
        candidate = (self.root / logical_path).resolve(strict=False)
        if os.path.commonpath((str(self.root), str(candidate))) != str(self.root):
            raise WorkspaceError("workspace path escapes root")
        current = self.root
        for part in parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise WorkspaceError("workspace symlink traversal is forbidden")
        return candidate

    def read_text(self, logical_path: str) -> str:
        path = self.path(logical_path)
        if path.is_symlink() or not path.is_file():
            raise WorkspaceError("workspace file is unavailable")
        return path.read_text(encoding="utf-8")

    def write_text(self, logical_path: str, content: str) -> None:
        self.write_bytes(logical_path, content.encode("utf-8"))

    def write_bytes(self, logical_path: str, content: bytes) -> None:
        path = self.path(logical_path)
        if path.exists() and path.is_symlink():
            raise WorkspaceError("symlink writes are forbidden")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(content)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        temporary.replace(path)
        _fsync_directory(path.parent)

    def delete_file(self, logical_path: str) -> None:
        path = self.path(logical_path)
        if path.is_symlink() or not path.is_file():
            raise WorkspaceError("workspace file is unavailable")
        path.unlink()
        _fsync_directory(path.parent)

    def stats(self) -> dict[str, int]:
        files = 0
        bytes_used = 0
        for path in self.root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            files += 1
            bytes_used += path.stat().st_size
        return {"file_count": files, "bytes_used": bytes_used}

    def list_files(self, prefix: str = "") -> list[dict[str, int | str]]:
        if prefix:
            base = self.path(prefix)
            if base.is_symlink() or (base.exists() and not base.is_dir()):
                raise WorkspaceError("workspace directory is unavailable")
        else:
            base = self.root
        items: list[dict[str, int | str]] = []
        for path in base.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            items.append({"path": path.relative_to(self.root).as_posix(), "bytes": path.stat().st_size, "modified_at": int(path.stat().st_mtime)})
        return sorted(items, key=lambda item: str(item["path"]))

    def create_backup(self, destination: Path) -> int:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + f".{os.getpid()}.tmp")
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in self.root.rglob("*"):
                if path.is_symlink() or not path.is_file():
                    continue
                archive.write(path, path.relative_to(self.root).as_posix())
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        temporary.replace(destination)
        _fsync_directory(destination.parent)
        return destination.stat().st_size

    def restore_backup(self, archive_path: Path, max_bytes: int, max_files: int | None = None) -> dict[str, int]:
        if not archive_path.is_file():
            raise WorkspaceError("backup is unavailable")
        total = 0
        members: list[zipfile.ZipInfo] = []
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir() or member.filename.startswith("/") or ".." in Path(member.filename).parts:
                    raise WorkspaceError("backup contains an unsafe path")
                if member.external_attr >> 16 & 0o170000 == 0o120000:
                    raise WorkspaceError("backup contains a symlink")
                total += member.file_size
                if total > max_bytes:
                    raise WorkspaceError("backup exceeds workspace quota")
                members.append(member)
                if max_files is not None and len(members) > max_files:
                    raise WorkspaceError("backup exceeds file-count quota")
            staging = Path(tempfile.mkdtemp(prefix="notemeld-restore-", dir=self.root.parent))
            try:
                for member in members:
                    target = (staging / member.filename).resolve(strict=False)
                    if os.path.commonpath((str(staging.resolve()), str(target))) != str(staging.resolve()):
                        raise WorkspaceError("backup path escapes staging")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                        output.flush()
                        os.fsync(output.fileno())
                for source in staging.rglob("*"):
                    if source.is_file():
                        target = self.path(source.relative_to(staging).as_posix())
                        target.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(source, target)
                _fsync_directory(self.root)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        return {"file_count": len(members), "bytes_restored": total}

    def copy_to(self, destination: "Workspace", max_bytes: int) -> dict[str, int]:
        stats = self.stats()
        if stats["bytes_used"] > max_bytes:
            raise WorkspaceError("workspace exceeds destination quota")
        copied = 0
        for source in self.root.rglob("*"):
            if source.is_symlink() or not source.is_file():
                continue
            relative = source.relative_to(self.root).as_posix()
            target = destination.path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{os.getpid()}.copy.tmp")
            shutil.copyfile(source, temporary)
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            temporary.replace(target)
            _fsync_directory(target.parent)
            copied += 1
        return {"file_count": copied, "bytes_copied": stats["bytes_used"]}


def _fsync_directory(path: Path) -> None:
    """Persist directory entry updates where the platform supports it."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
