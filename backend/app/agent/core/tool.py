"""AgentTool 接口与 ToolCall/ToolResult 数据结构。

与 P0 notemeld-ai 的 ``Tool`` 解耦：AgentTool 是 agent-core 的一等公民，
P0 的 Tool 仅用于参数 schema（``parameters`` 字段格式与 P0 Type 完全一致）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel


class ToolCall(BaseModel):
    """LLM 产出的一次工具调用请求。"""

    id: str
    name: str
    arguments: dict = {}


class ToolResult(BaseModel):
    """工具执行结果。

    content 格式与 OpenAI tool message 兼容：
    ``[{"type": "text", "text": "..."}]``。
    """

    call_id: str
    content: list[dict] = []
    details: dict = {}
    is_error: bool = False


#: ``on_update`` 回调：供长工具运行中派发增量进度。
OnToolUpdate = Callable[[dict], Awaitable[None] | None]


@dataclass
class AgentTool:
    """Agent 工具定义。

    Attributes:
        name: 唯一标识，与 LLM tool_calls.name 对齐。
        label: 可选人类可读名称（前端展示用）。
        description: 工具功能描述，会写入 LLM context。
        parameters: JSON Schema，格式与 P0 notemeld-ai ``Type.Object(...)``
            产出 dict 完全一致。
        execution_mode: "parallel" 表示此工具可与其他 parallel 工具并发执行；
            任何一方标记为 "serial" 则该轮串行。缺省 "serial"。
        execute: async (call_id: str, params: dict, signal: AbortSignal,
            on_update: OnToolUpdate) -> ToolResult | dict
            允许返回 ToolResult 或等价 dict（含 "content"/"details"/"is_error"）。
    """

    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    label: str | None = None
    execution_mode: Literal["parallel", "serial"] = "serial"
    execute: (
        Callable[[str, dict, Any, OnToolUpdate], Awaitable[ToolResult | dict]]
        | None
    ) = None

    # ------------------------------------------------------------------ #
    # 导出为 OpenAI 兼容 tool 格式，由 loop 里组装 tools list 时用
    # ------------------------------------------------------------------ #
    def to_openai_function(self) -> dict:
        properties = self.parameters.get("properties", {})
        required = self.parameters.get("required", [])
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    **({"required": required} if required else {}),
                },
            },
        }
