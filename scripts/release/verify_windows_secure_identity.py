#!/usr/bin/env python3
"""Exercise the real Windows Credential Manager Host identity path."""

from __future__ import annotations

import hashlib
import json
import platform
import uuid

from app.cloud_sync.secure_identity import (
    OsIdentityStore,
    _windows_credential_delete,
)


def run() -> dict[str, str]:
    if platform.system() != "Windows":
        raise RuntimeError("Windows secure identity smoke must run on Windows")
    service = f"com.notemeld.desktop.host.release-smoke.{uuid.uuid4()}"
    store = OsIdentityStore(service)
    try:
        created = store.load_or_create()
        loaded = store.load_or_create()
        if loaded != created:
            raise RuntimeError("Windows Credential Manager identity did not round-trip")
        return {
            "status": "PASS",
            "platform": "Windows",
            "store": "Credential Manager",
            "public_key_sha256": hashlib.sha256(created.public_key).hexdigest(),
        }
    finally:
        _windows_credential_delete(f"{service}.private")
        _windows_credential_delete(f"{service}.public")


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
