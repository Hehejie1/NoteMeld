"""P3-T3: skill_loader 单测 — SKILL.md 解析 + load_skills + build_skill_tool + 参数替换。

覆盖：
- parse_skill_content：合法 frontmatter / 缺 frontmatter / 非法 name / 缺脚本调用 / 脚本前缀变体
- parse_skill_file：读真实文件 / 不存在 / 非文件
- load_skills：多 skill 加载 / 空目录 / 不存在目录 / 重复 name / 非法 skill 跳过
- default_skills_dir：路径 = note_output_dir()/skills
- _substitute_command：$key / ${key} / 缺失占位符 / 含空格值
- build_skill_tool：构造 AgentTool / execute 非长任务成功 / 缺必填参数 / 长任务无 manager
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import tempfile
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.core.signal import AbortSignal
from app.agent.core.tool import AgentTool, ToolResult
from app.agent.skill_loader import (
    SkillDefinition,
    SkillLoaderError,
    build_skill_tool,
    default_skills_dir,
    load_skills,
    parse_skill_content,
    parse_skill_file,
    _substitute_command,
)
from app.utils.storage_paths import note_output_dir


# ---------------------------------------------------------------------------
# 共享 SKILL.md 样本
# ---------------------------------------------------------------------------

_VALID_SKILL_MD = """\
---
name: compile_source
description: 编译视频为笔记
parameters:
  - key: url
    label: 视频链接
    widget: text_input
    required: true
  - key: style
    label: 笔记风格
    widget: select
    options: [简洁, 详细]
    required: false
    default: 简洁
long_running: true
timeout_seconds: 600
---
脚本调用：python scripts/compile_source.py --url "$url" --style "$style"
"""

_VALID_SHORT_SKILL_MD = """\
---
name: echo_skill
description: echo something
---
script: echo hello
"""


class _BaseTmpDirTest(unittest.TestCase):
    """NOTE_OUTPUT_DIR → tmp 目录，避免污染真实数据。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["NOTE_OUTPUT_DIR"] = str(self._tmp.name)

    def tearDown(self) -> None:
        os.environ.pop("NOTE_OUTPUT_DIR", None)
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# parse_skill_content
# ---------------------------------------------------------------------------


class ParseSkillContentTest(_BaseTmpDirTest):
    def test_valid_frontmatter_with_params(self):
        skill = parse_skill_content(_VALID_SKILL_MD)
        self.assertEqual(skill.name, "compile_source")
        self.assertEqual(skill.description, "编译视频为笔记")
        self.assertTrue(skill.long_running)
        self.assertEqual(skill.timeout_seconds, 600)
        self.assertEqual(len(skill.parameters), 2)
        self.assertEqual(skill.parameters[0]["key"], "url")
        self.assertTrue(skill.parameters[0]["required"])
        self.assertEqual(skill.parameters[1]["widget"], "select")
        self.assertEqual(skill.parameters[1]["default"], "简洁")
        self.assertEqual(skill.parameters[1]["options"], ["简洁", "详细"])
        self.assertIn("compile_source.py", skill.script_command)

    def test_missing_frontmatter_raises(self):
        with self.assertRaises(SkillLoaderError):
            parse_skill_content("name: foo\nscript: echo hi\n")

    def test_invalid_name_raises(self):
        bad = _VALID_SKILL_MD.replace("name: compile_source", "name: bad name!")
        with self.assertRaises(SkillLoaderError):
            parse_skill_content(bad)

    def test_empty_name_raises(self):
        bad = _VALID_SKILL_MD.replace("name: compile_source", "name: ")
        with self.assertRaises(SkillLoaderError):
            parse_skill_content(bad)

    def test_missing_script_command_raises(self):
        no_script = """\
---
name: no_script
description: nothing
---
只有说明文字，没有脚本调用。
"""
        with self.assertRaises(SkillLoaderError):
            parse_skill_content(no_script)

    def test_script_prefix_variants(self):
        # 脚本调用：
        s1 = parse_skill_content(_VALID_SHORT_SKILL_MD)
        self.assertEqual(s1.script_command, "echo hello")

        # script: 前缀
        s2 = parse_skill_content(
            "---\nname: a\n---\nscript: python foo.py\n"
        )
        self.assertEqual(s2.script_command, "python foo.py")

        # 无前缀，python 开头
        s3 = parse_skill_content(
            "---\nname: b\n---\npython3 bar.py --x 1\n"
        )
        self.assertEqual(s3.script_command, "python3 bar.py --x 1")

        # 无前缀，bash 开头
        s4 = parse_skill_content(
            "---\nname: c\n---\nbash run.sh\n"
        )
        self.assertEqual(s4.script_command, "bash run.sh")

    def test_long_running_default_timeout(self):
        # long_running=True 且无 timeout_seconds → 默认 0（不限）
        md = "---\nname: long_one\ndescription: d\nlong_running: true\n---\nscript: echo hi\n"
        skill = parse_skill_content(md)
        self.assertTrue(skill.long_running)
        self.assertEqual(skill.timeout_seconds, 0)

    def test_non_long_running_default_timeout(self):
        md = "---\nname: short_one\ndescription: d\n---\nscript: echo hi\n"
        skill = parse_skill_content(md)
        self.assertFalse(skill.long_running)
        self.assertEqual(skill.timeout_seconds, 120)

    def test_working_dir_from_skill_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "SKILL.md"
            p.write_text(_VALID_SKILL_MD, encoding="utf-8")
            skill = parse_skill_file(p)
            self.assertEqual(skill.working_dir, p.parent)
            self.assertEqual(skill.skill_file, p)


# ---------------------------------------------------------------------------
# SkillDefinition.to_json_schema / required_keys
# ---------------------------------------------------------------------------


class SkillDefinitionSchemaTest(_BaseTmpDirTest):
    def test_to_json_schema(self):
        skill = parse_skill_content(_VALID_SKILL_MD)
        schema = skill.to_json_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("url", schema["properties"])
        self.assertIn("style", schema["properties"])
        self.assertEqual(schema["properties"]["url"]["type"], "string")
        self.assertEqual(schema["properties"]["style"]["type"], "string")
        self.assertEqual(schema["properties"]["style"]["enum"], ["简洁", "详细"])
        self.assertEqual(schema["required"], ["url"])

    def test_required_keys(self):
        skill = parse_skill_content(_VALID_SKILL_MD)
        self.assertEqual(skill.required_keys(), ["url"])


# ---------------------------------------------------------------------------
# parse_skill_file
# ---------------------------------------------------------------------------


class ParseSkillFileTest(_BaseTmpDirTest):
    def test_read_real_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "SKILL.md"
            p.write_text(_VALID_SKILL_MD, encoding="utf-8")
            skill = parse_skill_file(p)
            self.assertEqual(skill.name, "compile_source")

    def test_nonexistent_file_raises(self):
        with self.assertRaises(SkillLoaderError):
            parse_skill_file("/no/such/SKILL.md")

    def test_directory_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SkillLoaderError):
                parse_skill_file(d)


# ---------------------------------------------------------------------------
# load_skills / default_skills_dir
# ---------------------------------------------------------------------------


class LoadSkillsTest(_BaseTmpDirTest):
    def test_default_skills_dir_under_note_output(self):
        self.assertEqual(default_skills_dir(), (note_output_dir() / "skills").resolve())

    def test_load_multiple_skills(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "a" / "SKILL.md").parent.mkdir(parents=True)
            (root / "a" / "SKILL.md").write_text(
                "---\nname: alpha\ndescription: a\n---\nscript: echo a\n", encoding="utf-8"
            )
            (root / "b" / "SKILL.md").parent.mkdir(parents=True)
            (root / "b" / "SKILL.md").write_text(
                "---\nname: beta\ndescription: b\n---\nscript: echo b\n", encoding="utf-8"
            )
            tools = load_skills(root)
            names = [t.name for t in tools]
            self.assertEqual(sorted(names), ["alpha", "beta"])
            for t in tools:
                self.assertIsInstance(t, AgentTool)

    def test_empty_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_skills(d), [])

    def test_nonexistent_dir_returns_empty(self):
        self.assertEqual(load_skills("/no/such/dir"), [])

    def test_duplicate_name_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "a").mkdir()
            (root / "b").mkdir()
            content = "---\nname: dup\ndescription: d\n---\nscript: echo x\n"
            (root / "a" / "SKILL.md").write_text(content, encoding="utf-8")
            (root / "b" / "SKILL.md").write_text(content, encoding="utf-8")
            tools = load_skills(root)
            # 重复 name 只保留一个
            self.assertEqual(len(tools), 1)
            self.assertEqual(tools[0].name, "dup")

    def test_invalid_skill_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "bad").mkdir()
            # 缺脚本调用 → SkillLoaderError → 跳过
            (root / "bad" / "SKILL.md").write_text(
                "---\nname: bad_skill\ndescription: d\n---\n无脚本\n", encoding="utf-8"
            )
            (root / "good").mkdir()
            (root / "good" / "SKILL.md").write_text(
                "---\nname: good_skill\ndescription: d\n---\nscript: echo ok\n", encoding="utf-8"
            )
            tools = load_skills(root)
            self.assertEqual([t.name for t in tools], ["good_skill"])


# ---------------------------------------------------------------------------
# _substitute_command
# ---------------------------------------------------------------------------


class SubstituteCommandTest(unittest.TestCase):
    def test_substitute_simple(self):
        argv = _substitute_command("python foo.py --url $url", {"url": "abc"})
        self.assertEqual(argv, ["python", "foo.py", "--url", "abc"])

    def test_substitute_braces(self):
        argv = _substitute_command("python foo.py --name ${name}", {"name": "x"})
        self.assertEqual(argv, ["python", "foo.py", "--name", "x"])

    def test_substitute_missing_key_empty(self):
        argv = _substitute_command("python foo.py --url $url", {})
        self.assertEqual(argv[0], "python")
        self.assertEqual(argv[2], "--url")
        # 缺失占位符 → 空字符串 token
        self.assertEqual(argv[3], "")

    def test_substitute_value_with_spaces(self):
        argv = _substitute_command("python foo.py --t $t", {"t": "hello world"})
        # 含空格的值保持为单个 token
        self.assertEqual(argv, ["python", "foo.py", "--t", "hello world"])

    def test_substitute_none_value(self):
        argv = _substitute_command("python foo.py --t $t", {"t": None})
        self.assertEqual(argv[-1], "")


# ---------------------------------------------------------------------------
# build_skill_tool
# ---------------------------------------------------------------------------


class BuildSkillToolTest(_BaseTmpDirTest):
    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def test_build_tool_basic_properties(self):
        skill = parse_skill_content(_VALID_SKILL_MD)
        tool = build_skill_tool(skill)
        self.assertEqual(tool.name, "compile_source")
        self.assertEqual(tool.description, "编译视频为笔记")
        self.assertEqual(tool.execution_mode, "serial")
        self.assertIn("url", tool.parameters["properties"])

    def test_execute_non_long_running_success(self):
        skill = SkillDefinition(
            name="quick",
            description="d",
            long_running=False,
            script_command="echo hello",
            timeout_seconds=10,
        )
        tool = build_skill_tool(skill)

        async def go():
            sig = AbortSignal()
            result = await tool.execute("call-1", {}, sig, None)
            return result

        result = self._run(go())
        self.assertIsInstance(result, ToolResult)
        self.assertFalse(result.is_error)
        text = json.loads(result.content[0]["text"])
        self.assertEqual(text["returncode"], 0)
        self.assertIn("hello", text["stdout"])

    def test_execute_missing_required_no_collector(self):
        skill = parse_skill_content(_VALID_SKILL_MD)  # url required
        tool = build_skill_tool(skill, parameter_collector=None)

        async def go():
            sig = AbortSignal()
            result = await tool.execute("call-2", {}, sig, None)
            return result

        result = self._run(go())
        self.assertTrue(result.is_error)
        payload = json.loads(result.content[0]["text"])
        self.assertIn("url", payload["error"])

    def test_execute_long_running_no_manager(self):
        skill = SkillDefinition(
            name="lr",
            description="d",
            long_running=True,
            script_command="echo hi",
        )
        tool = build_skill_tool(skill, long_task_manager=None)

        async def go():
            sig = AbortSignal()
            # 提供必填参数避免走到长任务分支前的参数错误
            result = await tool.execute("call-3", {}, sig, None)
            return result

        result = self._run(go())
        self.assertTrue(result.is_error)
        payload = json.loads(result.content[0]["text"])
        self.assertIn("LongTaskManager", payload["error"])

    def test_execute_long_running_with_manager(self):
        skill = SkillDefinition(
            name="lr2",
            description="d",
            long_running=True,
            script_command="echo hi",
        )

        class FakeMgr:
            _conversation_id = "conv-x"

            async def start_task(self, *, skill, params, conversation_id, call_id=None):
                return {"card_id": "card-z", "task_id": "lt-z", "status": "PENDING"}

        tool = build_skill_tool(skill, long_task_manager=FakeMgr())

        async def go():
            sig = AbortSignal()
            result = await tool.execute("call-4", {}, sig, None)
            return result

        result = self._run(go())
        self.assertFalse(result.is_error)
        card = json.loads(result.content[0]["text"])
        self.assertEqual(card["card_id"], "card-z")
        self.assertEqual(card["status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
