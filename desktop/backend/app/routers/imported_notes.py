from fastapi import APIRouter, Query

from app.services.conversation_import_service import ConversationImportRequest, ConversationImportService
from app.services.note_document_store import list_note_library
from app.services.note_import_service import NoteImportService, NoteTitleAmbiguousError
from app.utils.response import ResponseWrapper as R


router = APIRouter()


@router.get("/notes/library")
def note_library(
    q: str = "",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    wiki_status: str | None = None,
    status: str | None = None,
):
    return R.success(
        list_note_library(query=q, offset=offset, limit=limit, wiki_status=wiki_status, status=status)
    )


@router.post("/notes/import")
def import_note(data: ConversationImportRequest):
    try:
        result = ConversationImportService().import_markdown(data)
        return R.success(result.model_dump())
    except ValueError as exc:
        return R.error(str(exc), code=400)


@router.get("/notes/search")
def search_notes(q: str, limit: int = 10):
    return R.success(NoteImportService().search_notes(q, limit=limit))


@router.get("/notes/read")
def read_note(title: str):
    try:
        payload = NoteImportService().read_note_by_title(title)
    except NoteTitleAmbiguousError as exc:
        return R.error(str(exc), code=409)
    if payload is None:
        return R.error("笔记不存在", code=404)
    return R.success(payload)
