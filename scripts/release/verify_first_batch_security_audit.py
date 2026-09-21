#!/usr/bin/env python3
"""Audit production Cloud storage, exported logs, and Redis for E-01 leaks.

Sensitive test values are loaded only from named environment variables.  They
must never be passed as command-line values.  The evidence output contains
only hashes and aggregate scan metadata; matched bytes are never printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Callable, Iterable
from urllib.parse import urlparse


REQUIRED_NEEDLES = {
    "challenge",
    "account_token",
    "device_token",
    "session_key",
    "provider_key",
}
RELAY_CURSOR_COLUMNS = [
    "session_id",
    "sender_device_id",
    "last_sequence",
    "updated_at",
]
RELAY_KEY_PREFIX = b"notemeld:relay:"
RELAY_PRESENCE_PREFIX = b"notemeld:relay:online:"
COMPRESSED_LOG_SUFFIXES = {".bz2", ".gz", ".xz", ".zip", ".zst"}


class AuditError(RuntimeError):
    pass


def _validate_needles(needles: dict[str, str]) -> dict[str, bytes]:
    if set(needles) != REQUIRED_NEEDLES:
        raise AuditError(f"audit needle labels must be exactly {sorted(REQUIRED_NEEDLES)}")
    encoded: dict[str, bytes] = {}
    for label, value in needles.items():
        if not isinstance(value, str) or not 12 <= len(value) <= 8192 or "\n" in value or "\r" in value:
            raise AuditError(f"audit needle {label} must be a 12-8192 character single-line value")
        encoded[label] = value.encode("utf-8")
    if len(set(encoded.values())) != len(encoded):
        raise AuditError("audit needle values must be distinct")
    return encoded


def _validate_redis_url(redis_url: str) -> None:
    parsed = urlparse(redis_url)
    if parsed.scheme != "rediss" or not parsed.hostname:
        raise AuditError("production security audit requires an absolute rediss:// URL")


def _find_needle(data: bytes, needles: dict[str, bytes], surface: str) -> None:
    for label, needle in needles.items():
        if needle in data:
            raise AuditError(f"sensitive audit needle {label} was found in {surface}")


def _regular_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []

    def add(candidate: Path) -> None:
        if candidate.suffix.lower() in COMPRESSED_LOG_SUFFIXES:
            raise AuditError("production log exports must be decompressed before security audit")
        files.append(candidate)

    for source in paths:
        if source.is_symlink():
            raise AuditError("log audit paths must not be symbolic links")
        if source.is_file():
            add(source)
            continue
        if not source.is_dir():
            raise AuditError("every log audit path must be an existing file or directory")
        for candidate in sorted(source.rglob("*")):
            if candidate.is_symlink():
                raise AuditError("log audit trees must not contain symbolic links")
            if candidate.is_file():
                add(candidate)
    unique = sorted(set(path.resolve() for path in files), key=str)
    if not unique:
        raise AuditError("at least one exported production log file is required")
    return unique


def _scan_files(
    paths: list[Path],
    needles: dict[str, bytes],
    *,
    surface: str,
    max_bytes: int,
) -> dict[str, Any]:
    if max_bytes < 1:
        raise AuditError("audit byte limit must be positive")
    total = 0
    bundle = hashlib.sha256()
    overlap_size = max(len(value) for value in needles.values()) - 1
    for path in paths:
        digest = hashlib.sha256()
        overlap = b""
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise AuditError(f"{surface} audit exceeds the configured byte limit")
                    _find_needle(overlap + chunk, needles, surface)
                    overlap = (overlap + chunk)[-overlap_size:] if overlap_size else b""
                    digest.update(chunk)
        except OSError as exc:
            raise AuditError(f"could not read {surface} audit input") from exc
        bundle.update(digest.digest())
    return {"files": len(paths), "bytes": total, "bundle_sha256": bundle.hexdigest()}


def _audit_database(
    database: Path,
    needles: dict[str, bytes],
    max_bytes: int,
    session_id: str,
) -> dict[str, Any]:
    if database.is_symlink() or not database.is_file():
        raise AuditError("Cloud database must be an existing regular file, not a symbolic link")
    files = [database]
    for suffix in ("-wal", "-shm"):
        sibling = Path(f"{database}{suffix}")
        if sibling.exists():
            if sibling.is_symlink() or not sibling.is_file():
                raise AuditError("Cloud database WAL/SHM inputs must be regular files")
            files.append(sibling)
    scanned = _scan_files(files, needles, surface="Cloud database/WAL/SHM", max_bytes=max_bytes)
    try:
        with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as cx:
            quick_check = str(cx.execute("PRAGMA quick_check").fetchone()[0])
            columns = [str(row[1]) for row in cx.execute("PRAGMA table_info(relay_cursors)").fetchall()]
            session = cx.execute("SELECT kind FROM sessions WHERE id=?", (session_id,)).fetchone()
            relay_cursors = int(cx.execute("SELECT COUNT(*) FROM relay_cursors WHERE session_id=?", (session_id,)).fetchone()[0])
            commands = int(cx.execute("SELECT COUNT(*) FROM commands WHERE session_id=?", (session_id,)).fetchone()[0])
            events = int(cx.execute("SELECT COUNT(*) FROM events WHERE session_id=?", (session_id,)).fetchone()[0])
    except sqlite3.Error as exc:
        raise AuditError("Cloud database could not be inspected read-only") from exc
    if quick_check != "ok":
        raise AuditError("Cloud database quick_check did not return ok")
    if columns != RELAY_CURSOR_COLUMNS:
        raise AuditError("Cloud relay cursor schema contains missing or unexpected columns")
    if session is None or session[0] != "device_remote":
        raise AuditError("audited Cloud session is missing or is not device_remote")
    if relay_cursors < 2:
        raise AuditError("audited device-remote session has no bidirectional relay cursor evidence")
    if commands != 0 or events != 0:
        raise AuditError("audited device-remote session has forbidden Cloud command/event rows")
    return {
        **scanned,
        "quick_check": quick_check,
        "relay_cursor_columns": columns,
        "session_relay_cursors": relay_cursors,
        "session_commands": commands,
        "session_events": events,
    }


def _audit_redis(
    redis_url: str,
    needles: dict[str, bytes],
    *,
    redis_factory: Callable[[str], Any] | None,
    max_keys: int,
) -> dict[str, int]:
    _validate_redis_url(redis_url)
    if max_keys < 1:
        raise AuditError("Redis audit key limit must be positive")
    if redis_factory is None:
        try:
            import redis
        except ImportError as exc:  # pragma: no cover - deployment dependency guard
            raise AuditError("redis package is required for production security audit") from exc
        redis_factory = lambda url: redis.Redis.from_url(  # noqa: E731
            url,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    client = redis_factory(redis_url)
    count = 0
    try:
        if client.ping() is not True:
            raise AuditError("Redis security audit ping failed")
        for key in client.scan_iter(match="notemeld:relay:*", count=100):
            count += 1
            if count > max_keys:
                raise AuditError("Redis relay key count exceeds the configured audit limit")
            key_bytes = key.encode() if isinstance(key, str) else bytes(key)
            _find_needle(key_bytes, needles, "Redis relay keyspace")
            if not key_bytes.startswith(RELAY_KEY_PREFIX) or not key_bytes.startswith(RELAY_PRESENCE_PREFIX):
                raise AuditError("unexpected Redis relay key may persist payload data")
            value_type = client.type(key)
            if value_type not in {b"string", "string"}:
                raise AuditError("Redis relay presence key has an unexpected data type")
            ttl = client.ttl(key)
            if type(ttl) is not int or ttl <= 0:
                raise AuditError("Redis relay presence key is not ephemeral")
            value = client.get(key)
            if not isinstance(value, (bytes, str)):
                raise AuditError("Redis relay presence value is invalid")
            _find_needle(value.encode() if isinstance(value, str) else value, needles, "Redis relay keyspace")
    except AuditError:
        raise
    except Exception as exc:
        raise AuditError("Redis relay keyspace could not be inspected") from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    return {"keys": count, "ephemeral_presence_keys": count}


def run(
    database: Path,
    log_paths: list[Path],
    redis_url: str,
    needles: dict[str, str],
    *,
    session_id: str,
    redis_factory: Callable[[str], Any] | None = None,
    max_scan_bytes: int = 256 * 1024 * 1024,
    max_redis_keys: int = 10_000,
) -> dict[str, Any]:
    if not isinstance(session_id, str) or not session_id or len(session_id) > 4096:
        raise AuditError("audited device-remote session ID is required")
    encoded = _validate_needles(needles)
    database_result = _audit_database(database, encoded, max_scan_bytes, session_id)
    log_files = _regular_files(log_paths)
    log_result = _scan_files(log_files, encoded, surface="exported production logs", max_bytes=max_scan_bytes)
    redis_result = _audit_redis(
        redis_url,
        encoded,
        redis_factory=redis_factory,
        max_keys=max_redis_keys,
    )
    return {
        "release_checks": {"e_01_cloud_storage_logs_redis": "PASS"},
        "database": database_result,
        "logs": log_result,
        "redis": redis_result,
        "needle_sha256": {
            label: hashlib.sha256(value).hexdigest()
            for label, value in sorted(encoded.items())
        },
    }


def _load_needles(specs: list[str], environ: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for spec in specs:
        if "=" not in spec:
            raise AuditError("--needle must use label=ENVIRONMENT_VARIABLE format")
        label, variable = spec.split("=", 1)
        if not label or not variable or label in result:
            raise AuditError("--needle labels and environment variable names must be unique and non-empty")
        value = environ.get(variable)
        if value is None:
            raise AuditError(f"required audit environment variable is missing for {label}")
        result[label] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True, help="Read-only production cloud.db snapshot or mounted file")
    parser.add_argument("--session-id", required=True, help="Device-remote session retained until this audit completes")
    parser.add_argument("--log", type=Path, action="append", required=True, help="Exported bounded log file or directory; repeat as needed")
    parser.add_argument("--redis-url-env", default="NOTEMELD_CLOUD_RELAY_URL", help="Environment variable containing the rediss:// URL")
    parser.add_argument("--needle", action="append", required=True, help="Sensitive label=ENVIRONMENT_VARIABLE; values never enter argv")
    parser.add_argument("--max-scan-bytes", type=int, default=256 * 1024 * 1024)
    parser.add_argument("--max-redis-keys", type=int, default=10_000)
    args = parser.parse_args()
    try:
        redis_url = os.environ.get(args.redis_url_env)
        if not redis_url:
            raise AuditError("Redis URL environment variable is missing")
        result = run(
            args.database,
            args.log,
            redis_url,
            _load_needles(args.needle, os.environ),
            session_id=args.session_id,
            max_scan_bytes=args.max_scan_bytes,
            max_redis_keys=args.max_redis_keys,
        )
    except AuditError as exc:
        print(f"first-batch security audit failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
