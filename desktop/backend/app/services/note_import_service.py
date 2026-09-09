from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import uuid
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from app.models.summary_input import MetaContext, PageContext, SummaryInput
from app.services.note_read_errors import NoteTitleAmbiguousError
from app.utils.storage_paths import note_output_dir


logger = logging.getLogger(__name__)


class ImportNoteRequest(BaseModel):
    title: str
    content: str
    format: str = "markdown"
    source_url: Optional[str] = None
    source_type: str = "manual"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImportNoteResult(BaseModel):
    note_id: str
    title: str
    status: str
    wiki_status: str
    message: str
    diagnostics: list[str] = Field(default_factory=list)
    retry_actions: list[dict[str, str]] = Field(default_factory=list)


def _default_document_writer(payload: dict[str, Any]) -> dict:
    from app.services.note_document_store import upsert_note_document

    return upsert_note_document(payload)


def _default_document_by_id_reader(note_id: str) -> Optional[dict[str, Any]]:
    from app.db.engine import get_db
    from app.db.models.conversation import NoteDocument

    db = next(get_db())
    try:
        row = db.query(NoteDocument).filter(NoteDocument.task_id == note_id).first()
        if row is None:
            return None
        return {
            "task_id": row.task_id,
            "conversation_id": row.conversation_id,
            "title": row.title or "",
            "content": row.content or "",
            "source_url": row.source_url or "",
            "platform": row.platform or "",
            "model_name": row.model_name or "",
            "style": row.style or "",
            "status": row.status or "SUCCESS",
            "wiki_status": row.wiki_status or "pending",
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "deleted_at": row.deleted_at,
        }
    finally:
        db.close()


def _default_document_compensator(
    note_id: str,
    previous: Optional[dict[str, Any]],
) -> None:
    from app.db.engine import get_db
    from app.db.models.conversation import NoteDocument

    db = next(get_db())
    try:
        row = db.query(NoteDocument).filter(NoteDocument.task_id == note_id).first()
        if previous is None:
            if row is not None:
                db.delete(row)
        else:
            if row is None:
                row = NoteDocument(task_id=note_id)
                db.add(row)
            row.conversation_id = previous["conversation_id"]
            row.title = previous.get("title", "")
            row.content = previous.get("content", "")
            row.source_url = previous.get("source_url", "")
            row.platform = previous.get("platform", "")
            row.model_name = previous.get("model_name", "")
            row.style = previous.get("style", "")
            row.status = previous.get("status", "SUCCESS")
            row.wiki_status = previous.get("wiki_status", "pending")
            row.created_at = previous.get("created_at")
            row.updated_at = previous.get("updated_at")
            row.deleted_at = previous.get("deleted_at")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _default_vector_store_factory():
    from app.services.vector_store import VectorStoreManager

    return VectorStoreManager()


def _default_wiki_scheduler(**kwargs) -> None:
    from app.services.wiki_enhancement_queue import schedule_wiki_extraction

    schedule_wiki_extraction(**kwargs)


def _default_document_searcher(query: str, limit: int) -> list[dict[str, Any]]:
    from app.services.note_document_store import search_note_documents_by_title

    return search_note_documents_by_title(query, limit=limit)


def _default_document_reader(title: str) -> Optional[dict[str, Any]]:
    from app.services.note_document_store import read_note_document_by_title

    return read_note_document_by_title(title)


class NoteImportService:
    _revision_locks_guard = threading.Lock()
    _revision_locks: dict[str, threading.RLock] = {}

    def __init__(
        self,
        output_dir: Path | None = None,
        document_writer: Callable[[dict[str, Any]], dict] | None = None,
        document_searcher: Callable[[str, int], list[dict[str, Any]]] | None = None,
        document_reader: Callable[[str], Optional[dict[str, Any]]] | None = None,
        document_by_id_reader: Callable[[str], Optional[dict[str, Any]]] | None = None,
        document_compensator: Callable[[str, Optional[dict[str, Any]]], None] | None = None,
        vector_store_factory: Callable[[], Any] | None = None,
        wiki_scheduler: Callable[..., None] | None = None,
        gpt: Any = None,
    ):
        self.output_dir = Path(output_dir or note_output_dir())
        self.document_writer = document_writer or _default_document_writer
        self.document_searcher = document_searcher or _default_document_searcher
        self.document_reader = document_reader or _default_document_reader
        self.document_by_id_reader = document_by_id_reader or _default_document_by_id_reader
        self.document_compensator = document_compensator or _default_document_compensator
        self.vector_store_factory = vector_store_factory or _default_vector_store_factory
        self.wiki_scheduler = wiki_scheduler or _default_wiki_scheduler
        self.gpt = gpt

    def import_note(
        self,
        request: ImportNoteRequest,
        conversation_id: Optional[str] = None,
    ) -> ImportNoteResult:
        return self.publish_revision(request, conversation_id, note_id=None)

    def publish_revision(
        self,
        request: ImportNoteRequest,
        conversation_id: Optional[str],
        note_id: str | None = None,
        *,
        commit_hook: Callable[[str], None] | None = None,
    ) -> ImportNoteResult:
        title = request.title.strip()
        content = request.content.strip()
        if not title:
            raise ValueError("title is required")
        if not content:
            raise ValueError("content is required")

        note_id = str(note_id or f"note_{uuid.uuid4().hex}").strip()
        if not note_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-" for character in note_id):
            raise ValueError("note_id contains unsafe characters")

        with self._revision_lock(note_id):
            return self._publish_revision_locked(
                request,
                conversation_id,
                note_id,
                title,
                content,
                commit_hook,
            )

    def _publish_revision_locked(
        self,
        request: ImportNoteRequest,
        conversation_id: Optional[str],
        note_id: str,
        title: str,
        content: str,
        commit_hook: Callable[[str], None] | None,
    ) -> ImportNoteResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        note_path = self.output_dir / f"{note_id}.json"
        summary_input_path = self.output_dir / f"{note_id}_summary_input.json"
        previous_artifacts = {
            note_path: note_path.read_bytes() if note_path.is_file() else None,
            summary_input_path: (
                summary_input_path.read_bytes() if summary_input_path.is_file() else None
            ),
        }
        previous_document = deepcopy(self.document_by_id_reader(note_id))
        summary_input = self._build_summary_input(note_id, request, title, content)
        document_payload = self._document_payload(
            note_id,
            request,
            title,
            content,
            conversation_id,
        )
        written_artifacts: list[Path] = []
        try:
            self._write_note_result(note_id, request, title, content)
            written_artifacts.append(note_path)
            self._write_summary_input(summary_input_path, summary_input)
            written_artifacts.append(summary_input_path)
        except Exception:
            self._restore_artifacts(
                {
                    path: previous_artifacts[path]
                    for path in written_artifacts
                }
            )
            raise
        try:
            self.document_writer(document_payload)
            if commit_hook is not None:
                commit_hook(note_id)
        except Exception:
            self._compensate_revision(
                note_id,
                previous_artifacts,
                previous_document,
            )
            raise

        diagnostics: list[str] = []
        retry_actions: list[dict[str, str]] = []
        if not self._index_note(note_id):
            diagnostics.append("vector_index_failed")
            retry_actions.append(
                {
                    "kind": "vector_reindex",
                    "endpoint": "/api/migration/reindex",
                    "task_id": note_id,
                }
            )
        wiki_status = "pending"
        if not self._schedule_wiki(note_id, summary_input, content):
            diagnostics.append("wiki_schedule_failed")
            if self._has_saved_model_for_wiki_retry(summary_input):
                retry_actions.append(
                    {
                        "kind": "wiki_retry",
                        "endpoint": f"/api/wiki/retry/{note_id}",
                        "task_id": note_id,
                    }
                )
            wiki_status = "partial"
            try:
                self.document_writer({**document_payload, "wiki_status": wiki_status})
            except Exception as exc:
                logger.warning(
                    "更新导入笔记 partial Wiki 状态失败: note_id=%s error=%s",
                    note_id,
                    exc,
                )
                diagnostics.append("wiki_status_update_failed")

        return ImportNoteResult(
            note_id=note_id,
            title=title,
            status="partial" if diagnostics else "imported",
            wiki_status=wiki_status,
            message=(
                "笔记已存储，部分后处理可重试"
                if diagnostics
                else "笔记已存储，Wiki 将在后台解析"
            ),
            diagnostics=diagnostics,
            retry_actions=retry_actions,
        )

    @classmethod
    def _revision_lock(cls, note_id: str) -> threading.RLock:
        with cls._revision_locks_guard:
            lock = cls._revision_locks.get(note_id)
            if lock is None:
                lock = threading.RLock()
                cls._revision_locks[note_id] = lock
            return lock

    def search_notes(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        normalized_query = query.strip()
        if not normalized_query:
            return []
        safe_limit = min(max(int(limit or 10), 1), 50)
        return [self._public_note_summary(item) for item in self.document_searcher(normalized_query, safe_limit)]

    def read_note_by_title(self, title: str) -> Optional[dict[str, Any]]:
        normalized_title = title.strip()
        if not normalized_title:
            return None
        try:
            document = self.document_reader(normalized_title)
        except NoteTitleAmbiguousError:
            raise
        except ValueError as exc:
            raise NoteTitleAmbiguousError(str(exc)) from exc
        if not document:
            return None
        return self._public_note_detail(document)

    def _write_note_result(self, note_id: str, request: ImportNoteRequest, title: str, content: str) -> None:
        payload = {
            "markdown": content,
            "transcript": {"language": "", "full_text": content, "segments": []},
            "audio_meta": {
                "title": title,
                "platform": request.source_type,
                "duration": 0,
                "raw_info": {
                    "title": title,
                    "webpage_url": request.source_url or "",
                    "tags": request.tags,
                    **request.metadata,
                },
            },
        }
        note_path = self.output_dir / f"{note_id}.json"
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._atomic_replace_bytes(note_path, encoded)

    def _atomic_replace_bytes(self, destination: Path, payload: bytes) -> None:
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.stem}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                tmp_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            tmp_path.replace(destination)
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    def _write_summary_input(
        self,
        destination: Path,
        summary_input: SummaryInput,
    ) -> None:
        encoded = json.dumps(
            asdict(summary_input),
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        self._atomic_replace_bytes(destination, encoded)

    def _restore_artifacts(
        self,
        previous_artifacts: dict[Path, bytes | None],
    ) -> None:
        errors: list[Exception] = []
        for path, previous in previous_artifacts.items():
            try:
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    self._atomic_replace_bytes(path, previous)
            except Exception as exc:
                errors.append(exc)
                logger.error("补偿恢复 Note 文件失败: path=%s", path)
        if errors:
            raise RuntimeError("note artifact compensation failed") from errors[0]

    def _compensate_revision(
        self,
        note_id: str,
        previous_artifacts: dict[Path, bytes | None],
        previous_document: Optional[dict[str, Any]],
    ) -> None:
        errors: list[Exception] = []
        try:
            self.document_compensator(note_id, previous_document)
        except Exception as exc:
            errors.append(exc)
            logger.error("补偿恢复 NoteDocument 失败: note_id=%s", note_id)
        try:
            self._restore_artifacts(previous_artifacts)
        except Exception as exc:
            errors.append(exc)
            logger.error("补偿恢复 Note 持久化文件失败: note_id=%s", note_id)
        if errors:
            raise RuntimeError("note revision compensation failed") from errors[0]

    @staticmethod
    def _document_payload(
        note_id: str,
        request: ImportNoteRequest,
        title: str,
        content: str,
        conversation_id: Optional[str],
    ) -> dict[str, Any]:
        return {
            "task_id": note_id,
            "conversation_id": conversation_id or note_id,
            "title": title,
            "content": content,
            "source_url": request.source_url or "",
            "platform": request.source_type,
            "model_name": "import",
            "style": request.format,
            "status": "SUCCESS",
            "wiki_status": "pending",
        }

    def _index_note(self, note_id: str) -> bool:
        try:
            self.vector_store_factory().index_task(note_id)
            return True
        except Exception as exc:
            logger.warning("导入笔记向量索引失败（不影响导入）: note_id=%s error=%s", note_id, exc)
            return False

    def _schedule_wiki(
        self,
        note_id: str,
        summary_input: SummaryInput,
        content: str,
    ) -> bool:
        try:
            self.wiki_scheduler(
                output_dir=self.output_dir,
                task_id=note_id,
                summary_input=summary_input,
                markdown=content,
                gpt=self.gpt,
                update_status=self._update_wiki_status,
            )
            return True
        except Exception as exc:
            logger.warning("导入笔记 Wiki 调度失败（不影响导入）: note_id=%s error=%s", note_id, exc)
            return False

    @staticmethod
    def _has_saved_model_for_wiki_retry(summary_input: SummaryInput) -> bool:
        provider_id = str(summary_input.user_options.get("provider_id") or "").strip()
        model_name = str(summary_input.user_options.get("model_name") or "").strip()
        if not provider_id or not model_name:
            return False
        try:
            from app.services.model import ModelService
            from app.services.provider import ProviderService

            provider = ProviderService.get_provider_by_id(provider_id)
            if not provider:
                return False
            ModelService.build_saved_model_config(provider, model_name)
            return True
        except Exception:
            return False

    def _build_summary_input(
        self,
        note_id: str,
        request: ImportNoteRequest,
        title: str,
        content: str,
    ) -> SummaryInput:
        return SummaryInput(
            input_id=note_id,
            input_type=request.source_type or "manual",
            source_url=request.source_url,
            platform=request.source_type,
            title=title,
            user_goal=None,
            user_options={
                "format": request.format,
                "tags": request.tags,
                "metadata": request.metadata,
                "provider_id": request.metadata.get("provider_id"),
                "model_name": request.metadata.get("model_name"),
            },
            page_context=PageContext(
                title=title,
                url=request.source_url or "",
                page_type=request.source_type or "manual",
                main_text_summary=content[:1200],
            ),
            transcript_context=None,
            vision_context=None,
            social_context=None,
            meta_context=MetaContext(
                resource_type=request.source_type or "manual",
                platform=request.source_type,
                raw={"imported": True, "tags": request.tags, **request.metadata},
            ),
        )

    @staticmethod
    def _update_wiki_status(note_id: str, wiki_status: str) -> None:
        try:
            from app.services.note_document_store import update_note_document_wiki_status

            update_note_document_wiki_status(note_id, wiki_status)
        except Exception as exc:
            logger.warning("更新导入笔记 Wiki 状态失败: note_id=%s error=%s", note_id, exc)

    @staticmethod
    def _public_note_summary(document: dict[str, Any]) -> dict[str, Any]:
        content = str(document.get("content") or "")
        return {
            "note_id": document.get("taskId") or document.get("note_id") or "",
            "title": document.get("title") or "",
            "snippet": _snippet(content),
            "source_url": document.get("sourceUrl") or "",
            "source_type": document.get("platform") or "",
            "wiki_status": document.get("wikiStatus") or "pending",
            "updated_at": document.get("updatedAt") or "",
        }

    @staticmethod
    def _public_note_detail(document: dict[str, Any]) -> dict[str, Any]:
        return {
            "note_id": document.get("taskId") or document.get("note_id") or "",
            "title": document.get("title") or "",
            "content": document.get("content") or "",
            "source_url": document.get("sourceUrl") or "",
            "source_type": document.get("platform") or "",
            "wiki_status": document.get("wikiStatus") or "pending",
            "updated_at": document.get("updatedAt") or "",
        }


def _snippet(content: str, max_length: int = 220) -> str:
    compact = " ".join(line.strip() for line in content.splitlines() if line.strip())
    return compact[:max_length]
