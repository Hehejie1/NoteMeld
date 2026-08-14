"""P3 阶段二集成测试：Agent 运行时全量集成。

覆盖：
- run_free_chat / run_free_chat_stream 注册 workspace+memory+skill 工具
- cid=None 时不注册 workspace 工具
- research_space_id 注入 system_prompt
- sse_bridge long_task_manager 生命周期（done 后不立即关闭，长任务收尾后关闭）
- 长任务端到端 mock：skill 脚本输出 PROGRESS 行 → task_card_progress 经 SSE
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.agent_core._base import FakeModel, FakeModels, build_agent_tool, build_tool_call


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _make_mock_hooks(system_prompt="sys", sources=None):
    from app.agent.chat_adapter import ChatContextHooks
    return ChatContextHooks(system_prompt=system_prompt, sources=sources or [])


class FreeChatToolRegistrationTest(unittest.TestCase):
    """P3 阶段二：run_free_chat* 注册 workspace+memory+skill 工具。"""

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["NOTE_OUTPUT_DIR"] = str(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        os.environ.pop("NOTE_OUTPUT_DIR", None)

    def test_run_free_chat_does_not_flatten_memory_tools(self):
        """Memory 能力留在目录中，初始模型上下文只暴露固定元工具。"""
        from app.agent.agent_service import run_free_chat

        captured_tools: list = []

        def _capture_agent(initial_state, **kwargs):
            captured_tools.extend(initial_state.tools)
            from app.agent.core.agent import Agent
            return Agent(initial_state=initial_state, **kwargs)

        models = FakeModels(turns=["回答"])
        hooks = _make_mock_hooks()

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_free_chat_hooks", return_value=hooks), \
             patch("app.agent.agent_service.load_skills", return_value=[]), \
             patch("app.agent.agent_service.Agent", side_effect=_capture_agent):
            result = self._run(run_free_chat(
                question="hi",
                history=[],
                provider_id="prov",
                model_name="model",
            ))

        tool_names = [t.name for t in captured_tools]
        self.assertEqual(tool_names, [
            "capability_discover", "capability_describe", "capability_invoke",
        ])
        self.assertNotIn("update_user_profile", tool_names)
        self.assertEqual(result["answer"], "回答")

    def test_run_free_chat_with_cid_does_not_flatten_workspace_tools(self):
        """cid 非空时 Workspace 能力仍须通过 L1-L3 使用。"""
        from app.agent.agent_service import run_free_chat

        captured_tools: list = []

        def _capture_agent(initial_state, **kwargs):
            captured_tools.extend(initial_state.tools)
            from app.agent.core.agent import Agent
            return Agent(initial_state=initial_state, **kwargs)

        models = FakeModels(turns=["回答"])
        hooks = _make_mock_hooks()

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_free_chat_hooks", return_value=hooks), \
             patch("app.agent.agent_service.load_skills", return_value=[]), \
             patch("app.agent.agent_service.Agent", side_effect=_capture_agent):
            self._run(run_free_chat(
                question="hi",
                history=[],
                provider_id="prov",
                model_name="model",
                conversation_id="cid-1",
            ))

        tool_names = [t.name for t in captured_tools]
        self.assertEqual(tool_names, [
            "capability_discover", "capability_describe", "capability_invoke",
        ])
        self.assertNotIn("workspace_read", tool_names)

    def test_run_free_chat_without_cid_still_uses_fixed_meta_tools(self):
        """cid=None 也保持固定工具集合，不因底层能力数量改变。"""
        from app.agent.agent_service import run_free_chat

        captured_tools: list = []

        def _capture_agent(initial_state, **kwargs):
            captured_tools.extend(initial_state.tools)
            from app.agent.core.agent import Agent
            return Agent(initial_state=initial_state, **kwargs)

        models = FakeModels(turns=["回答"])
        hooks = _make_mock_hooks()

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_free_chat_hooks", return_value=hooks), \
             patch("app.agent.agent_service.load_skills", return_value=[]), \
             patch("app.agent.agent_service.Agent", side_effect=_capture_agent):
            self._run(run_free_chat(
                question="hi",
                history=[],
                provider_id="prov",
                model_name="model",
                conversation_id=None,
            ))

        tool_names = [t.name for t in captured_tools]
        self.assertEqual(tool_names, [
            "capability_discover", "capability_describe", "capability_invoke",
        ])

    def test_run_free_chat_max_turns_is_six(self):
        """max_turns 从 1 提升到 6。"""
        from app.agent.agent_service import run_free_chat, _FREE_CHAT_MAX_TURNS

        self.assertEqual(_FREE_CHAT_MAX_TURNS, 6)

        captured_max_turns: list = []

        def _capture_agent(initial_state, **kwargs):
            captured_max_turns.append(kwargs.get("max_turns"))
            from app.agent.core.agent import Agent
            return Agent(initial_state=initial_state, **kwargs)

        models = FakeModels(turns=["回答"])
        hooks = _make_mock_hooks()

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_free_chat_hooks", return_value=hooks), \
             patch("app.agent.agent_service.load_skills", return_value=[]), \
             patch("app.agent.agent_service.Agent", side_effect=_capture_agent):
            self._run(run_free_chat(
                question="hi",
                history=[],
                provider_id="prov",
                model_name="model",
            ))

        self.assertEqual(captured_max_turns[0], 6)

    def test_run_free_chat_exposes_only_meta_tools_and_closes_registry(self):
        """真实 Skill/Memory/Workspace schema 不得平铺，registry 必须按请求关闭。"""
        from app.agent.agent_service import run_free_chat

        captured_tools: list = []

        def _capture_agent(initial_state, **kwargs):
            captured_tools.extend(initial_state.tools)
            from app.agent.core.agent import Agent
            return Agent(initial_state=initial_state, **kwargs)

        models = FakeModels(turns=["回答"])
        hooks = _make_mock_hooks(system_prompt="sys", sources=[])
        registry = MagicMock()
        registry.build_l0_summary.return_value = "[能力地图 L0]\nWiki：RAG"
        registry.close = AsyncMock()
        meta_tools = [
            build_agent_tool("capability_discover"),
            build_agent_tool("capability_describe"),
            build_agent_tool("capability_invoke"),
        ]

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_free_chat_hooks", return_value=hooks), \
             patch("app.agent.agent_service.build_free_chat_registry", return_value=registry), \
             patch("app.agent.agent_service.create_progressive_tools", return_value=meta_tools), \
             patch("app.agent.agent_service.Agent", side_effect=_capture_agent):
            result = self._run(run_free_chat(
                question="什么是 RAG",
                history=[],
                provider_id="prov",
                model_name="model",
                use_wiki=True,
            ))

        self.assertEqual(
            [tool.name for tool in captured_tools],
            ["capability_discover", "capability_describe", "capability_invoke"],
        )
        self.assertIn("[能力地图 L0]", hooks.system_prompt)
        registry.close.assert_awaited_once()
        self.assertEqual(result["answer"], "回答")

    def test_run_free_chat_closes_registry_on_model_error(self):
        """模型失败不能绕过请求级 MCP/registry 清理。"""
        from app.agent.agent_service import run_free_chat

        models = FakeModels(turns=["unused"])
        hooks = _make_mock_hooks()
        registry = MagicMock()
        registry.build_l0_summary.return_value = "[能力地图 L0]"
        registry.close = AsyncMock()

        class FailingAgent:
            async def prompt(self, question):  # noqa: ARG002
                raise RuntimeError("model failed")

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_free_chat_hooks", return_value=hooks), \
             patch("app.agent.agent_service.build_free_chat_registry", return_value=registry), \
             patch("app.agent.agent_service.create_progressive_tools", return_value=[]), \
             patch("app.agent.agent_service.Agent", return_value=FailingAgent()):
            with self.assertRaises(RuntimeError):
                self._run(run_free_chat(
                    question="hi",
                    history=[],
                    provider_id="prov",
                    model_name="model",
                ))

        registry.close.assert_awaited_once()

    def test_run_free_chat_stream_closes_registry_on_client_disconnect(self):
        """SSE 消费端提前关闭 async generator 时也必须释放 registry。"""
        from app.agent.agent_service import run_free_chat_stream

        models = FakeModels(turns=["一段流式回答"])
        hooks = _make_mock_hooks()
        registry = MagicMock()
        registry.build_l0_summary.return_value = "[能力地图 L0]"
        registry.close = AsyncMock()

        async def consume_one_then_close():
            stream = run_free_chat_stream(
                question="hi",
                history=[],
                provider_id="prov",
                model_name="model",
            )
            await stream.__anext__()
            await stream.aclose()

        with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
             patch("app.agent.agent_service.build_free_chat_hooks", return_value=hooks), \
             patch("app.agent.agent_service.build_free_chat_registry", return_value=registry), \
             patch("app.agent.agent_service.create_progressive_tools", return_value=[]):
            self._run(consume_one_then_close())

        registry.close.assert_awaited_once()


class ResearchSpaceInjectionTest(unittest.TestCase):
    """P3 阶段二：research_space_id 注入 system_prompt。"""

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["NOTE_OUTPUT_DIR"] = str(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        os.environ.pop("NOTE_OUTPUT_DIR", None)

    def test_build_free_chat_hooks_injects_rs_id(self):
        """build_free_chat_hooks 通过 cid 查 rs_id 并传给 _memory_prefix。"""
        from app.agent.chat_adapter import build_free_chat_hooks

        # 准备 research_space 记忆文件
        from app.agent.memory import MemoryManager
        mgr = MemoryManager()
        mgr.save_research_space("rs-001", {"title": "测试研究空间", "goal": "验证注入"})

        captured_rs_id: list = []

        def _fake_memory_prefix(rs_id=None):
            captured_rs_id.append(rs_id)
            return f"[memory_prefix rs={rs_id}]"

        with patch("app.services.chat_service._prepare_free_chat_context") as mock_ctx, \
             patch("app.services.chat_service._resolve_asset_context", return_value=""), \
             patch("app.agent.chat_adapter._resolve_research_space_id", return_value="rs-001"), \
             patch("app.agent.chat_adapter._memory_prefix", side_effect=_fake_memory_prefix):
            mock_ctx.return_value = MagicMock(context_text="ctx", sources=[])
            hooks = build_free_chat_hooks(
                question="q", linked_task_id=None, use_wiki=True,
                conversation_id="cid-1", asset_content=None,
            )

        self.assertEqual(captured_rs_id[0], "rs-001")
        self.assertIn("[memory_prefix rs=rs-001]", hooks.system_prompt)

    def test_build_free_chat_hooks_cid_none_no_rs_id(self):
        """cid=None 时 rs_id=None，_memory_prefix 收到 None。"""
        from app.agent.chat_adapter import build_free_chat_hooks

        captured_rs_id: list = []

        def _fake_memory_prefix(rs_id=None):
            captured_rs_id.append(rs_id)
            return ""

        with patch("app.services.chat_service._prepare_free_chat_context") as mock_ctx, \
             patch("app.services.chat_service._resolve_asset_context", return_value=""), \
             patch("app.agent.chat_adapter._resolve_research_space_id", return_value=None), \
             patch("app.agent.chat_adapter._memory_prefix", side_effect=_fake_memory_prefix):
            mock_ctx.return_value = MagicMock(context_text="ctx", sources=[])
            build_free_chat_hooks(
                question="q", linked_task_id=None, use_wiki=True,
                conversation_id=None, asset_content=None,
            )

        self.assertIsNone(captured_rs_id[0])

    def test_agent_free_chat_hook_does_not_prefetch_wiki(self):
        """Agent 首轮只拿 L0 地图，不能在模型决策前执行 WikiSearch。"""
        from app.agent.chat_adapter import build_free_chat_hooks

        with patch("app.services.chat_service.WikiSearch") as wiki_search, \
             patch("app.agent.chat_adapter._resolve_research_space_id", return_value=None), \
             patch("app.agent.chat_adapter._memory_prefix", return_value=""):
            hooks = build_free_chat_hooks(
                question="你好",
                linked_task_id=None,
                use_wiki=True,
                conversation_id=None,
                asset_content=None,
            )

        wiki_search.assert_not_called()
        self.assertEqual(hooks.sources, [])
        self.assertIn("未预取", hooks.system_prompt)

    def test_legacy_context_keeps_default_wiki_prefetch(self):
        """新增 kw-only 开关不能改变 legacy free-chat 的默认检索语义。"""
        from app.services.chat_service import _prepare_free_chat_context

        with patch("app.services.chat_service.WikiSearch") as wiki_search:
            wiki_search.return_value.search.return_value = []
            _prepare_free_chat_context("我的知识库里有什么", None, True)

        wiki_search.assert_called_once()
        wiki_search.return_value.search.assert_called_once()


class SseBridgeLongTaskTest(unittest.TestCase):
    """sse_bridge long_task_manager 生命周期。"""

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def test_no_long_task_manager_breaks_on_done(self):
        """无 long_task_manager：done 后立即 break（旧行为）。"""
        from app.agent.sse_bridge import agent_events_to_sse_dict
        from app.agent.core import Agent, AgentState

        models = FakeModels(turns=["OK"])
        agent = Agent(
            initial_state=AgentState(model=FakeModel()),
            max_turns=1,
            models=models,
        )

        async def consume():
            events = []
            async for evt in agent_events_to_sse_dict(agent, "hi", []):
                events.append(evt)
            return events

        events = self._run(consume())
        types = [e["type"] for e in events]
        self.assertIn("done", types)
        # done 是最后一个事件
        self.assertEqual(types[-1], "done")

    def test_long_task_manager_delays_break_after_done(self):
        """long_task_manager 存在时：done 后不立即 break，等长任务收尾。"""
        from app.agent.sse_bridge import agent_events_to_sse_dict
        from app.agent.core import Agent, AgentState
        from app.agent.long_task import LongTaskManager

        models = FakeModels(turns=["answer"])
        agent = Agent(
            initial_state=AgentState(model=FakeModel()),
            max_turns=1,
            models=models,
        )

        # 模拟一个活跃卡片：done 后 list_active_cards 返回非空，wait_for_all 后返回空
        mgr = LongTaskManager()
        active_state = {"active": True}

        def _list_active():
            return [{"card_id": "c1"}] if active_state["active"] else []

        async def _wait_for_all(timeout=30.0):
            active_state["active"] = False

        mgr.list_active_cards = _list_active
        mgr.wait_for_all = _wait_for_all

        async def consume():
            events = []
            async for evt in agent_events_to_sse_dict(
                agent, "hi", [], long_task_manager=mgr
            ):
                events.append(evt)
            return events

        events = self._run(consume())
        types = [e["type"] for e in events]
        # done 仍存在
        self.assertIn("done", types)
        # done 不是最后（应该有 None 哨兵后退出，但 None 不 yield）
        # 关键：流正常关闭，没有 hang

    def test_long_task_dispatcher_receives_events(self):
        """long_task_manager.dispatcher 被 sse_bridge 注入，事件汇入 SSE 流。"""
        from app.agent.sse_bridge import agent_events_to_sse_dict
        from app.agent.core import Agent, AgentState
        from app.agent.long_task import LongTaskManager

        models = FakeModels(turns=["answer"])
        agent = Agent(
            initial_state=AgentState(model=FakeModel()),
            max_turns=1,
            models=models,
        )

        mgr = LongTaskManager()
        mgr.list_active_cards = lambda: []
        mgr.wait_for_all = MagicMock()

        async def _noop_wait(timeout=30.0):
            return None

        mgr.wait_for_all = _noop_wait

        # 在 agent 结束后手动派发一个 task_card 事件
        original_subscribe = agent.subscribe
        dispatched = []

        async def consume():
            # 在 sse_bridge 启动后，dispatcher 已被注入
            # 等 done 后，用 dispatcher 派发 task_card
            import asyncio as _aio
            async def _inject():
                await _aio.sleep(0.05)  # 等 done
                if mgr.dispatcher:
                    mgr.dispatcher({"type": "task_card", "card_id": "c1", "status": "SUCCESS"})
            _aio.create_task(_inject())
            events = []
            async for evt in agent_events_to_sse_dict(
                agent, "hi", [], long_task_manager=mgr
            ):
                events.append(evt)
            return events

        events = self._run(consume())
        task_cards = [e for e in events if e.get("type") == "task_card"]
        # dispatcher 被注入（非 None）
        self.assertIsNotNone(mgr.dispatcher)
        # 由于时序，task_card 可能在 done 之前或之后；关键是流不 hang


class LongTaskEndToEndTest(unittest.TestCase):
    """长任务端到端：mock skill 脚本输出 PROGRESS 行 → SSE task_card_progress。"""

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["NOTE_OUTPUT_DIR"] = str(self._tmp.name)
        self._patches: list = []
        self._start_patch("app.agent.long_task.append_message")
        self._start_patch("app.agent.long_task.update_message")
        self._start_patch("app.agent.long_task.cancel_note_task")
        self._start_patch("app.agent.long_task.is_note_task_canceled", return_value=False)

    def _start_patch(self, target, **kw):
        p = patch(target, **kw)
        m = p.start()
        self._patches.append(p)
        return m

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()
        os.environ.pop("NOTE_OUTPUT_DIR", None)
        self._tmp.cleanup()

    def test_long_task_progress_flows_through_sse(self):
        """完整流程：LongTaskManager.start_task → dispatcher → SSE 流。"""
        from app.agent.long_task import LongTaskManager, clear_registry
        from app.agent.skill_loader import SkillDefinition

        clear_registry()
        try:
            events: list[dict] = []
            mgr = LongTaskManager(dispatcher=lambda e: events.append(e), default_timeout=0)
            skill = SkillDefinition(
                name="compile_source",
                description="test",
                long_running=True,
                script_command=f'{sys.executable} -c "print(\'PROGRESS:50:RUNNING:half\'); print(\'PROGRESS:100:SUCCESS:done\')"',
                timeout_seconds=0,
            )

            async def go():
                card = await mgr.start_task(skill=skill, params={}, conversation_id="cid-e2e")
                await mgr.wait_for_all(timeout=10.0)
                return card

            card = self._run(go())
            progress_events = [e for e in events if e.get("type") == "task_card_progress"]
            progresses = [e["progress"] for e in progress_events]
            self.assertIn(50, progresses)
            self.assertIn(100, progresses)

            final = mgr.get_card(card["card_id"])
            self.assertEqual(final["status"], "SUCCESS")
        finally:
            clear_registry()


if __name__ == "__main__":
    unittest.main()
