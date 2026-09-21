from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter

from app.models.whiteboard import SafeId
from app.services.conversation_asset_store import ConversationAssetStore
from app.services.file_ingest_service import detect_uploaded_file_kind
from app.services.whiteboard_repository import WhiteboardRepository
from app.utils.storage_paths import upload_dir


FileKind = Literal["markdown", "audio", "video", "document", "image"]
_SAFE_ID = TypeAdapter(SafeId)


class WhiteboardAssetRegistrationService:
    """Registers an existing validated upload as a board-owned conversation asset."""

    def __init__(
        self,
        *,
        repository: WhiteboardRepository,
        asset_store: ConversationAssetStore | None = None,
        uploads_root: str | Path | None = None,
    ) -> None:
        self._repository = repository
        self._asset_store = asset_store or ConversationAssetStore()
        self._uploads_root = Path(uploads_root or upload_dir()).resolve()

    def register(
        self,
        conversation_id: str,
        whiteboard_id: str,
        *,
        upload_id: str,
        file_name: str,
        content_type: str,
        file_kind: FileKind,
    ) -> dict[str, str]:
        # The board lookup is the authority for conversation ownership.
        self._repository.get(conversation_id, whiteboard_id)
        normalized_upload_id = _SAFE_ID.validate_python(upload_id.strip())
        normalized_file_name = self._safe_file_name(file_name)
        normalized_content_type = content_type.strip() or "application/octet-stream"
        normalized_content_type = self._bounded_text(
            normalized_content_type, "content_type", 200
        )
        physical_file = self._resolve_upload(normalized_upload_id)
        if Path(normalized_file_name).suffix.lower() != physical_file.suffix.lower():
            raise ValueError("file extension does not match upload")
        if detect_uploaded_file_kind(normalized_file_name, normalized_content_type) != file_kind:
            raise ValueError("file_kind does not match upload metadata")

        source_url = f"/api/uploads/{normalized_upload_id}"
        digest = hashlib.sha256(
            f"{conversation_id}\0{normalized_upload_id}".encode("utf-8")
        ).hexdigest()[:32]
        asset_id = f"asset_whiteboard_{digest}"
        self._asset_store.create_asset(
            {
                "asset_id": asset_id,
                "conversation_id": conversation_id,
                "title": Path(normalized_file_name).stem or "白板文件",
                "content": f"Whiteboard file asset: {normalized_file_name}",
                "format": "file",
                "file_name": normalized_file_name,
                "source_url": source_url,
                "source_type": "whiteboard_file",
                "metadata": {
                    "content_type": normalized_content_type,
                    "file_kind": file_kind,
                    "upload_id": normalized_upload_id,
                    "whiteboard_id": whiteboard_id,
                },
            }
        )
        return {
            "asset_id": asset_id,
            "upload_id": normalized_upload_id,
            "source_url": source_url,
            "file_name": normalized_file_name,
            "content_type": normalized_content_type,
            "file_kind": file_kind,
        }

    def _resolve_upload(self, upload_id: str) -> Path:
        if not self._uploads_root.is_dir():
            raise FileNotFoundError("upload not found")
        candidates = sorted(
            candidate.resolve()
            for candidate in self._uploads_root.iterdir()
            if candidate.is_file()
            and (candidate.name == upload_id or candidate.name.startswith(f"{upload_id}."))
        )
        if len(candidates) != 1 or self._uploads_root not in candidates[0].parents:
            raise FileNotFoundError("upload not found")
        return candidates[0]

    @staticmethod
    def _safe_file_name(value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 500 or Path(normalized).name != normalized:
            raise ValueError("invalid file_name")
        if any(ord(character) < 32 for character in normalized):
            raise ValueError("invalid file_name")
        return normalized

    @staticmethod
    def _bounded_text(value: str, field_name: str, limit: int) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > limit:
            raise ValueError(f"invalid {field_name}")
        if any(ord(character) < 32 for character in normalized):
            raise ValueError(f"invalid {field_name}")
        return normalized
