from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.storage_paths import note_output_dir


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationAssetStore:
    def __init__(self, output_dir: Path | None = None):
        base_dir = Path(output_dir) if output_dir else note_output_dir() / "conversation_assets"
        self.output_dir = Path(base_dir)

    def create_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        conversation_id = str(payload.get("conversation_id") or "").strip()
        title = str(payload.get("title") or "").strip()
        content = str(payload.get("content") or "").strip()
        if not conversation_id:
            raise ValueError("conversation_id is required")
        if not title:
            raise ValueError("title is required")
        if not content:
            raise ValueError("content is required")

        asset_id = str(payload.get("asset_id") or f"asset_{uuid.uuid4().hex}")
        item = {
            "asset_id": asset_id,
            "conversation_id": conversation_id,
            "title": title,
            "content": content,
            "format": str(payload.get("format") or "markdown"),
            "source_url": str(payload.get("source_url") or ""),
            "source_type": str(payload.get("source_type") or "manual"),
            "file_name": str(payload.get("file_name") or ""),
            "tags": list(payload.get("tags") or []),
            "metadata": dict(payload.get("metadata") or {}),
            "created_at": str(payload.get("created_at") or _now_iso()),
            "updated_at": str(payload.get("updated_at") or _now_iso()),
        }

        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = self.output_dir / f"{asset_id}.json"
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        return item

    def list_assets(self, conversation_id: str) -> list[dict[str, Any]]:
        normalized = str(conversation_id or "").strip()
        if not normalized or not self.output_dir.exists():
            return []

        items = []
        for path in sorted(self.output_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict) and payload.get("conversation_id") == normalized:
                items.append(payload)
        return items
