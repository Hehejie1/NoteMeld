from __future__ import annotations

import hashlib
import re


def make_device_id(platform: str, platform_unique_id: str) -> str:
    """Create a stable, non-reversible device label for cloud registration.

    Platform adapters supply a persisted vendor/app-install identifier (never a
    raw serial number). The digest prevents that identifier from becoming part
    of URLs, logs or the cloud database while the platform prefix keeps IDs
    diagnosable and cross-platform namespaces distinct.
    """
    normalized_platform = re.sub(r"[^a-z0-9_-]", "-", platform.strip().lower()).strip("-")
    if not normalized_platform or len(normalized_platform) > 24:
        raise ValueError("invalid device platform")
    if not platform_unique_id or len(platform_unique_id) > 512:
        raise ValueError("platform unique id is required")
    digest = hashlib.sha256(f"notemeld-device-v1:{normalized_platform}:{platform_unique_id}".encode()).hexdigest()[:32]
    return f"{normalized_platform}-{digest}"
