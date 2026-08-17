"""Atomic local descriptor shared by UI, CLI, and desktop Host launchers."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentRuntimeDescriptor:
    pid: int
    base_url: str
    token: str
    sdk_version: str = "0.1.0"
    abi_version: int = 2
    schema_version: str = "1"
    started_at: str = ""
    data_root: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pid": self.pid,
            "base_url": self.base_url,
            "token": self.token,
            "sdk_version": self.sdk_version,
            "abi_version": self.abi_version,
            "started_at": self.started_at,
            "data_root": self.data_root,
        }


def descriptor_path(data_root: str | Path) -> Path:
    return Path(data_root) / "run" / "agent-runtime.json"


def write_descriptor(data_root: str | Path, descriptor: AgentRuntimeDescriptor) -> Path:
    target = descriptor_path(data_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(descriptor.as_dict(), handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        try:
            target.chmod(0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def read_descriptor(data_root: str | Path) -> AgentRuntimeDescriptor | None:
    target = descriptor_path(data_root)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        if raw.get("schema_version") != "1" or not isinstance(raw.get("pid"), int):
            return None
        if not all(isinstance(raw.get(key), str) and raw[key] for key in ("base_url", "token", "sdk_version", "data_root")):
            return None
        if raw.get("abi_version") != 2:
            return None
        return AgentRuntimeDescriptor(
            pid=raw["pid"], base_url=raw["base_url"], token=raw["token"],
            sdk_version=raw["sdk_version"], abi_version=2, schema_version="1",
            started_at=raw.get("started_at", ""), data_root=raw["data_root"],
        )
    except (OSError, ValueError, TypeError):
        return None


def remove_descriptor(data_root: str | Path) -> None:
    try:
        descriptor_path(data_root).unlink()
    except FileNotFoundError:
        pass
