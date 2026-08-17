from __future__ import annotations

import json
import os

from app.core.agent_runtime_descriptor import (
    AgentRuntimeDescriptor,
    descriptor_path,
    read_descriptor,
    remove_descriptor,
    write_descriptor,
)


def _descriptor(root: str) -> AgentRuntimeDescriptor:
    return AgentRuntimeDescriptor(
        pid=os.getpid(),
        base_url="http://127.0.0.1:8765",
        token="test-token",
        sdk_version="0.2.0",
        abi_version=2,
        data_root=root,
        started_at="2026-08-18T00:00:00Z",
    )


def test_descriptor_is_atomic_private_and_round_trips(tmp_path):
    root = str(tmp_path)
    path = write_descriptor(root, _descriptor(root))

    assert path == descriptor_path(root)
    assert path.stat().st_mode & 0o777 == 0o600
    assert read_descriptor(root) == _descriptor(root)
    assert not list(path.parent.glob(f".{path.name}.*"))


def test_descriptor_rejects_incompatible_sdk_abi_or_data_root(tmp_path):
    root = str(tmp_path)
    path = write_descriptor(root, _descriptor(root))
    raw = json.loads(path.read_text())

    for key, value in (("abi_version", 1), ("data_root", ""), ("sdk_version", "")):
        candidate = dict(raw)
        candidate[key] = value
        path.write_text(json.dumps(candidate))
        assert read_descriptor(root) is None


def test_remove_descriptor_is_idempotent(tmp_path):
    root = str(tmp_path)
    write_descriptor(root, _descriptor(root))
    remove_descriptor(root)
    remove_descriptor(root)
    assert read_descriptor(root) is None
