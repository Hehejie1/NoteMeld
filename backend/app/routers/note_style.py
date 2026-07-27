import re
from threading import Thread
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.db import note_style_dao
from app.services.note import NoteGenerator
from app.services.note_style_file_extractors import (
    chunk_source_text,
    extract_source_from_file,
    resolve_uploaded_file_path,
    sanitize_html_to_skeleton,
)
from app.services.note_style_import_service import extract_template_from_text
from app.services.note_style_llm_analyzer import (
    build_template_analysis_prompt,
    build_template_analysis_request,
    parse_compact_template_json,
)
from app.services.note_style_example_generator import with_standard_example_content
from app.services.note_style_schema import NoteStylePayload
from app.services.template_extraction_tasks import (
    cancel_task,
    cleanup_tasks,
    create_task,
    get_latest_task,
    get_task,
    is_task_canceled,
    list_tasks,
    reset_task,
    run_startup_template_task_cleanup,
    update_task,
)
from app.services.web_note import WebNoteGenerator
from app.utils.response import ResponseWrapper as R
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()
TASK_HISTORY_STATUSES = {"pending", "running", "succeeded", "failed", "retrying", "canceled"}


class StyleCreateRequest(NoteStylePayload):
    pass


class StyleUpdateRequest(StyleCreateRequest):
    pass


class StyleExtractTextRequest(BaseModel):
    content: str
    source_name: str = "manual.md"
    provider_id: str = ""
    model_name: str = ""
    user_instruction: str = ""
    current_template: Optional[NoteStylePayload] = None
    generation_mode: str = "create"


class StyleExtractFileRequest(BaseModel):
    file_url: str
    file_name: str
    content_type: str = ""
    provider_id: str = ""
    model_name: str = ""
    user_instruction: str = ""
    current_template: Optional[NoteStylePayload] = None
    generation_mode: str = "create"


class StyleTaskCleanupRequest(BaseModel):
    keep_latest: int = 20
    max_age_days: int = 7


def _try_analyze_with_llm(
    source: dict,
    chunks: list[dict],
    provider_id: str,
    model_name: str,
    user_instruction: str,
    current_template: Optional[dict] = None,
    generation_mode: str = "create",
) -> Optional[dict]:
    if not provider_id or not model_name:
        return None
    prompt = build_template_analysis_prompt(
        source,
        chunks,
        user_instruction,
        current_template=current_template,
        generation_mode=generation_mode,
    )
    request_payload = build_template_analysis_request(prompt)
    gpt = NoteGenerator()._get_gpt(model_name, provider_id)
    if hasattr(gpt, "set_usage_context"):
        gpt.set_usage_context(
            {
                "provider_id": provider_id,
                "model_name": model_name,
                "phase": "note_style_template_extract",
                "request_meta": {"stage": "template_analysis"},
            }
        )
    response = gpt.create_chat_completion(
        request_payload["messages"],
        phase_label="模板分析",
        request_meta={"stage": "note_style_template_extract"},
        timeout=request_payload["timeout"],
        max_tokens=request_payload["max_tokens"],
    )
    content = gpt._extract_message_content(response, "模板分析")
    return parse_compact_template_json(content, current_template=current_template)


def _fallback_template_from_source(source: dict, file_name: str) -> dict:
    if source.get("deterministic_template"):
        return NoteStylePayload(**source["deterministic_template"]).model_dump()
    text = source.get("text") or ""
    result = extract_template_from_text(text or file_name, file_name)
    if source.get("skeleton_hint"):
        result["skeleton_html"] = source["skeleton_hint"]
    return NoteStylePayload(**result).model_dump()


def _build_analysis_summary(source: dict) -> Optional[dict]:
    analysis = source.get("analysis")
    if not isinstance(analysis, dict):
        return None
    summary: dict[str, object] = {}
    if isinstance(analysis.get("router"), dict):
        summary["router"] = analysis["router"]
    if isinstance(analysis.get("replication_score"), dict):
        summary["replication_score"] = analysis["replication_score"]
    prompts = analysis.get("recommended_followup_prompts")
    if isinstance(prompts, list):
        summary["recommended_followup_prompts"] = prompts
    return summary or None


def _task_payload(payload: BaseModel) -> dict:
    return payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()


def _merge_with_current_template(
    result: Optional[dict], current_template: Optional[dict], generation_mode: str
) -> Optional[dict]:
    if result is None or generation_mode != "edit" or not current_template:
        return result

    merged = NoteStylePayload(**current_template).model_dump()
    for key in ["name", "description", "skeleton_html", "style_constraints", "rule_config", "example_content"]:
        if result.get(key):
            merged[key] = result[key]
    if result.get("output_formats"):
        merged["output_formats"] = result["output_formats"]
    return NoteStylePayload(**merged).model_dump()


def _finalize_template_result(result: dict) -> dict:
    return NoteStylePayload(**with_standard_example_content(result)).model_dump()


def _run_text_extraction(task_id: str, payload_data: dict) -> None:
    try:
        update_task(task_id, status="running", stage="extracting", progress=10, messages=["正在提取模板结构"])
        if is_task_canceled(task_id):
            return
        content = (payload_data.get("content") or "").strip()
        source_name = payload_data.get("source_name") or "manual.md"
        current_template = payload_data.get("current_template") or None
        generation_mode = (payload_data.get("generation_mode") or "create").strip().lower() or "create"
        if re.match(r"^https?://", content):
            update_task(task_id, stage="fetching_url", progress=25, messages=["正在抓取网页 HTML"])
            if is_task_canceled(task_id):
                return
            html = WebNoteGenerator.fetch_html(content)
            source = {
                "kind": "url",
                "text": re.sub(r"<[^>]+>", " ", html),
                "warnings": [],
                "skeleton_hint": sanitize_html_to_skeleton(html),
            }
            chunks = chunk_source_text(source["text"] or "")
            result = _try_analyze_with_llm(
                source,
                chunks,
                payload_data.get("provider_id") or "",
                payload_data.get("model_name") or "",
                payload_data.get("user_instruction") or content,
                current_template=current_template,
                generation_mode=generation_mode,
            )
            if result is None:
                result = extract_template_from_text(source["text"], source_name or content)
                result["skeleton_html"] = source["skeleton_hint"]
        else:
            source = {
                "kind": "text",
                "text": content,
                "warnings": [],
                "skeleton_hint": current_template.get("skeleton_html", "") if current_template else "",
            }
            chunks = chunk_source_text(content)
            result = _try_analyze_with_llm(
                source,
                chunks,
                payload_data.get("provider_id") or "",
                payload_data.get("model_name") or "",
                payload_data.get("user_instruction") or content,
                current_template=current_template,
                generation_mode=generation_mode,
            )
            if result is None:
                result = extract_template_from_text(content, source_name)
        result = _merge_with_current_template(result, current_template, generation_mode)
        result = _finalize_template_result(result)
        if is_task_canceled(task_id):
            return
        update_task(
            task_id,
            status="succeeded",
            stage="completed",
            progress=100,
            result=result,
            messages=["已完成模板结构提取"],
        )
    except Exception as exc:
        logger.exception("note style text extraction failed")
        update_task(task_id, status="failed", stage="failed", error=str(exc), progress=100)


def _run_file_extraction(task_id: str, payload_data: dict) -> None:
    try:
        update_task(task_id, status="running", stage="uploaded", progress=5, messages=["已接收文件，准备解析"])
        if is_task_canceled(task_id):
            return
        file_path = resolve_uploaded_file_path(payload_data.get("file_url") or "")
        is_image_request = (
            (payload_data.get("content_type") or "").startswith("image/")
            or (payload_data.get("file_name") or "").lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
        )
        parsing_message = (
            ["正在预处理图片，并行执行 OCR 与第一轮结构 VLM"]
            if is_image_request
            else ["正在解析文件结构"]
        )
        update_task(task_id, stage="parsing", progress=15, messages=parsing_message)
        if is_task_canceled(task_id):
            return
        source = extract_source_from_file(
            file_path,
            payload_data.get("file_name") or "",
            payload_data.get("content_type") or "",
            provider_id=payload_data.get("provider_id") or "",
            model_name=payload_data.get("model_name") or "",
            user_instruction=payload_data.get("user_instruction") or "",
        )
        analysis_summary = _build_analysis_summary(source)
        current_template = payload_data.get("current_template") or None
        generation_mode = (payload_data.get("generation_mode") or "create").strip().lower() or "create"
        chunks = chunk_source_text(source.get("text") or "")
        update_task(
            task_id,
            stage="chunking",
            chunks=chunks,
            progress=35,
            messages=(
                ["已完成 OCR 并行解析、第一轮结构 VLM 和第二轮语义 VLM，准备进行模板补全"]
                if source.get("kind") == "image_structured"
                else ["已完成分块，准备进行 OCR/VLM/LLM 分析"]
            ),
            request_payload={
                **payload_data,
                "analysis_summary": analysis_summary,
            },
        )
        if is_task_canceled(task_id):
            return
        result = None
        llm_error = None
        try:
            update_task(
                task_id,
                stage="llm_analyzing",
                progress=55,
                messages=(
                    ["正在结合图片分析结果补全模板结构"]
                    if source.get("kind") == "image_structured"
                    else ["正在调用模型分析模板风格"]
                ),
            )
            if is_task_canceled(task_id):
                return
            result = _try_analyze_with_llm(
                source,
                chunks,
                payload_data.get("provider_id") or "",
                payload_data.get("model_name") or "",
                payload_data.get("user_instruction") or "",
                current_template=current_template,
                generation_mode=generation_mode,
            )
        except Exception as exc:
            llm_error = str(exc)
            logger.warning("note style LLM analysis failed, fallback enabled: %s", exc)
        if result is None:
            update_task(task_id, stage="merging", progress=75, messages=["模型分析不可用，使用确定性结构回退"])
            if is_task_canceled(task_id):
                return
            result = _fallback_template_from_source(source, payload_data.get("file_name") or "imported")
        result = _merge_with_current_template(result, current_template, generation_mode)
        result = _finalize_template_result(result)
        if is_task_canceled(task_id):
            return
        messages = ["已完成模板结构提取"]
        if source.get("warnings"):
            messages.extend(source["warnings"])
        if llm_error:
            messages.append(f"模型分析失败，已回退：{llm_error}")
        update_task(
            task_id,
            status="succeeded",
            stage="completed",
            progress=100,
            result=result,
            messages=messages,
            request_payload={
                **payload_data,
                "analysis_summary": analysis_summary,
            },
        )
    except Exception as exc:
        logger.exception("note style file extraction failed")
        update_task(task_id, status="failed", stage="failed", error=str(exc), progress=100)


def _start_background(task_id: str, request_type: str, payload_data: dict) -> None:
    target = _run_file_extraction if request_type == "file" else _run_text_extraction
    Thread(target=target, args=(task_id, payload_data), daemon=True).start()


@router.get("/note_styles")
def list_note_styles():
    return R.success(data=note_style_dao.list_styles())


@router.post("/note_styles")
def create_note_style(payload: StyleCreateRequest):
    try:
        item = note_style_dao.create_style(payload)
        return R.success(data=item)
    except Exception as e:
        logger.exception("create_note_style failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/note_styles/{style_id}")
def update_note_style(style_id: str, payload: StyleUpdateRequest):
    try:
        item = note_style_dao.update_style(style_id, payload)
        if item is None:
            raise HTTPException(status_code=404, detail="风格模板不存在")
        return R.success(data=item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/note_styles/{style_id}")
def delete_note_style(style_id: str):
    try:
        ok = note_style_dao.delete_style(style_id)
        if not ok:
            raise HTTPException(status_code=404, detail="风格模板不存在")
        return R.success()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/note_styles/extract_text")
def extract_note_style_from_text(payload: StyleExtractTextRequest):
    task = create_task()
    payload_data = _task_payload(payload)
    update_task(
        task["task_id"],
        request_type="text",
        request_payload=payload_data,
        user_message={
            "content": payload.content,
            "source_name": payload.source_name,
            "model_name": payload.model_name,
            "provider_id": payload.provider_id,
        },
        provider_id=payload.provider_id,
        model_name=payload.model_name,
        messages=["任务已创建，正在排队处理"],
    )
    _start_background(task["task_id"], "text", payload_data)
    return R.success(data=get_task(task["task_id"]))


@router.post("/note_styles/extract_file")
def extract_note_style_from_file(payload: StyleExtractFileRequest):
    task = create_task()
    payload_data = _task_payload(payload)
    update_task(
        task["task_id"],
        request_type="file",
        request_payload=payload_data,
        user_message={
            "file_name": payload.file_name,
            "content": payload.user_instruction,
            "model_name": payload.model_name,
            "provider_id": payload.provider_id,
        },
        provider_id=payload.provider_id,
        model_name=payload.model_name,
        file_name=payload.file_name,
        messages=["任务已创建，正在排队处理"],
    )
    _start_background(task["task_id"], "file", payload_data)
    return R.success(data=get_task(task["task_id"]))


@router.post("/note_styles/extraction_tasks/{task_id}/retry")
def retry_note_style_extraction_task(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="模板提取任务不存在")
    request_type = task.get("request_type")
    payload_data = task.get("request_payload") or {}
    if request_type not in {"text", "file"} or not payload_data:
        raise HTTPException(status_code=400, detail="模板提取任务无法重试")
    reset_task(task_id, messages=["已重新提交任务，正在排队处理"])
    _start_background(task_id, request_type, payload_data)
    return R.success(data=get_task(task_id))


@router.get("/note_styles/extraction_tasks/latest")
def get_latest_note_style_extraction_task():
    return R.success(data=get_latest_task())


@router.get("/note_styles/extraction_tasks")
def list_note_style_extraction_tasks(limit: int = 20, offset: int = 0, status: Optional[str] = None):
    normalized_status = (status or "").strip().lower() or None
    if normalized_status == "all":
        normalized_status = None
    if normalized_status and normalized_status not in TASK_HISTORY_STATUSES:
        raise HTTPException(status_code=400, detail="不支持的模板任务状态筛选值")
    return R.success(
        data=list_tasks(
            limit=max(1, min(limit, 100)),
            offset=max(offset, 0),
            status=normalized_status,
        )
    )


@router.post("/note_styles/extraction_tasks/{task_id}/cancel")
def cancel_note_style_extraction_task(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="模板提取任务不存在")
    return R.success(data=cancel_task(task_id))


@router.post("/note_styles/extraction_tasks/cleanup")
def cleanup_note_style_extraction_tasks(payload: StyleTaskCleanupRequest):
    deleted = cleanup_tasks(
        keep_latest=max(payload.keep_latest, 0),
        max_age_seconds=max(payload.max_age_days, 0) * 24 * 60 * 60,
    )
    return R.success(data={"deleted": deleted})


@router.get("/note_styles/extraction_tasks/{task_id}")
def get_note_style_extraction_task(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="模板提取任务不存在")
    return R.success(data=task)


def run_template_task_startup_cleanup() -> int:
    return run_startup_template_task_cleanup()
