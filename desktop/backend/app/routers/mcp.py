import json
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.mcp.auth import validate_mcp_request
from app.mcp.service import McpToolService


router = APIRouter(dependencies=[Depends(validate_mcp_request)])


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Any] = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/mcp")
def handle_mcp(payload: JsonRpcRequest):
    service = McpToolService()
    try:
        if payload.method == "initialize":
            return _result(payload.id, _initialize_result(payload.params))
        if payload.method == "notifications/initialized":
            return _result(payload.id, {})
        if payload.method == "ping":
            return _result(payload.id, {})
        if payload.method == "tools/list":
            return _result(payload.id, {"tools": service.list_tools()})
        if payload.method == "tools/call":
            name = str(payload.params.get("name") or "")
            arguments = payload.params.get("arguments") or {}
            tool_result = service.call_tool(name, arguments)
            return _result(payload.id, _tool_call_result(tool_result))
        if payload.method == "resources/list":
            return _result(payload.id, {"resources": service.list_resources()})
        if payload.method == "resources/read":
            uri = str(payload.params.get("uri") or "")
            content = service.read_resource(uri)
            if content is None:
                return _error(payload.id, -32602, "Unsupported or missing resource")
            return _result(payload.id, {"contents": [content]})
        return _error(payload.id, -32601, f"Unsupported method: {payload.method}")
    except ValueError as exc:
        return _error(payload.id, -32602, str(exc))
    except Exception as exc:
        return _error(payload.id, -32603, str(exc))


def _initialize_result(params: dict[str, Any]) -> dict[str, Any]:
    requested_version = str(params.get("protocolVersion") or "2024-11-05")
    return {
        "protocolVersion": requested_version,
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
        },
        "serverInfo": {
            "name": "notemeld",
            "version": "0.1.0",
        },
    }


def _tool_call_result(tool_result: Any) -> dict[str, Any]:
    structured_content = _structured_content(tool_result)
    display_text = ""
    if isinstance(tool_result, dict) and isinstance(tool_result.get("markdown"), str):
        display_text = tool_result["markdown"]
    else:
        display_text = json.dumps(tool_result, ensure_ascii=False, indent=2)
    return {
        "content": [
            {
                "type": "text",
                "text": display_text,
            }
        ],
        "structuredContent": structured_content,
        "isError": bool(isinstance(tool_result, dict) and tool_result.get("isError")),
    }


def _structured_content(tool_result: Any) -> dict[str, Any]:
    if isinstance(tool_result, dict):
        return tool_result
    if isinstance(tool_result, list):
        return {"items": tool_result}
    if tool_result is None:
        return {}
    return {"value": tool_result}


def _result(request_id: Optional[Any], result: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content={"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id: Optional[Any], code: int, message: str) -> JSONResponse:
    return JSONResponse(
        content={
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
    )
