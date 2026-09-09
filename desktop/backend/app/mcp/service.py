from __future__ import annotations

import json
import asyncio
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import unquote

import httpx

from app.services.conversation_import_service import ConversationImportRequest, ConversationImportService
from app.services.note_import_service import NoteImportService, NoteTitleAmbiguousError
from app.utils.storage_paths import note_output_dir
from app.agent_host.capabilities import NoteMeldCapabilityRegistry
from app.agent_host.drivers.tools import NoteMeldToolDriver


FORBIDDEN_KEYS = {
    "task_id",
    "taskId",
    "source_id",
    "transcript",
    "graph",
    "path",
    "file_path",
    "markdown_path",
    "source_path",
    "contribution_path",
    "graph_path",
}


TOOL_DEFINITIONS = [
    {
        "name": "generate_note",
        "description": "Generate a structured Markdown note from a video or web URL. Use this when the user provides a link and asks to 做成笔记, 生成笔记, 总结视频, 学习笔记, or 结构化笔记. The model/provider, style, and screenshots can be omitted; NoteMeld will choose safe local defaults. Waits for Markdown until maxWaitSeconds; on timeout returns taskId for get_task/get_note.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Online video or web URL."},
                "videoUrl": {"type": "string", "description": "Alias of url for BiliNote-style clients."},
                "model": {"type": "string", "description": "Optional model name from list_models. Auto-selected when omitted."},
                "modelName": {"type": "string", "description": "Alias of model."},
                "providerId": {"type": "string", "description": "Optional NoteMeld provider id from list_models. Auto-selected when omitted."},
                "platform": {"type": "string", "description": "douyin / bilibili / youtube / kuaishou / web_link. Auto-detected if omitted."},
                "style": {"type": "string", "description": "Optional NoteMeld style. Uses the default note style when omitted."},
                "format": {"type": "array", "items": {"type": "string"}, "description": "Optional output format tags."},
                "screenshot": {"type": "boolean", "description": "Whether to capture screenshots. Defaults to false.", "default": False},
                "maxWaitSeconds": {"type": "number", "description": "Maximum seconds to wait for Markdown.", "default": 600},
                "pollIntervalSeconds": {"type": "number", "description": "Polling interval in seconds.", "default": 3},
            },
            "required": [],
        },
    },
    {
        "name": "get_task",
        "description": "Check a NoteMeld note generation task status by taskId.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "taskId": {"type": "string", "description": "Task id returned by generate_note."},
            },
            "required": ["taskId"],
        },
    },
    {
        "name": "get_note",
        "description": "Fetch generated Markdown by taskId.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "taskId": {"type": "string", "description": "Task id returned by generate_note."},
                "noteId": {"type": "string", "description": "Alias of taskId for BiliNote-style clients."},
            },
            "required": [],
        },
    },
    {
        "name": "list_models",
        "description": "List enabled local NoteMeld models and providers without exposing API keys.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "notemeld_import_note",
        "description": "Import an existing markdown note and schedule LLM Wiki extraction.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Note title."},
                "content": {"type": "string", "description": "Markdown note content."},
                "format": {"type": "string", "description": "Input format, defaults to markdown.", "default": "markdown"},
                "source_url": {"type": "string", "description": "Optional original URL."},
                "source_type": {"type": "string", "description": "Source type, defaults to manual.", "default": "manual"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags."},
                "metadata": {"type": "object", "description": "Optional metadata."},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "notemeld_search_notes",
        "description": "Search imported/generated notes by title.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Title keyword to search."},
                "limit": {"type": "integer", "description": "Maximum number of notes.", "default": 10, "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
        },
    },
    {
        "name": "notemeld_create_note",
        "description": "通过公开 Note capability 创建一篇 Note，可选关联父 Note。",
        "inputSchema": {"type": "object", "properties": {
            "title": {"type": "string"}, "content": {"type": "string"},
            "source_url": {"type": "string"}, "parent_note_id": {"type": "string"},
            "request_id": {"type": "string"}}, "required": ["title", "content"]},
    },
    {
        "name": "notemeld_link_notes",
        "description": "通过公开 Note capability 关联两篇 Note。",
        "inputSchema": {"type": "object", "properties": {
            "source_note_id": {"type": "string"}, "target_note_id": {"type": "string"},
            "kind": {"type": "string"}, "request_id": {"type": "string"}},
            "required": ["source_note_id", "target_note_id"]},
    },
    {
        "name": "notemeld_note_relations",
        "description": "读取 Note 的关系、来源和 provenance。",
        "inputSchema": {"type": "object", "properties": {"note_id": {"type": "string"}},
            "required": ["note_id"]},
    },
    {
        "name": "notemeld_read_note",
        "description": "Read a note by title without exposing internal task IDs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Exact note title."},
            },
            "required": ["title"],
        },
    },
    {
        "name": "notemeld_search_wiki",
        "description": "Search structured LLM Wiki entities, concepts, claims, evidence, and relations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Question or keyword for structured Wiki search."},
                "limit": {"type": "integer", "description": "Maximum number of Wiki results.", "default": 5, "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "notemeld_read_wiki_page",
        "description": "Read an allowlisted Wiki concept/entity page by title.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_type": {"type": "string", "enum": ["concept", "entity"], "description": "Allowlisted Wiki page type."},
                "title": {"type": "string", "description": "Exact Wiki page title."},
            },
            "required": ["page_type", "title"],
        },
    },
    {
        "name": "notemeld_document_to_markdown",
        "description": "将支持的文档转换为带 provenance 的 GFM Markdown 中间产物；不直接创建 Note。",
        "inputSchema": {"type": "object", "properties": {
            "file_url": {"type": "string"}, "file_name": {"type": "string"},
            "source": {"type": "object"}, "request_id": {"type": "string"},
        }, "required": ["file_url", "file_name"]},
    },
    {
        "name": "notemeld_image_ocr",
        "description": "识别图片文字并保留基础 bbox、顺序和置信度；不做 ASCII 转换，也不直接创建 Note。",
        "inputSchema": {"type": "object", "properties": {
            "file_url": {"type": "string"}, "file_name": {"type": "string"},
            "source": {"type": "object"}, "request_id": {"type": "string"},
        }, "required": ["file_url", "file_name"]},
    },
    {
        "name": "notemeld_video_fetch",
        "description": "获取视频/音频来源的媒体元信息，可按需准备视频资源；不总结、不创建 Note。",
        "inputSchema": {"type": "object", "properties": {
            "source_url": {"type": "string"}, "platform": {"type": "string"},
            "include_video": {"type": "boolean"}, "source": {"type": "object"},
            "request_id": {"type": "string"},
        }, "required": ["source_url"]},
    },
    {
        "name": "notemeld_audio_extract",
        "description": "从视频或音频来源提取可继续处理的音频产物；不总结、不创建 Note。",
        "inputSchema": {"type": "object", "properties": {
            "source_url": {"type": "string"}, "platform": {"type": "string"},
            "source": {"type": "object"}, "request_id": {"type": "string"},
        }, "required": ["source_url"]},
    },
    {
        "name": "notemeld_audio_transcribe",
        "description": "优先使用平台字幕，否则调用 NoteMeld 转写引擎输出带时间段的文本；不总结、不创建 Note。",
        "inputSchema": {"type": "object", "properties": {
            "source_url": {"type": "string"}, "platform": {"type": "string"},
            "source": {"type": "object"}, "request_id": {"type": "string"},
        }, "required": ["source_url"]},
    },
    {
        "name": "notemeld_video_frames",
        "description": "按时间点提取视频帧并执行基础 OCR，返回时间戳和位置结果；不做 ASCII、不创建 Note。",
        "inputSchema": {"type": "object", "properties": {
            "source_url": {"type": "string"}, "platform": {"type": "string"},
            "timestamps": {"type": "array", "items": {"type": "number"}},
            "source": {"type": "object"}, "request_id": {"type": "string"},
        }, "required": ["source_url"]},
    },
]

RESOURCE_DEFINITIONS = [
    {
        "uri": "notemeld://notes/by-title/{title}",
        "name": "Note by title",
        "description": "Read a note by URL-encoded title.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "notemeld://wiki/concepts/{title}",
        "name": "Wiki concept by title",
        "description": "Read an allowlisted Wiki concept page by URL-encoded title.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "notemeld://wiki/entities/{title}",
        "name": "Wiki entity by title",
        "description": "Read an allowlisted Wiki entity page by URL-encoded title.",
        "mimeType": "text/markdown",
    },
]


class McpToolService:
    def __init__(
        self,
        import_service: Optional[ConversationImportService] = None,
        note_service: Optional[NoteImportService] = None,
        wiki_search: Any = None,
        wiki_store: Any = None,
        generation_client: Any = None,
        model_catalog: Optional[Callable[[], list[dict[str, Any]]]] = None,
    ):
        self.import_service = import_service or ConversationImportService()
        self.note_service = note_service or NoteImportService()
        self.wiki_search = wiki_search
        self.wiki_store = wiki_store
        self.generation_client = generation_client or LocalNoteGenerationClient()
        self.model_catalog = model_catalog or list_enabled_model_catalog
        self.capabilities = NoteMeldCapabilityRegistry()

    def list_tools(self) -> list[dict[str, Any]]:
        return TOOL_DEFINITIONS

    def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None) -> Any:
        args = arguments or {}
        capability_names = {
            "notemeld_create_note": "note:create",
            "notemeld_link_notes": "note:link",
            "notemeld_note_relations": "note:relations",
            "notemeld_document_to_markdown": "document:to_markdown",
            "notemeld_image_ocr": "image:ocr",
            "notemeld_video_fetch": "video:fetch",
            "notemeld_audio_extract": "audio:extract",
            "notemeld_audio_transcribe": "audio:transcribe",
            "notemeld_video_frames": "video:frames",
        }
        if name in capability_names:
            call_id = str(args.get("request_id") or uuid.uuid4())
            result = asyncio.run(NoteMeldToolDriver(self.capabilities).invoke(
                {"name": capability_names[name], "call_id": call_id, "arguments": args},
                {"actor_id": "mcp"},
            ))
            output = result.get("output", {}) if isinstance(result, dict) else {}
            if not output.get("ok"):
                raise ValueError(str((output.get("error") or {}).get("message") or "MCP capability failed"))
            return output.get("result")
        if name == "generate_note":
            return self.generate_note(args)
        if name == "get_task":
            return self.generation_client.get_task(_required_task_id(args))
        if name == "get_note":
            return self.generation_client.read_note(_required_task_id(args))
        if name == "list_models":
            return {"models": self.model_catalog()}
        if name == "notemeld_import_note":
            result = self.import_service.import_markdown(ConversationImportRequest(import_mode="note", **args)).model_dump()
            result.pop("document_task_id", None)
            return _sanitize(result)
        if name == "notemeld_search_notes":
            return _sanitize(self.note_service.search_notes(str(args.get("query") or ""), int(args.get("limit") or 10)))
        if name == "notemeld_read_note":
            try:
                payload = self.note_service.read_note_by_title(str(args.get("title") or ""))
            except NoteTitleAmbiguousError as exc:
                raise ValueError(str(exc)) from exc
            return _sanitize(payload or {})
        if name == "notemeld_search_wiki":
            wiki_search = self.wiki_search or self._default_wiki_search()
            return _sanitize(wiki_search.search(str(args.get("query") or ""), limit=int(args.get("limit") or 5)))
        if name == "notemeld_read_wiki_page":
            return _sanitize(self.read_wiki_page(str(args.get("page_type") or ""), str(args.get("title") or "")) or {})
        raise ValueError(f"Unsupported MCP tool: {name}")

    def generate_note(self, args: dict[str, Any]) -> dict[str, Any]:
        payload = _build_generate_payload(args, self.model_catalog)
        max_wait_seconds = max(0.0, float(args.get("maxWaitSeconds", 600)))
        poll_interval_seconds = max(0.0, float(args.get("pollIntervalSeconds", 3)))
        submitted = self.generation_client.submit_note(payload)
        task_id = _normalize_task_id(submitted)
        if not task_id:
            raise ValueError("NoteMeld did not return a taskId")

        deadline = time.monotonic() + max_wait_seconds
        last_status: dict[str, Any] = {"taskId": task_id, "status": "PENDING", "message": submitted.get("message", "")}
        while True:
            status_payload = self.generation_client.get_task(task_id)
            last_status = _normalize_task_payload(status_payload, task_id)
            status = str(last_status.get("status") or "").upper()
            markdown = _extract_markdown(last_status)
            if status == "SUCCESS":
                if not markdown:
                    note = self.generation_client.read_note(task_id)
                    markdown = str(note.get("markdown") or "")
                return {
                    **last_status,
                    "taskId": task_id,
                    "status": "SUCCESS",
                    "markdown": markdown,
                }
            if status in {"FAILED", "CANCELED", "NOT_FOUND"}:
                return {
                    **last_status,
                    "taskId": task_id,
                    "status": status,
                    "isError": True,
                    "message": last_status.get("message") or "NoteMeld task failed",
                }
            if time.monotonic() >= deadline:
                return {
                    **last_status,
                    "taskId": task_id,
                    "next": f"继续调用 get_task(taskId={task_id})，完成后调用 get_note(taskId={task_id}) 获取 Markdown。",
                }
            if poll_interval_seconds > 0:
                time.sleep(poll_interval_seconds)

    def list_resources(self) -> list[dict[str, Any]]:
        return RESOURCE_DEFINITIONS

    def read_resource(self, uri: str) -> Optional[dict[str, str]]:
        if uri.startswith("notemeld://notes/by-title/"):
            title = unquote(uri.removeprefix("notemeld://notes/by-title/"))
            try:
                note = self.note_service.read_note_by_title(title)
            except NoteTitleAmbiguousError as exc:
                raise ValueError(str(exc)) from exc
            if not note:
                return None
            return {
                "uri": uri,
                "mimeType": "text/markdown",
                "text": str(note.get("content") or ""),
            }

        for prefix, page_type in (
            ("notemeld://wiki/concepts/", "concept"),
            ("notemeld://wiki/entities/", "entity"),
        ):
            if uri.startswith(prefix):
                title = unquote(uri.removeprefix(prefix))
                page = self.read_wiki_page(page_type, title)
                if not page:
                    return None
                return {
                    "uri": uri,
                    "mimeType": "text/markdown",
                    "text": str(page.get("markdown") or ""),
                }
        return None

    def read_wiki_page(self, page_type: str, title: str) -> Optional[dict[str, Any]]:
        normalized_type = page_type.strip()
        if normalized_type not in {"concept", "entity"}:
            return None
        normalized_title = title.strip()
        if not normalized_title:
            return None

        wiki_store = self.wiki_store or self._default_wiki_store()
        for page in wiki_store.list_file_pages():
            if page.get("type") == normalized_type and page.get("title") == normalized_title:
                return wiki_store.get_file_page(normalized_type, page.get("id", ""))
        return None

    @staticmethod
    def _default_wiki_search():
        from app.services.wiki_search import WikiSearch

        return WikiSearch(note_output_dir() / "wiki")

    @staticmethod
    def _default_wiki_store():
        from app.services.wiki_store import WikiStore

        return WikiStore(base_dir=note_output_dir() / "wiki")


class LocalNoteGenerationClient:
    def __init__(
        self,
        api_base_url: str = "http://127.0.0.1:8483/api",
        output_dir: Optional[Path] = None,
        timeout: float = 15.0,
        http_client_factory: Optional[Callable[[float], Any]] = None,
        conversation_preparer: Optional[Callable[[dict[str, Any]], str]] = None,
    ):
        self.api_base_url = api_base_url.rstrip("/")
        self.output_dir = output_dir or note_output_dir()
        self.timeout = timeout
        self.http_client_factory = http_client_factory or (lambda timeout: httpx.Client(timeout=timeout))
        self.conversation_preparer = conversation_preparer or prepare_mcp_note_conversation

    def submit_note(self, payload: dict[str, Any]) -> dict[str, Any]:
        prepared_payload = dict(payload)
        if not str(prepared_payload.get("conversation_id") or "").strip():
            prepared_payload["conversation_id"] = self.conversation_preparer(prepared_payload)
        with self.http_client_factory(self.timeout) as client:
            response = client.post(f"{self.api_base_url}/generate_note", json=prepared_payload)
        response.raise_for_status()
        return _unwrap_api_response(response.json())

    def get_task(self, task_id: str) -> dict[str, Any]:
        safe_task_id = _safe_task_id(task_id)
        with self.http_client_factory(self.timeout) as client:
            response = client.get(f"{self.api_base_url}/task_status/{safe_task_id}")
        response.raise_for_status()
        return _normalize_task_payload(_unwrap_api_response(response.json()), safe_task_id)

    def read_note(self, task_id: str) -> dict[str, Any]:
        safe_task_id = _safe_task_id(task_id)
        result_path = self.output_dir / f"{safe_task_id}.json"
        if not result_path.exists():
            status = self.get_task(safe_task_id)
            markdown = _extract_markdown(status)
            if markdown:
                return {"taskId": safe_task_id, "status": status.get("status", "SUCCESS"), "markdown": markdown}
            raise ValueError(f"Note result not found for taskId: {safe_task_id}")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        markdown = _extract_markdown(payload)
        return {"taskId": safe_task_id, "status": "SUCCESS", "markdown": markdown, "result": payload}


def list_enabled_model_catalog() -> list[dict[str, Any]]:
    from app.db.engine import get_db
    from app.db.models.models import Model
    from app.db.models.providers import Provider

    db = next(get_db())
    try:
        rows = (
            db.query(Model, Provider)
            .join(Provider, Model.provider_id == Provider.id)
            .filter(Provider.enabled == 1)
            .order_by(Provider.name.asc(), Model.id.asc())
            .all()
        )
        return [
            {
                "providerId": provider.id,
                "providerName": provider.name,
                "model": model.model_name,
                "modelId": model.id,
                "baseUrl": provider.base_url,
            }
            for model, provider in rows
        ]
    finally:
        db.close()


def prepare_mcp_note_conversation(payload: dict[str, Any]) -> str:
    from app.services.conversation_store import append_message, upsert_conversation

    conversation_id = f"mcp-{uuid.uuid4()}"
    source_url = str(payload.get("video_url") or "").strip()
    extras = str(payload.get("extras") or "").strip()
    user_content = source_url if not extras else f"{source_url}\n{extras}"
    upsert_conversation(
        {
            "id": conversation_id,
            "mode": "note",
            "title": source_url[:48] or "MCP 笔记生成",
            "status": "PENDING",
            "message": "MCP 笔记任务已提交",
            "platform": payload.get("platform") or "",
            "noteState": "generating",
            "formData": {**payload, "conversation_id": conversation_id},
        }
    )
    append_message(
        conversation_id,
        {
            "id": f"mcp-user-{uuid.uuid4()}",
            "role": "user",
            "message_type": "user_input",
            "content": user_content,
            "status": "success",
            "meta": {"source": "mcp"},
        },
    )
    return conversation_id


def _build_generate_payload(args: dict[str, Any], model_catalog: Callable[[], list[dict[str, Any]]]) -> dict[str, Any]:
    url = str(args.get("url") or args.get("videoUrl") or "").strip()
    if not url:
        raise ValueError("generate_note requires url or videoUrl")
    model_name, provider_id = _resolve_generation_model(args, model_catalog)
    return {
        "video_url": url,
        "platform": _detect_platform(url, str(args.get("platform") or "")),
        "quality": "medium",
        "screenshot": bool(args.get("screenshot", False)),
        "link": bool(args.get("link", False)),
        "model_name": model_name,
        "provider_id": provider_id,
        "format": args.get("format") or [],
        "style": args.get("style") or "",
        "extras": args.get("extras") or "",
        "force_web_fallback": bool(args.get("forceWebFallback", False)),
        "enable_refine_engine": bool(args.get("enableRefineEngine", False)),
    }


def _resolve_generation_model(
    args: dict[str, Any],
    model_catalog: Callable[[], list[dict[str, Any]]],
) -> tuple[str, str]:
    requested_model = str(args.get("model") or args.get("modelName") or "").strip()
    requested_provider_id = str(args.get("providerId") or args.get("provider_id") or "").strip()
    if requested_model and requested_provider_id:
        return requested_model, requested_provider_id

    models = model_catalog()
    if not models:
        raise ValueError("generate_note requires at least one enabled NoteMeld model")

    selected = _select_generation_model(models, requested_model, requested_provider_id)
    model_name = str(selected.get("model") or selected.get("modelName") or "").strip()
    provider_id = str(selected.get("providerId") or selected.get("provider_id") or "").strip()
    if not model_name or not provider_id:
        raise ValueError("enabled NoteMeld model is missing model/providerId")
    return requested_model or model_name, requested_provider_id or provider_id


def _select_generation_model(
    models: list[dict[str, Any]],
    requested_model: str,
    requested_provider_id: str,
) -> dict[str, Any]:
    requested_model_lower = requested_model.lower()
    requested_provider_lower = requested_provider_id.lower()
    for model in models:
        model_name = str(model.get("model") or model.get("modelName") or "").strip()
        provider_id = str(model.get("providerId") or model.get("provider_id") or "").strip()
        if requested_model and model_name.lower() != requested_model_lower:
            continue
        if requested_provider_id and provider_id.lower() != requested_provider_lower:
            continue
        return model
    raise ValueError("requested NoteMeld model/providerId is not enabled")


def _detect_platform(url: str, explicit_platform: str) -> str:
    normalized = explicit_platform.strip().lower()
    if normalized:
        return normalized
    lowered = url.lower()
    if "douyin.com" in lowered:
        return "douyin"
    if "bilibili.com" in lowered or "b23.tv" in lowered:
        return "bilibili"
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "youtube"
    if "kuaishou.com" in lowered:
        return "kuaishou"
    return "web_link"


def _required_task_id(args: dict[str, Any]) -> str:
    task_id = str(args.get("taskId") or args.get("task_id") or args.get("noteId") or "").strip()
    if not task_id:
        raise ValueError("taskId is required")
    return _safe_task_id(task_id)


def _safe_task_id(task_id: str) -> str:
    normalized = task_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", normalized):
        raise ValueError("Invalid taskId")
    if "/" in normalized or "\\" in normalized or ".." in normalized:
        raise ValueError("Invalid taskId")
    return normalized


def _normalize_task_id(payload: dict[str, Any]) -> str:
    return str(payload.get("taskId") or payload.get("task_id") or payload.get("id") or "").strip()


def _normalize_task_payload(payload: dict[str, Any], task_id: str) -> dict[str, Any]:
    normalized = dict(payload or {})
    normalized["taskId"] = str(normalized.get("taskId") or normalized.get("task_id") or task_id)
    normalized.pop("task_id", None)
    return normalized


def _unwrap_api_response(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Unexpected NoteMeld API response")
    if "data" in payload and ("code" in payload or "msg" in payload):
        if payload.get("code", 0) != 0:
            raise ValueError(str(payload.get("msg") or "NoteMeld API error"))
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            raise ValueError("Unexpected NoteMeld API data")
        return data
    return payload


def _extract_markdown(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    direct = payload.get("markdown")
    if isinstance(direct, str) and direct:
        return direct
    result = payload.get("result")
    if isinstance(result, dict):
        markdown = result.get("markdown")
        if isinstance(markdown, str):
            return markdown
    return ""


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize(item)
            for key, item in value.items()
            if key not in FORBIDDEN_KEYS
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
