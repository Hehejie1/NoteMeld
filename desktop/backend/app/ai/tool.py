"""Tool / Type schema：TypeBox 等价的 JSON Schema 构建器 + Tool 定义。

Type 静态方法产出标准 JSON Schema dict，可直接传给 OpenAI function calling 的
``parameters`` 字段，也可用于 pydantic 校验。

设计参考 pi-ai 的 TypeBox 等价实现，但用纯 Python dict 产出 JSON Schema，
避免引入额外依赖。

示例::

    schema = Type.Object({
        "task_id": Type.String(description="任务 ID"),
        "keyword": Type.Optional(Type.String(description="搜索关键词")),
    }, required=["task_id"])
    # → {"type": "object", "properties": {"task_id": {...}, "keyword": {...}}, "required": ["task_id"]}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


class Type:
    """JSON Schema 构建器，产出与 OpenAI function calling 兼容的参数 schema。"""

    @staticmethod
    def Object(
        properties: dict[str, dict],
        required: list[str] | None = None,
        description: str | None = None,
    ) -> dict:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required is not None:
            schema["required"] = required
        if description:
            schema["description"] = description
        return schema

    @staticmethod
    def String(description: str | None = None, enum: list[str] | None = None) -> dict:
        schema: dict[str, Any] = {"type": "string"}
        if description:
            schema["description"] = description
        if enum is not None:
            schema["enum"] = enum
        return schema

    @staticmethod
    def Number(description: str | None = None) -> dict:
        schema: dict[str, Any] = {"type": "number"}
        if description:
            schema["description"] = description
        return schema

    @staticmethod
    def Integer(description: str | None = None) -> dict:
        schema: dict[str, Any] = {"type": "integer"}
        if description:
            schema["description"] = description
        return schema

    @staticmethod
    def Boolean(description: str | None = None) -> dict:
        schema: dict[str, Any] = {"type": "boolean"}
        if description:
            schema["description"] = description
        return schema

    @staticmethod
    def Array(
        items: dict,
        description: str | None = None,
    ) -> dict:
        schema: dict[str, Any] = {"type": "array", "items": items}
        if description:
            schema["description"] = description
        return schema

    @staticmethod
    def Enum(values: list[str], description: str | None = None) -> dict:
        schema: dict[str, Any] = {"type": "string", "enum": values}
        if description:
            schema["description"] = description
        return schema

    @staticmethod
    def Optional(t: dict) -> dict:
        """标记一个字段为可选（不放入 required 列表）。

        TypeBox 的 Optional 语义是「这个字段可以不传」，在 JSON Schema 中
        通过不出现在 ``required`` 数组里来表达。这里返回原 schema 不变，
        由 Object 的 required 列表控制是否必填。
        """
        return t


@dataclass
class Tool:
    """Agent 工具定义。

    Attributes:
        name: 工具名称，供 LLM 调用。
        description: 工具描述，供 LLM 理解用途。
        parameters: JSON Schema dict（由 Type.* 构建），描述参数结构。
        label: 展示用标签（可选，供 UI 显示）。
        execution_mode: 执行模式，``parallel`` 或 ``serial``，默认 ``serial``。
        execute: 异步执行函数，签名为
            ``async (call_id, params, signal, on_update) -> ToolResult``。
    """

    name: str
    description: str
    parameters: dict
    label: str | None = None
    execution_mode: Literal["parallel", "serial"] = "serial"
    execute: Callable[..., Any] | None = None

    def to_openai_function(self) -> dict:
        """转换为 OpenAI function calling 格式。

        产出 ``{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}``，
        与现有 ``chat_tools.TOOLS`` 格式一致，保证兼容。
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
