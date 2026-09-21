from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Any, Protocol

from .workspace import Workspace


@dataclass(frozen=True)
class BackupRecord:
    backup_id: str
    bytes: int
    created_at: int
    location: str


class BackupStorage(Protocol):
    def create(self, workspace: Workspace, *, user_id: str, workspace_id: str, backup_id: str) -> BackupRecord: ...

    def list(self, *, user_id: str, workspace_id: str, limit: int) -> list[BackupRecord]: ...

    def delete(self, *, user_id: str, workspace_id: str, backup_id: str) -> None: ...

    def restore(self, workspace: Workspace, *, user_id: str, workspace_id: str, backup_id: str, max_bytes: int, max_files: int) -> dict[str, int]: ...

    def read(self, *, user_id: str, workspace_id: str, backup_id: str) -> bytes: ...


class LocalBackupStorage:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, user_id: str, workspace_id: str, backup_id: str) -> Path:
        return self.root / user_id / workspace_id / f"{backup_id}.zip"

    def create(self, workspace: Workspace, *, user_id: str, workspace_id: str, backup_id: str) -> BackupRecord:
        destination = self._path(user_id, workspace_id, backup_id)
        size = workspace.create_backup(destination)
        return BackupRecord(backup_id, size, int(destination.stat().st_mtime), f"{workspace_id}/{destination.name}")

    def list(self, *, user_id: str, workspace_id: str, limit: int) -> list[BackupRecord]:
        directory = self.root / user_id / workspace_id
        if not directory.is_dir():
            return []
        records = []
        for path in directory.glob("*.zip"):
            try:
                stat = path.stat()
            except OSError:
                continue
            records.append(BackupRecord(path.stem, stat.st_size, int(stat.st_mtime), f"{workspace_id}/{path.name}"))
        return sorted(records, key=lambda item: item.created_at, reverse=True)[:limit]

    def delete(self, *, user_id: str, workspace_id: str, backup_id: str) -> None:
        path = self._path(user_id, workspace_id, backup_id)
        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise FileNotFoundError(backup_id) from exc

    def restore(self, workspace: Workspace, *, user_id: str, workspace_id: str, backup_id: str, max_bytes: int, max_files: int) -> dict[str, int]:
        return workspace.restore_backup(self._path(user_id, workspace_id, backup_id), max_bytes, max_files)

    def read(self, *, user_id: str, workspace_id: str, backup_id: str) -> bytes:
        return self._path(user_id, workspace_id, backup_id).read_bytes()


class S3BackupStorage:
    def __init__(self, settings: Any):
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - exercised in production environments
            raise RuntimeError("boto3 is required when S3 backup storage is enabled") from exc
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )
        self.bucket = settings.s3_bucket
        self.prefix = settings.s3_prefix

    def _key(self, user_id: str, workspace_id: str, backup_id: str) -> str:
        return f"{self.prefix}/{user_id}/{workspace_id}/{backup_id}.zip"

    def create(self, workspace: Workspace, *, user_id: str, workspace_id: str, backup_id: str) -> BackupRecord:
        with tempfile.NamedTemporaryFile(prefix="notemeld-backup-", suffix=".zip") as temporary:
            path = Path(temporary.name)
            size = workspace.create_backup(path)
            self.client.upload_file(str(path), self.bucket, self._key(user_id, workspace_id, backup_id))
        return BackupRecord(backup_id, size, 0, self._key(user_id, workspace_id, backup_id))

    def list(self, *, user_id: str, workspace_id: str, limit: int) -> list[BackupRecord]:
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=f"{self.prefix}/{user_id}/{workspace_id}/")
        records = []
        for item in response.get("Contents", []):
            key = str(item.get("Key", ""))
            if not key.endswith(".zip"):
                continue
            name = key.rsplit("/", 1)[-1]
            records.append(BackupRecord(name[:-4], int(item.get("Size", 0)), int(item.get("LastModified").timestamp()), key))
        return sorted(records, key=lambda record: record.created_at, reverse=True)[:limit]

    def delete(self, *, user_id: str, workspace_id: str, backup_id: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(user_id, workspace_id, backup_id))

    def restore(self, workspace: Workspace, *, user_id: str, workspace_id: str, backup_id: str, max_bytes: int, max_files: int) -> dict[str, int]:
        with tempfile.NamedTemporaryFile(prefix="notemeld-restore-", suffix=".zip") as temporary:
            self.client.download_file(self.bucket, self._key(user_id, workspace_id, backup_id), temporary.name)
            return workspace.restore_backup(Path(temporary.name), max_bytes, max_files)

    def read(self, *, user_id: str, workspace_id: str, backup_id: str) -> bytes:
        with tempfile.NamedTemporaryFile(prefix="notemeld-download-", suffix=".zip") as temporary:
            self.client.download_file(self.bucket, self._key(user_id, workspace_id, backup_id), temporary.name)
            return Path(temporary.name).read_bytes()


def create_backup_storage(settings: Any) -> BackupStorage:
    if settings.backup_storage_backend == "s3":
        return S3BackupStorage(settings)
    return LocalBackupStorage(settings.data_dir / "backups")
