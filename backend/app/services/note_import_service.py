from __future__ import annotations

import json
import logging
import uuid
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


def _default_document_writer(payload: dict[str, Any]) -> dict:
    from app.services.note_document_store import upsert_note_document

    return upsert_note_document(payload)


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
    def __init__(
        self,
        output_dir: Path | None = None,
        document_writer: Callable[[dict[str, Any]], dict] | None = None,
        document_searcher: Callable[[str, int], list[dict[str, Any]]] | None = None,
        document_reader: Callable[[str], Optional[dict[str, Any]]] | None = None,
        vector_store_factory: Callable[[], Any] | None = None,
        wiki_scheduler: Callable[..., None] | None = None,
        gpt: Any = None,
    ):
        self.output_dir = Path(output_dir or note_output_dir())
        self.document_writer = document_writer or _default_document_writer
        self.document_searcher = document_searcher or _default_document_searcher
        self.document_reader = document_reader or _default_document_reader
        self.vector_store_factory = vector_store_factory or _default_vector_store_factory
        self.wiki_scheduler = wiki_scheduler or _default_wiki_scheduler
        self.gpt = gpt

    def import_note(
        self,
        request: ImportNoteRequest,
        conversation_id: Optional[str] = None,
    ) -> ImportNoteResult:
        title = request.title.strip()
        content = request.content.strip()
        if not title:
            raise ValueError("title is required")
        if not content:
            raise ValueError("content is required")

        note_id = f"note_{uuid.uuid4().hex}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._write_note_result(note_id, request, title, content)

        self.document_writer(
            {
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
        )
        self._index_note(note_id)
        self._schedule_wiki(note_id, request, title, content)

        return ImportNoteResult(
            note_id=note_id,
            title=title,
            status="imported",
            wiki_status="pending",
            message="笔记已存储，Wiki 将在后台解析",
        )

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
        tmp_path = note_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(note_path)

    def _index_note(self, note_id: str) -> None:
        try:
            self.vector_store_factory().index_task(note_id)
        except Exception as exc:
            logger.warning("导入笔记向量索引失败（不影响导入）: note_id=%s error=%s", note_id, exc)

    def _schedule_wiki(self, note_id: str, request: ImportNoteRequest, title: str, content: str) -> None:
        try:
            self.wiki_scheduler(
                output_dir=self.output_dir,
                task_id=note_id,
                summary_input=self._build_summary_input(note_id, request, title, content),
                markdown=content,
                gpt=self.gpt,
                update_status=self._update_wiki_status,
            )
        except Exception as exc:
            logger.warning("导入笔记 Wiki 调度失败（不影响导入）: note_id=%s error=%s", note_id, exc)

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
            user_options={"format": request.format, "tags": request.tags, "metadata": request.metadata},
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
