"""P3-T2: memory 单测 — 三层记忆容错 + 注入 hook + AgentTool。

验收映射：
- §2 记忆注入（build_system_prefix → MemoryContextHook.transform_context）
- JSON 损坏容错（备份 + 默认值）
- masteries Top-N 截断
- create_memory_tools 两个工具
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

from app.agent.core.message import AgentMessage
from app.agent.core.signal import AbortSignal
from app.agent.memory import (
    MASTERIES_TOP_N,
    MemoryContextHook,
    MemoryManager,
    build_memory_hook,
    create_memory_tools,
    memory_root,
    research_space_path,
    user_profile_path,
)


class _BaseWithTmpDir(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["NOTE_OUTPUT_DIR"] = str(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        os.environ.pop("NOTE_OUTPUT_DIR", None)

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)


class MemoryPathTest(_BaseWithTmpDir):
    def test_memory_root_under_note_output(self) -> None:
        self.assertEqual(memory_root().name, "memory")
        # memory_root 用 .resolve()，比较时也用 resolve（macOS /var → /private/var 符号链接）
        expected_root = str(pathlib.Path(self._tmp.name).resolve())
        self.assertTrue(str(memory_root()).startswith(expected_root + os.sep))

    def test_research_space_path_rejects_unsafe_id(self) -> None:
        for bad in ("../escape", "a/b", "a b", "rs.x", ""):
            with self.assertRaises(ValueError, msg=f"rs_id={bad!r} 应被拒"):
                research_space_path(bad)

    def test_research_space_path_valid(self) -> None:
        p = research_space_path("rs_001")
        self.assertEqual(p.name, "rs_001.json")


class ReadJsonSafeTest(_BaseWithTmpDir):
    def test_corrupted_file_backed_up_and_default_returned(self) -> None:
        # 写一个损坏的 user_profile.json
        path = user_profile_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ 不是合法 json }}}", encoding="utf-8")

        mgr = MemoryManager()
        profile = mgr.load_user_profile()
        # 返回默认结构
        self.assertEqual(profile["display_name"], "")
        self.assertEqual(profile["interests"], [])
        # 损坏文件被备份（生成 .corrupted-*.json）
        backups = list(path.parent.glob("user_profile.corrupted-*.json"))
        self.assertEqual(len(backups), 1, "损坏文件应被备份")

    def test_missing_file_returns_default(self) -> None:
        mgr = MemoryManager()
        profile = mgr.load_user_profile()
        self.assertEqual(profile["version"], 1)
        self.assertEqual(profile["masteries"], [])


class UserProfileRoundTripTest(_BaseWithTmpDir):
    def test_save_then_load_preserves_fields(self) -> None:
        mgr = MemoryManager()
        mgr.save_user_profile({
            "display_name": "小明",
            "interests": [{"topic": "AI", "weight": 0.9}],
            "domains": [{"name": "后端", "level": "高级"}],
            "preferences": {"lang": "zh"},
        })
        loaded = mgr.load_user_profile()
        self.assertEqual(loaded["display_name"], "小明")
        self.assertEqual(loaded["interests"][0]["topic"], "AI")
        self.assertEqual(loaded["preferences"]["lang"], "zh")
        self.assertTrue(loaded["updated_at"])  # 自动填 updated_at

    def test_save_merges_with_existing(self) -> None:
        mgr = MemoryManager()
        mgr.save_user_profile({"display_name": "A", "preferences": {"a": 1}})
        mgr.save_user_profile({"display_name": "B"})  # 只改名字
        loaded = mgr.load_user_profile()
        self.assertEqual(loaded["display_name"], "B")
        self.assertEqual(loaded["preferences"]["a"], 1)  # 旧偏好保留


class MasteriesTruncationTest(_BaseWithTmpDir):
    def test_masteries_truncated_to_top_n(self) -> None:
        mgr = MemoryManager()
        # 构造 30 条 mastery，score 0-29
        mgr.save_user_profile({
            "masteries": [
                {"subject": f"s{i}", "score": float(i)} for i in range(30)
            ]
        })
        loaded = mgr.load_user_profile()
        self.assertEqual(len(loaded["masteries"]), MASTERIES_TOP_N)
        # 截断后应保留 score 最高的 Top-N（按降序）
        scores = [m["score"] for m in loaded["masteries"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(max(scores), 29.0)


class ResearchSpaceTest(_BaseWithTmpDir):
    def test_upsert_then_load(self) -> None:
        mgr = MemoryManager()
        mgr.save_research_space("rs1", {"title": "调研A", "goal": "完成P3"})
        loaded = mgr.load_research_space("rs1")
        self.assertEqual(loaded["title"], "调研A")
        self.assertEqual(loaded["goal"], "完成P3")
        self.assertEqual(loaded["rs_id"], "rs1")
        self.assertTrue(loaded["created_at"])

    def test_load_nonexistent_returns_default(self) -> None:
        mgr = MemoryManager()
        loaded = mgr.load_research_space("new_rs")
        self.assertEqual(loaded["key_facts"], [])
        self.assertEqual(loaded["rs_id"], "new_rs")


class BuildSystemPrefixTest(_BaseWithTmpDir):
    def test_empty_profile_returns_empty_prefix(self) -> None:
        mgr = MemoryManager()
        self.assertEqual(mgr.build_system_prefix(), "")

    def test_profile_with_data_returns_prefix(self) -> None:
        mgr = MemoryManager()
        mgr.save_user_profile({"display_name": "小明", "interests": [{"topic": "AI", "weight": 0.9}]})
        prefix = mgr.build_system_prefix()
        self.assertIn("长期记忆", prefix)
        self.assertIn("小明", prefix)
        self.assertIn("AI", prefix)

    def test_prefix_includes_research_space(self) -> None:
        mgr = MemoryManager()
        mgr.save_research_space("rs1", {"title": "调研X", "goal": "目标Y", "key_facts": [{"text": "事实Z"}]})
        prefix = mgr.build_system_prefix("rs1")
        self.assertIn("调研X", prefix)
        self.assertIn("目标Y", prefix)
        self.assertIn("事实Z", prefix)

    def test_invalid_rs_id_returns_prefix_without_rs(self) -> None:
        # research_space_path 会抛 ValueError → build_system_prefix 内部 catch → 仅返回 profile 部分
        mgr = MemoryManager()
        mgr.save_user_profile({"display_name": "用户"})
        prefix = mgr.build_system_prefix("bad/id")
        self.assertIn("用户", prefix)


class MemoryContextHookTest(_BaseWithTmpDir):
    def test_hook_prepends_prefix_to_system_message(self) -> None:
        mgr = MemoryManager()
        mgr.save_user_profile({"display_name": "小明"})
        hook = build_memory_hook()
        self.assertTrue(hook.prefix)

        messages = [AgentMessage(role="system", content="你是助手")]
        out = hook.transform_context(messages, AbortSignal())
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].content.startswith(hook.prefix))
        self.assertIn("你是助手", out[0].content)

    def test_hook_inserts_system_when_absent(self) -> None:
        mgr = MemoryManager()
        mgr.save_user_profile({"display_name": "小明"})
        hook = build_memory_hook()

        messages = [AgentMessage(role="user", content="你好")]
        out = hook.transform_context(messages, AbortSignal())
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].role, "system")
        self.assertEqual(out[1].role, "user")

    def test_hook_empty_prefix_passes_through(self) -> None:
        hook = build_memory_hook()  # 无 profile → prefix 空
        self.assertEqual(hook.prefix, "")
        messages = [AgentMessage(role="user", content="hi")]
        out = hook.transform_context(messages, AbortSignal())
        self.assertEqual(out, messages)


class MemoryToolsTest(_BaseWithTmpDir):
    def test_create_memory_tools_returns_two_named_tools(self) -> None:
        tools = create_memory_tools()
        names = [t.name for t in tools]
        self.assertEqual(names, ["update_user_profile", "manage_research_space"])

    def test_update_user_profile_tool_execute(self) -> None:
        tools = create_memory_tools()
        tool = next(t for t in tools if t.name == "update_user_profile")
        res = self._run(tool.execute(
            "call1",
            {"display_name": "测试用户", "interests": [{"topic": "阅读", "weight": 0.8}]},
            AbortSignal(),
            None,
        ))
        self.assertFalse(res.is_error)
        payload = json.loads(res.content[0]["text"])
        self.assertEqual(payload["display_name"], "测试用户")
        # 落盘可读回
        self.assertEqual(MemoryManager().load_user_profile()["display_name"], "测试用户")

    def test_manage_research_space_upsert_then_add_fact(self) -> None:
        tools = create_memory_tools()
        tool = next(t for t in tools if t.name == "manage_research_space")

        # upsert
        r1 = self._run(tool.execute("c1", {"rs_id": "rs1", "action": "upsert", "title": "T", "goal": "G"}, AbortSignal(), None))
        self.assertFalse(r1.is_error)

        # add_fact
        r2 = self._run(tool.execute("c2", {"rs_id": "rs1", "action": "add_fact", "fact": {"text": "事实1"}}, AbortSignal(), None))
        self.assertFalse(r2.is_error)
        payload = json.loads(r2.content[0]["text"])
        self.assertEqual(len(payload["key_facts"]), 1)
        self.assertEqual(payload["key_facts"][0]["text"], "事实1")

    def test_manage_research_space_missing_required_returns_error(self) -> None:
        tools = create_memory_tools()
        tool = next(t for t in tools if t.name == "manage_research_space")
        # 缺 action
        res = self._run(tool.execute("c3", {"rs_id": "rs1"}, AbortSignal(), None))
        self.assertTrue(res.is_error)
        # 非法 rs_id
        res2 = self._run(tool.execute("c4", {"rs_id": "bad/id", "action": "upsert"}, AbortSignal(), None))
        self.assertTrue(res2.is_error)

    def test_manage_research_space_delete(self) -> None:
        tools = create_memory_tools()
        tool = next(t for t in tools if t.name == "manage_research_space")
        # 先创建
        self._run(tool.execute("c5", {"rs_id": "rs2", "action": "upsert", "title": "X"}, AbortSignal(), None))
        self.assertTrue(research_space_path("rs2").exists())
        # 删除
        res = self._run(tool.execute("c6", {"rs_id": "rs2", "action": "delete"}, AbortSignal(), None))
        self.assertFalse(res.is_error)
        self.assertFalse(research_space_path("rs2").exists())


if __name__ == "__main__":
    unittest.main()
