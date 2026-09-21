"""notemeld-ai Type schema + Tool 单测。

覆盖：
- Type.* 产出的 JSON Schema 与 OpenAI function calling 兼容
- Tool.to_openai_function() 与现有 ``chat_tools.TOOLS`` 格式逐字段一致
"""
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai.tool import Tool, Type  # noqa: E402
from app.services.chat_tools import TOOLS as CHAT_TOOLS  # noqa: E402


class TypeSchemaTest(unittest.TestCase):
    def test_string_with_description_and_enum(self):
        schema = Type.String(description="kw", enum=["a", "b"])
        self.assertEqual(schema, {
            "type": "string",
            "description": "kw",
            "enum": ["a", "b"],
        })

    def test_string_minimal(self):
        self.assertEqual(Type.String(), {"type": "string"})

    def test_number(self):
        self.assertEqual(Type.Number(description="n"), {"type": "number", "description": "n"})

    def test_integer(self):
        self.assertEqual(Type.Integer(), {"type": "integer"})

    def test_boolean(self):
        self.assertEqual(Type.Boolean(description="flag"), {"type": "boolean", "description": "flag"})

    def test_array_with_items(self):
        schema = Type.Array(items=Type.String(), description="list")
        self.assertEqual(schema, {
            "type": "array",
            "items": {"type": "string"},
            "description": "list",
        })

    def test_enum_explicit(self):
        schema = Type.Enum(values=["start", "end"], description="pos")
        self.assertEqual(schema, {
            "type": "string",
            "enum": ["start", "end"],
            "description": "pos",
        })

    def test_object_with_required(self):
        schema = Type.Object(
            properties={
                "task_id": Type.String(description="任务 ID"),
                "keyword": Type.Optional(Type.String(description="搜索关键词")),
            },
            required=["task_id"],
        )
        self.assertEqual(schema, {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "任务 ID"},
                "keyword": {"type": "string", "description": "搜索关键词"},
            },
            "required": ["task_id"],
        })

    def test_object_without_required_omits_field(self):
        schema = Type.Object(properties={"a": Type.String()})
        self.assertNotIn("required", schema)
        self.assertEqual(schema["type"], "object")

    def test_object_with_description(self):
        schema = Type.Object(properties={"a": Type.String()}, description="obj")
        self.assertEqual(schema["description"], "obj")

    def test_optional_returns_input_unchanged(self):
        """Type.Optional 是个标记函数，应原样返回输入 schema。"""
        inner = Type.String(description="x")
        self.assertIs(Type.Optional(inner), inner)


class ToolToOpenAIFunctionTest(unittest.TestCase):
    def test_to_openai_function_minimal_shape(self):
        tool = Tool(
            name="lookup_transcript",
            description="查询视频转写片段",
            parameters=Type.Object(
                properties={"task_id": Type.String()},
                required=["task_id"],
            ),
        )
        fn = tool.to_openai_function()
        self.assertEqual(fn["type"], "function")
        self.assertEqual(fn["function"]["name"], "lookup_transcript")
        self.assertEqual(fn["function"]["description"], "查询视频转写片段")
        self.assertEqual(fn["function"]["parameters"], {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        })

    def test_to_openai_function_matches_chat_tools_format(self):
        """Tool.to_openai_function() 产出与 chat_tools.TOOLS[0] 结构完全一致的 dict。

        这是迁移质量门禁：notemeld-ai 的 Tool 必须能产出与现有 chat_tools.TOOLS
        完全等价的 OpenAI function calling 格式，保证 LLM 看到的工具定义不变。
        """
        # 复刻 chat_tools.TOOLS[0] (lookup_transcript) 的 schema
        tool = Tool(
            name="lookup_transcript",
            description="查询视频原始转录文本。可按时间范围筛选、按关键词搜索、或获取指定位置的内容。",
            parameters=Type.Object(
                properties={
                    "start_time": Type.Number(description="起始时间（秒），例如 0 表示视频开头，60 表示第1分钟"),
                    "end_time": Type.Number(description="结束时间（秒），不传则到末尾"),
                    "keyword": Type.String(description="搜索关键词，返回包含该关键词的转录片段"),
                    "position": Type.Enum(
                        values=["start", "end"],
                        description="快捷位置：start=视频开头前30句，end=视频结尾后30句",
                    ),
                },
                required=[],
            ),
        )
        fn = tool.to_openai_function()

        # 顶层键一致
        self.assertEqual(set(fn.keys()), {"type", "function"})
        self.assertEqual(set(fn["function"].keys()), {"name", "description", "parameters"})

        # 与 chat_tools.TOOLS[0] 逐字段比对
        reference = CHAT_TOOLS[0]
        self.assertEqual(fn, reference)

    def test_to_openai_function_no_required_field(self):
        """chat_tools.TOOLS[1] 的 parameters 没有 required 字段（properties 为空 dict）。"""
        tool = Tool(
            name="get_video_info",
            description="获取视频的完整元信息",
            parameters=Type.Object(properties={}),
        )
        fn = tool.to_openai_function()
        self.assertNotIn("required", fn["function"]["parameters"])

    def test_default_execution_mode_is_serial(self):
        tool = Tool(name="x", description="y", parameters={})
        self.assertEqual(tool.execution_mode, "serial")

    def test_tool_can_carry_execute_callable(self):
        async def fake_execute(*args, **kwargs):
            return {"ok": True}

        tool = Tool(name="x", description="y", parameters={}, execute=fake_execute)
        self.assertIs(tool.execute, fake_execute)


if __name__ == "__main__":
    unittest.main()
