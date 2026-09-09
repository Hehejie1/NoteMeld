from __future__ import annotations

from pathlib import Path


def validate_path_component(value: str, field_name: str) -> str:
    candidate = str(value or "").strip()
    if (
        not candidate
        or candidate in {".", ".."}
        or "/" in candidate
        or "\\" in candidate
        or "\x00" in candidate
        or len(candidate) > 160
    ):
        raise ValueError(f"invalid migration {field_name}")
    return candidate


def ensure_child_path(root_dir: Path, target_path: Path, field_name: str) -> Path:
    root = root_dir.resolve()
    target = target_path.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"invalid migration {field_name}") from exc
    return target
