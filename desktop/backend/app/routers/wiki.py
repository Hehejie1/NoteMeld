from fastapi import APIRouter, HTTPException

from app.services.wiki_store import WikiStore
from app.utils.storage_paths import note_output_dir
from app.utils.response import ResponseWrapper as R


router = APIRouter(prefix="/wiki")


def _wiki_store() -> WikiStore:
    return WikiStore(base_dir=note_output_dir() / "wiki")


@router.get("/graph")
def get_wiki_graph():
    return R.success(_wiki_store().read_graph())


@router.get("/communities")
def get_wiki_communities():
    return R.success(_wiki_store().read_community_index())


@router.get("/communities/{community_id}")
def get_wiki_community(community_id: int):
    community = _wiki_store().read_community_index().get("communities", {}).get(str(community_id))
    if community is None:
        raise HTTPException(status_code=404, detail="Wiki community not found")
    return R.success(community)


@router.get("/pages")
def list_wiki_pages():
    return R.success(_wiki_store().list_pages())


@router.get("/pages/{page_id}")
def get_wiki_page(page_id: str):
    page = _wiki_store().get_page(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Wiki page not found")
    return R.success(page)


@router.get("/articles/{source_id}")
def get_wiki_article(source_id: str):
    article = _wiki_store().get_article(source_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Wiki article not found")
    return R.success(article)


@router.get("/file-pages")
def list_wiki_file_pages():
    return R.success(_wiki_store().list_file_pages())


@router.get("/file-pages/{page_type}/{page_id}")
def get_wiki_file_page(page_type: str, page_id: str):
    page = _wiki_store().get_file_page(page_type, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Wiki file page not found")
    return R.success(page)
