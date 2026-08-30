from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from contextlib import contextmanager


class WorkspaceError(ValueError):
    pass


@contextmanager
def workspace_mutation_lock(root: Path):
    """Acquire an inter-process lock for quota-sensitive workspace mutations."""
    lock_path = root.parent / f".{root.name}.mutation.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            handle.write(b"0")
            handle.flush()
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
        generated = re.compile(r"^\..+\.[A-Za-z0-9_-]+(?:\.copy)?\.tmp$")
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
        try:
            with self._open_readonly(path) as handle:
                return handle.read().decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise WorkspaceError("workspace file is unavailable") from exc

    def read_text_bounded(self, logical_path: str, max_bytes: int) -> tuple[str, bool]:
        """Read at most ``max_bytes`` from a UTF-8 file without over-reading it."""
        if max_bytes <= 0:
            raise WorkspaceError("read limit must be positive")
        path = self.path(logical_path)
        if path.is_symlink() or not path.is_file():
            raise WorkspaceError("workspace file is unavailable")
        try:
            with self._open_readonly(path) as handle:
                content = handle.read(max_bytes + 1)
        except OSError as exc:
            raise WorkspaceError("workspace file is unavailable") from exc
        truncated = len(content) > max_bytes
        if truncated:
            content = content[:max_bytes]
        # Do not return a partial UTF-8 code point when the byte limit falls
        # in the middle of one. The ignored suffix is represented by the
        # existing ``truncated`` flag in the Agent tool response.
        return content.decode("utf-8", errors="ignore"), truncated

    @staticmethod
    def _open_readonly(path: Path):
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        return os.fdopen(descriptor, "rb")

    def write_text(self, logical_path: str, content: str) -> None:
        self.write_bytes(logical_path, content.encode("utf-8"))

    def write_bytes(self, logical_path: str, content: bytes) -> None:
        path = self.path(logical_path)
        if path.exists() and path.is_symlink():
            raise WorkspaceError("symlink writes are forbidden")
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            os.chmod(temporary, 0o600)
            temporary.write_bytes(content)
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            temporary.replace(path)
            _fsync_directory(path.parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

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

    def capacity(self) -> dict[str, int]:
        """Return filesystem capacity for the volume containing this workspace."""
        usage = shutil.disk_usage(self.root)
        return {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        }

    def list_files(self, prefix: str = "", limit: int | None = None) -> list[dict[str, int | str]]:
        if limit is not None and limit <= 0:
            raise WorkspaceError("file list limit must be positive")
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
            if limit is not None and len(items) >= limit:
                break
        return sorted(items, key=lambda item: str(item["path"]))

    def create_backup(self, destination: Path) -> int:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            os.chmod(temporary, 0o600)
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in self.root.rglob("*"):
                    if path.is_symlink() or not path.is_file():
                        continue
                    archive.write(path, path.relative_to(self.root).as_posix())
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            temporary.replace(destination)
            _fsync_directory(destination.parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return destination.stat().st_size

    def restore_backup(self, archive_path: Path, max_bytes: int, max_files: int | None = None) -> dict[str, int]:
        if not archive_path.is_file():
            raise WorkspaceError("backup is unavailable")
        total = 0
        members: list[zipfile.ZipInfo] = []
        member_names: set[str] = set()
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                file_mode = member.external_attr >> 16
                file_type = file_mode & 0o170000
                if file_type == 0o120000:
                    raise WorkspaceError("backup contains a symlink")
                if file_type not in {0, 0o100000, 0o040000}:
                    raise WorkspaceError("backup contains a special file")
                is_directory = member.is_dir()
                member_name = member.filename.rstrip("/") if is_directory else member.filename
                raw_parts = member_name.split("/")
                if (
                    not member_name
                    or member_name in {".", ".."}
                    or "\x00" in member_name
                    or len(member_name) > 4096
                    or member_name.startswith(("/", "\\"))
                    or "\\" in member_name
                    or ":" in member_name
                    or any(part in {"", ".", ".."} for part in raw_parts)
                ):
                    raise WorkspaceError("backup contains an unsafe path")
                if is_directory:
                    continue
                normalized_name = "/".join(raw_parts).casefold()
                if any(
                    existing == normalized_name
                    or existing.startswith(normalized_name + "/")
                    or normalized_name.startswith(existing + "/")
                    for existing in member_names
                ):
                    raise WorkspaceError("backup contains duplicate paths")
                member_names.add(normalized_name)
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
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".copy.tmp", dir=target.parent)
            os.close(descriptor)
            temporary = Path(temporary_name)
            try:
                os.chmod(temporary, 0o600)
                shutil.copyfile(source, temporary)
                with temporary.open("rb") as handle:
                    os.fsync(handle.fileno())
                temporary.replace(target)
                _fsync_directory(target.parent)
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
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
