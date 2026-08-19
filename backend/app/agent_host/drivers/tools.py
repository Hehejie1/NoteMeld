from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Mapping

from app.utils.logger import get_logger


logger = get_logger(__name__)

_SAFE_MESSAGES = {
    "unknown_tool": "工具不存在或未授权",
    "invalid_arguments": "工具参数不符合能力契约",
    "permission_denied": "没有权限执行该工具",
    "business_error": "工具未能完成业务请求",
    "tool_execution_error": "工具执行失败",
}
_KNOWN_PRODUCT_CODES = frozenset(_SAFE_MESSAGES)


def _descriptor_schema(tool: Any) -> Mapping[str, Any] | None:
    if isinstance(tool, Mapping):
        schema = tool.get("input_schema") or tool.get("parameters")
    else:
        schema = getattr(tool, "input_schema", None) or getattr(tool, "parameters", None)
    return schema if isinstance(schema, Mapping) else None


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _valid_value(value: Any, schema: Mapping[str, Any]) -> bool:
    expected = schema.get("type")
    if isinstance(expected, str) and not _matches_type(value, expected):
        return False
    if isinstance(expected, list) and not any(
        isinstance(item, str) and _matches_type(value, item) for item in expected
    ):
        return False
    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        maximum_length = schema.get("maxLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            return False
        if isinstance(maximum_length, int) and len(value) > maximum_length:
            return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            return False
        if isinstance(maximum, (int, float)) and value > maximum:
            return False
    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping) and any(
            not _valid_value(item, item_schema) for item in value
        ):
            return False
    return True


def _arguments_match_schema(arguments: Mapping[str, Any], schema: Mapping[str, Any] | None) -> bool:
    if not schema:
        return True
    if schema.get("type") == "object" and not isinstance(arguments, Mapping):
        return False
    required = schema.get("required") or []
    if isinstance(required, list) and any(
        not isinstance(name, str) or name not in arguments for name in required
    ):
        return False
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for name, value in arguments.items():
            property_schema = properties.get(name)
            if isinstance(property_schema, Mapping) and not _valid_value(value, property_schema):
                return False
    if schema.get("additionalProperties") is False and isinstance(properties, Mapping):
        if any(name not in properties for name in arguments):
            return False
    return True


def _tool_result(call_id: str, *, result: Any = None, error_code: str | None = None) -> dict[str, Any]:
    if error_code is None:
        output = {"ok": True, "result": result}
    else:
        output = {
            "ok": False,
            "error": {
                "code": error_code,
                "message": _SAFE_MESSAGES[error_code],
            },
        }
    return {"call_id": call_id, "output": output}


def _product_error_code(error: Exception) -> str:
    if isinstance(error, PermissionError):
        return "permission_denied"
    code = str(getattr(error, "code", "") or "")
    if code in _KNOWN_PRODUCT_CODES:
        return code
    if code in {"invalid_input", "invalid_argument", "invalid_arguments"}:
        return "invalid_arguments"
    if code in {"unknown_capability", "unknown_tool"}:
        return "unknown_tool"
    if isinstance(error, FileNotFoundError):
        return "business_error"
    if isinstance(error, ValueError):
        return "invalid_arguments"
    return "tool_execution_error"


class NoteMeldToolDriver:
    """Thin SDK ToolDriver adapter over a product capability provider."""

    def __init__(self, registry: Any = None, *, provider: Any = None):
        self.registry = registry or provider
        if self.registry is None:
            raise ValueError("tool registry or provider is required")

    async def describe(self, names: list[str]) -> list[dict[str, Any]]:
        result = self.registry.describe(names)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, list):
            raise TypeError("tool registry describe must return a list")
        return [dict(item) for item in result if isinstance(item, Mapping)]

    async def invoke(
        self,
        call: Mapping[str, Any],
        context: Mapping[str, Any],
        on_progress: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        name = str(call.get("tool_name") or call.get("name") or "").strip()
        call_id = str(call.get("call_id") or call.get("id") or "")
        if not call_id:
            raise ValueError("tool call id is required")
        if not name:
            return _tool_result(call_id, error_code="invalid_arguments")
        arguments = call.get("arguments", {})
        if not isinstance(arguments, dict):
            return _tool_result(call_id, error_code="invalid_arguments")
        get_tool = getattr(self.registry, "get_tool", None)
        try:
            tool = get_tool(name) if callable(get_tool) else None
        except Exception as error:  # noqa: BLE001 - product capability boundary
            code = _product_error_code(error)
            logger.warning("Agent product tool lookup failed: category=%s", code)
            return _tool_result(call_id, error_code=code)
        if callable(get_tool) and tool is None:
            return _tool_result(call_id, error_code="unknown_tool")
        if not _arguments_match_schema(arguments, _descriptor_schema(tool)):
            return _tool_result(call_id, error_code="invalid_arguments")
        progress = on_progress or (lambda _event: None)

        async def update(payload: dict[str, Any]) -> None:
            result = progress(payload)
            if asyncio.iscoroutine(result):
                await result

        class Signal:
            aborted = False
            session_id = str(context.get("session_id") or "")
            turn_id = str(context.get("turn_id") or "")

        try:
            result = await self.registry.invoke(
                name,
                arguments,
                call_id,
                Signal(),
                update,
            )
            if hasattr(result, "model_dump"):
                result = result.model_dump()
            return _tool_result(call_id, result=result)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - product capability boundary
            code = _product_error_code(error)
            logger.warning("Agent product tool failed: tool=%s category=%s", name, code)
            return _tool_result(call_id, error_code=code)
