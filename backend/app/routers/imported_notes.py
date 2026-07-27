from fastapi import APIRouter

from app.services.conversation_import_service import ConversationImportRequest, ConversationImportService
from app.services.note_import_service import NoteImportService, NoteTitleAmbiguousError
from app.utils.response import ResponseWrapper as R


router = APIRouter()


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
