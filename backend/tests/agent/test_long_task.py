"""P3-T4: long_task 单测 — 注册表 + 长任务卡片 + 状态推进 + 取消 + follow-up。

覆盖：
- register_card / find_manager_by_card / unregister_card / clear_registry
- LongTaskManager.start_task：卡片创建、PENDING 持久化、SSE task_card 事件
- 后台执行：真实子进程 success / progress 行解析 / failed
- cancel_task：CANCELED 状态 + 已结束卡片返回 False
- auto_follow_up 开关：关闭不调 follow_up，开启在 SUCCESS 后调用
- dispatcher=None 不崩溃
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.long_task import (
    LongTaskManager,
    clear_registry,
    find_manager_by_card,
    register_card,
    unregister_card,
)
from app.agent.skill_loader import SkillDefinition


def _make_skill(
    name: str = "compile_source",
    long_running: bool = True,
    script_command: str = "",
    timeout_seconds: int = 0,
) -> SkillDefinition:
    return SkillDefinition(
        name=name,
        description="test skill",
        long_running=long_running,
        script_command=script_command or f'{sys.executable} -c "print(\'ok\')"',
        timeout_seconds=timeout_seconds,
    )


class FakeAgent:
    """记录 follow_up 调用的假 Agent。"""

    def __init__(self) -> None:
        self.follow_up_calls: list[str] = []

    async def follow_up(self, prompt: str) -> None:
        self.follow_up_calls.append(prompt)


class LongTaskRegistryTest(unittest.TestCase):
    """模块级注册表：card_id → LongTaskManager。"""

    def setUp(self) -> None:
        clear_registry()

    def tearDown(self) -> None:
        clear_registry()

    def test_register_and_find_card(self):
        mgr = LongTaskManager()
        register_card("card-1", mgr)
        self.assertIs(find_manager_by_card("card-1"), mgr)

    def test_find_unknown_returns_none(self):
        self.assertIsNone(find_manager_by_card("nope"))

    def test_unregister_card(self):
        mgr = LongTaskManager()
        register_card("card-2", mgr)
        unregister_card("card-2")
        self.assertIsNone(find_manager_by_card("card-2"))
        # 幂等：重复注销不报错
        unregister_card("card-2")

    def test_clear_registry(self):
        register_card("a", LongTaskManager())
        register_card("b", LongTaskManager())
        clear_registry()
        self.assertIsNone(find_manager_by_card("a"))
        self.assertIsNone(find_manager_by_card("b"))


class LongTaskManagerTest(unittest.TestCase):
    """LongTaskManager：卡片创建、状态推进、取消、follow-up。"""

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["NOTE_OUTPUT_DIR"] = str(self._tmp.name)
        clear_registry()
        # patch DB / note_task_store 调用（long_task 命名空间内导入的引用）
        self._patches: list = []
        self.append_mock = self._start_patch("app.agent.long_task.append_message")
        self.update_mock = self._start_patch("app.agent.long_task.update_message")
        self.cancel_task_store_mock = self._start_patch("app.agent.long_task.cancel_note_task")
        self.is_canceled_mock = self._start_patch(
            "app.agent.long_task.is_note_task_canceled", return_value=False
        )

    def _start_patch(self, target, **kw):
        p = patch(target, **kw)
        m = p.start()
        self._patches.append(p)
        return m

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        clear_registry()
        os.environ.pop("NOTE_OUTPUT_DIR", None)
        self._tmp.cleanup()

    def _new_manager(self, *, dispatcher=None, auto_follow_up=False, agent=None):
        return LongTaskManager(
            agent=agent,
            auto_follow_up=auto_follow_up,
            dispatcher=dispatcher,
            default_timeout=0,
        )

    # ------------------------------------------------------------------ #
    # start_task
    # ------------------------------------------------------------------ #
    def test_start_task_returns_pending_card(self):
        events: list[dict] = []
        mgr = self._new_manager(dispatcher=lambda e: events.append(e))
        skill = _make_skill()

        card = self._run(mgr.start_task(skill=skill, params={}, conversation_id="cid-1", call_id="c1"))

        self.assertTrue(card["card_id"].startswith("card-"))
        self.assertTrue(card["task_id"].startswith("lt-"))
        self.assertEqual(card["status"], "PENDING")
        self.assertEqual(card["kind"], "compile_source")
        self.assertIn("compile_source", card["title"])
        self.assertEqual(card["conversation_id"], "cid-1")
        self.assertEqual(card["call_id"], "c1")

        # 注册表已登记
        self.assertIs(find_manager_by_card(card["card_id"]), mgr)

        # SSE task_card PENDING 已派发
        pending_evt = [e for e in events if e.get("type") == "task_card"]
        self.assertGreaterEqual(len(pending_evt), 1)
        self.assertEqual(pending_evt[0]["status"], "PENDING")

        # 清理后台任务
        self._run(mgr.wait_for_all(timeout=10.0))

    def test_start_task_persists_pending_message(self):
        mgr = self._new_manager()
        skill = _make_skill()
        self._run(mgr.start_task(skill=skill, params={}, conversation_id="cid-2"))

        # append_message 被调用（PENDING 卡片消息）
        self.assertTrue(self.append_mock.called)
        call_args = self.append_mock.call_args
        self.assertEqual(call_args.args[0], "cid-2")
        data = call_args.args[1]
        self.assertEqual(data["role"], "assistant")
        self.assertEqual(data["message_type"], "task_card")
        self.assertEqual(data["status"], "PENDING")

        self._run(mgr.wait_for_all(timeout=10.0))

    def test_start_task_empty_conversation_raises(self):
        mgr = self._new_manager()
        skill = _make_skill()
        with self.assertRaises(ValueError):
            self._run(mgr.start_task(skill=skill, params={}, conversation_id=""))

    def test_dispatcher_none_no_crash(self):
        mgr = self._new_manager(dispatcher=None)
        skill = _make_skill()
        card = self._run(mgr.start_task(skill=skill, params={}, conversation_id="cid-3"))
        self.assertEqual(card["status"], "PENDING")
        self._run(mgr.wait_for_all(timeout=10.0))

    # ------------------------------------------------------------------ #
    # 后台执行：success / progress / failed
    # ------------------------------------------------------------------ #
    def test_long_task_runs_to_success(self):
        events: list[dict] = []
        mgr = self._new_manager(dispatcher=lambda e: events.append(e))
        skill = _make_skill(script_command=f"{sys.executable} -c \"print('done')\"")

        async def go():
            card = await mgr.start_task(skill=skill, params={}, conversation_id="cid-ok")
            await mgr.wait_for_all(timeout=10.0)
            return card

        card = self._run(go())
        final = mgr.get_card(card["card_id"])
        self.assertEqual(final["status"], "SUCCESS")
        self.assertEqual(final["progress"], 100)

        # 至少有一枚 SUCCESS 的 task_card 事件
        success_evts = [e for e in events if e.get("type") == "task_card" and e.get("status") == "SUCCESS"]
        self.assertGreaterEqual(len(success_evts), 1)

    def test_long_task_progress_line_parsed(self):
        events: list[dict] = []
        mgr = self._new_manager(dispatcher=lambda e: events.append(e))
        script = (
            f"{sys.executable} -c "
            f"\"print('PROGRESS:50:RUNNING:half done'); print('PROGRESS:100:SUCCESS:completed')\""
        )
        skill = _make_skill(script_command=script)

        async def go():
            card = await mgr.start_task(skill=skill, params={}, conversation_id="cid-prog")
            await mgr.wait_for_all(timeout=10.0)
            return card

        card = self._run(go())
        final = mgr.get_card(card["card_id"])
        self.assertEqual(final["status"], "SUCCESS")
        self.assertEqual(final["progress"], 100)
        self.assertEqual(final["details"], "完成")

        # 进度事件序列包含 50 与 100
        progress_evts = [e for e in events if e.get("type") == "task_card_progress"]
        progresses = [e["progress"] for e in progress_evts]
        self.assertIn(50, progresses)
        self.assertIn(100, progresses)

    def test_long_task_failed_script(self):
        mgr = self._new_manager()
        skill = _make_skill(script_command=f"{sys.executable} -c \"import sys; sys.exit(3)\"")

        async def go():
            card = await mgr.start_task(skill=skill, params={}, conversation_id="cid-fail")
            await mgr.wait_for_all(timeout=10.0)
            return card

        card = self._run(go())
        final = mgr.get_card(card["card_id"])
        self.assertEqual(final["status"], "FAILED")
        self.assertIn("3", final["details"])

    # ------------------------------------------------------------------ #
    # cancel_task
    # ------------------------------------------------------------------ #
    def test_cancel_task_sets_canceled(self):
        mgr = self._new_manager()
        skill = _make_skill(script_command=f"{sys.executable} -c \"import time; time.sleep(30)\"")

        async def go():
            card = await mgr.start_task(skill=skill, params={}, conversation_id="cid-cancel")
            ok = await mgr.cancel_task(card["card_id"], reason="用户取消")
            await mgr.wait_for_all(timeout=10.0)
            return card, ok

        card, ok = self._run(go())
        self.assertTrue(ok)
        final = mgr.get_card(card["card_id"])
        self.assertEqual(final["status"], "CANCELED")
        self.assertEqual(final["details"], "用户取消")
        # cancel_note_task 被调用
        self.assertTrue(self.cancel_task_store_mock.called)

    def test_cancel_unknown_card_returns_false(self):
        mgr = self._new_manager()
        ok = self._run(mgr.cancel_task("card-does-not-exist"))
        self.assertFalse(ok)

    def test_cancel_finished_card_returns_false(self):
        mgr = self._new_manager()
        skill = _make_skill(script_command=f"{sys.executable} -c \"print('done')\"")

        async def go():
            card = await mgr.start_task(skill=skill, params={}, conversation_id="cid-fin")
            await mgr.wait_for_all(timeout=10.0)
            return card

        card = self._run(go())
        self.assertEqual(mgr.get_card(card["card_id"])["status"], "SUCCESS")
        # 已结束 → cancel 返回 False
        ok = self._run(mgr.cancel_task(card["card_id"]))
        self.assertFalse(ok)

    # ------------------------------------------------------------------ #
    # auto_follow_up 开关
    # ------------------------------------------------------------------ #
    def test_auto_follow_up_off_no_call(self):
        agent = FakeAgent()
        mgr = self._new_manager(agent=agent, auto_follow_up=False)
        skill = _make_skill(script_command=f"{sys.executable} -c \"print('done')\"")

        async def go():
            card = await mgr.start_task(skill=skill, params={}, conversation_id="cid-fu-off")
            await mgr.wait_for_all(timeout=10.0)
            await asyncio.sleep(0.3)
            return card

        self._run(go())
        self.assertEqual(agent.follow_up_calls, [])

    def test_auto_follow_up_on_calls_follow_up_on_success(self):
        agent = FakeAgent()
        mgr = self._new_manager(agent=agent, auto_follow_up=True)
        skill = _make_skill(script_command=f"{sys.executable} -c \"print('done')\"")

        async def go():
            card = await mgr.start_task(skill=skill, params={}, conversation_id="cid-fu-on")
            await mgr.wait_for_all(timeout=10.0)
            await asyncio.sleep(0.3)
            return card

        self._run(go())
        self.assertEqual(len(agent.follow_up_calls), 1)
        self.assertIn("compile_source", agent.follow_up_calls[0])
        self.assertIn("成功完成", agent.follow_up_calls[0])

    # ------------------------------------------------------------------ #
    # get_card / list_active_cards
    # ------------------------------------------------------------------ #
    def test_get_card_and_list_active(self):
        mgr = self._new_manager()
        skill_sleep = _make_skill(script_command=f"{sys.executable} -c \"import time; time.sleep(30)\"")

        async def go():
            card = await mgr.start_task(skill=skill_sleep, params={}, conversation_id="cid-list")
            # PENDING/RUNNING 阶段应出现在 list_active_cards
            active = mgr.list_active_cards()
            self.assertTrue(any(c["card_id"] == card["card_id"] for c in active))
            ok = await mgr.cancel_task(card["card_id"])
            await mgr.wait_for_all(timeout=10.0)
            return card, ok

        card, ok = self._run(go())
        self.assertTrue(ok)
        # CANCELED 后不再 active
        active = mgr.list_active_cards()
        self.assertFalse(any(c["card_id"] == card["card_id"] for c in active))
        # get_card 仍可读
        self.assertEqual(mgr.get_card(card["card_id"])["status"], "CANCELED")
        self.assertIsNone(mgr.get_card("unknown"))


if __name__ == "__main__":
    unittest.main()
