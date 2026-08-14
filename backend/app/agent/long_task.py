"""P3-T4: 长任务卡片 + SSE 事件 + 持久化 + 取消 + 自动 follow-up。

长任务（``skill.long_running=true``）的执行流::

    Agent tool_call → build_skill_tool.execute
        → LongTaskManager.start_task(skill, params, cid, call_id)
            1) 生成 card_id + task_id
            2) append_message(cid, {id=card_id, role=assistant, message_type=task_card,
                                    content=title, status=PENDING, meta={card_id,task_id,kind,title}})
            3) emit SSE {"type":"task_card","card_id","kind","task_id","status":"PENDING","title","progress":null}
            4) asyncio.create_task(_run_skill_streaming(...))  # 后台执行
            5) return card dict  # 立即返回，不阻塞 Agent loop

    后台 _run_skill_streaming:
        - 启动子进程（create_subprocess_exec，非 shell）
        - 逐行读 stdout：
            - PROGRESS:NN:STATUS:details  → emit task_card_progress + update_message
            - 其他行 → 累积为 stdout
        - signal.aborted → kill 子进程
        - timeout_seconds > 0 → 超时 kill
        - 完成 → update_message(SUCCESS/FAILED/CANCELED) + emit final task_card
        - auto_follow_up=True 且 manager 持有 agent → 排队 agent.follow_up(summary)

    cancel_task(card_id):
        - signal.abort("用户取消")
        - cancel_note_task(task_id, "用户取消")  # 写 status.json
        - update_message(status=CANCELED) + emit task_card CANCELED
        - 不 await 后台 task（让子进程被 kill 后自然结束）

设计要点：
- 卡片状态必须写 ``conversation_messages``（known-pitfall：刷新页面状态不丢）。
- ``dispatcher`` 是 ``Optional[Callable[[dict], Awaitable[None] | None]]``；由上层
  ``agent_service`` / ``sse_bridge`` 注入，把事件 dict 转发到 SSE 通道。本模块不直接
  耦合 SSE。
- ``auto_follow_up`` 默认 False；spec §6 要求"follow-up 关闭后不产生新 assistant 消息"，
  即关闭时不能调 ``agent.follow_up``。
- 子进程 stdout 行解析：``PROGRESS:<int>:<STATUS>:<details>`` 三段冒号分隔；
  非该格式行视为普通 stdout 累积。
- ``task_id`` 用 ``lt-{card_id[:8]}``，便于在 ``note_results/{task_id}.status.json``
  中追踪。
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.agent.core.signal import AbortSignal
from app.agent.skill_loader import SkillDefinition, _substitute_command
from app.services.conversation_store import append_message, update_message
from app.services.note_task_store import cancel_note_task, is_note_task_canceled
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: 卡片标题前缀（spec B.6 示例："视频编译中"）。
_TITLE_TEMPLATE = "{skill_name} 执行中"

#: 任务 id 前缀（与 note_task_store 的 task_id 命名空间对齐）。
_TASK_ID_PREFIX = "lt-"

#: 取消后等待子进程退出的最长时间（秒）；spec §4 要求 1s 内 CANCELED。
_CANCEL_GRACE_SECONDS = 1.0

#: stdout 进度行前缀。
_PROGRESS_PREFIX = "PROGRESS:"

#: 进度行正则：PROGRESS:<int 0-100>:<STATUS>:<details>
_PROGRESS_RE = re.compile(r"^PROGRESS:(\d+):([A-Z_]+):(.*)$")


# ---------------------------------------------------------------------------
# 模块级注册表：card_id → LongTaskManager（供 HTTP cancel_task 路由反查）
# ---------------------------------------------------------------------------

_card_managers: dict[str, "LongTaskManager"] = {}


def register_card(card_id: str, manager: "LongTaskManager") -> None:
    """登记 card_id 与 manager 的映射（start_task 自动调用）。"""
    _card_managers[card_id] = manager


def find_manager_by_card(card_id: str) -> Optional["LongTaskManager"]:
    """根据 card_id 反查 LongTaskManager；找不到返回 None。"""
    return _card_managers.get(card_id)


def unregister_card(card_id: str) -> None:
    """注销 card_id（用于测试清理 / 内存回收）。"""
    _card_managers.pop(card_id, None)


def clear_registry() -> None:
    """清空注册表（测试用）。"""
    _card_managers.clear()


# ---------------------------------------------------------------------------
# 类型别名
# ---------------------------------------------------------------------------

#: 事件派发器：接收事件 dict（同步或异步）；通常由 sse_bridge 注入。
Dispatcher = Callable[[dict], Optional[Awaitable[None]]]


# ---------------------------------------------------------------------------
# LongTaskManager
# ---------------------------------------------------------------------------


@dataclass
class LongTaskManager:
    """长任务卡片管理器。

    Attributes:
        agent: 可选的 Agent 实例，用于 ``auto_follow_up`` 时排队后续消息。
        auto_follow_up: 任务完成（SUCCESS/FAILED）后是否自动让 Agent 生成总结。
            CANCELED 不触发 follow_up。spec §6 要求关闭时不产生新 assistant 消息。
        dispatcher: 事件派发回调；为 None 时事件仅写库不发 SSE。
        default_timeout: 默认超时（秒）；0 表示不限。skill.timeout_seconds 优先。
    """

    agent: Any = None
    auto_follow_up: bool = False
    dispatcher: Optional[Dispatcher] = None
    default_timeout: int = 0

    # 运行时状态（非 dataclass 字段语义；运行时维护）
    _tasks: dict = field(default_factory=dict)        # card_id -> asyncio.Task
    _signals: dict = field(default_factory=dict)      # card_id -> AbortSignal
    _cards: dict = field(default_factory=dict)        # card_id -> card dict cache
    _conversation_id: str = ""

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #
    async def start_task(
        self,
        *,
        skill: SkillDefinition,
        params: dict,
        conversation_id: str,
        call_id: Optional[str] = None,
    ) -> dict:
        """启动长任务，立即返回卡片 dict（status=PENDING）。

        Args:
            skill: skill 定义（必须 long_running=True）。
            params: 已校验/已收集的参数。
            conversation_id: 关联会话 id；卡片消息会写入此会话。
            call_id: 触发此长任务的 Agent tool_call id（用于关联日志，可选）。

        Returns:
            卡片 dict：``{card_id, task_id, kind, title, status, progress, conversation_id}``。

        Raises:
            ValueError: conversation_id 为空。
        """
        if not conversation_id:
            raise ValueError("conversation_id 不能为空")

        card_id = f"card-{uuid.uuid4().hex[:12]}"
        task_id = f"{_TASK_ID_PREFIX}{card_id[-8:]}"
        title = _TITLE_TEMPLATE.format(skill_name=skill.name)
        kind = skill.name

        card: dict = {
            "card_id": card_id,
            "task_id": task_id,
            "kind": kind,
            "title": title,
            "status": "PENDING",
            "progress": None,
            "details": "",
            "conversation_id": conversation_id,
            "call_id": call_id,
            "started_at": _now_iso(),
        }
        self._cards[card_id] = card
        self._conversation_id = conversation_id
        register_card(card_id, self)

        # 1) 持久化 PENDING 卡片消息
        try:
            await asyncio.to_thread(
                append_message,
                conversation_id,
                {
                    "id": card_id,
                    "role": "assistant",
                    "message_type": "task_card",
                    "content": title,
                    "status": "PENDING",
                    "meta": {
                        "card_id": card_id,
                        "task_id": task_id,
                        "kind": kind,
                        "title": title,
                        "call_id": call_id,
                    },
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("append task_card PENDING 失败 cid=%s card=%s: %s", conversation_id, card_id, exc)
            # 不阻塞后续：卡片仍发 SSE，刷新时可能丢，但任务可继续执行

        # 2) 发 SSE task_card PENDING
        self._emit_task_card(card)

        # 3) 启动后台执行
        signal = AbortSignal()
        self._signals[card_id] = signal
        bg_task = asyncio.create_task(
            self._run_skill_streaming(card_id=card_id, skill=skill, params=params, signal=signal),
            name=f"longtask-{card_id}",
        )
        self._tasks[card_id] = bg_task
        bg_task.add_done_callback(lambda t, cid=card_id: self._on_bg_done(cid, t))

        return dict(card)

    async def cancel_task(self, card_id: str, reason: str = "用户取消") -> bool:
        """取消长任务。

        Args:
            card_id: 卡片 id。
            reason: 取消原因。

        Returns:
            True 表示找到卡片并取消；False 表示卡片不存在或已结束。
        """
        card = self._cards.get(card_id)
        if card is None:
            return False
        if card.get("status") in ("SUCCESS", "FAILED", "CANCELED"):
            return False

        task_id = card.get("task_id") or ""
        signal = self._signals.get(card_id)

        # 1) 触发 signal → 子进程被 kill
        if signal is not None and not signal.aborted:
            signal.abort(reason=reason)

        # 2) 写 note_task_store 状态文件（与现有 cancel_note_task 语义对齐）
        if task_id:
            try:
                await asyncio.to_thread(cancel_note_task, task_id, reason)
            except Exception as exc:  # noqa: BLE001
                logger.warning("cancel_note_task(%s) 失败: %s", task_id, exc)

        # 3) 更新卡片状态 + 持久化 + 发 SSE
        card["status"] = "CANCELED"
        card["details"] = reason
        card["ended_at"] = _now_iso()
        self._persist_card(card_id, content=card.get("title", ""), status="CANCELED", extra_meta={"details": reason})
        self._emit_task_card(card)

        logger.info("长任务已取消 card=%s task=%s reason=%s", card_id, task_id, reason)
        return True

    def get_card(self, card_id: str) -> Optional[dict]:
        """从内存缓存读取卡片状态。"""
        return self._cards.get(card_id)

    def list_active_cards(self) -> list[dict]:
        """返回所有未结束的卡片。"""
        return [dict(c) for c in self._cards.values() if c.get("status") in ("PENDING", "RUNNING")]

    async def wait_for_all(self, timeout: float = 30.0) -> None:
        """等待所有后台任务结束（用于测试 / 优雅关闭）。"""
        tasks = [t for t in self._tasks.values() if not t.done()]
        if not tasks:
            return
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("wait_for_all 超时 %ss，仍有 %d 个任务", timeout, len(tasks))

    # ------------------------------------------------------------------ #
    # 后台执行
    # ------------------------------------------------------------------ #
    async def _run_skill_streaming(
        self,
        *,
        card_id: str,
        skill: SkillDefinition,
        params: dict,
        signal: AbortSignal,
    ) -> None:
        """后台执行 skill 脚本，逐行解析 stdout 进度。"""
        card = self._cards.get(card_id)
        if card is None:
            return

        # 状态：RUNNING
        card["status"] = "RUNNING"
        card["progress"] = 0
        card["details"] = "已启动"
        self._persist_card(card_id, status="RUNNING", extra_meta={"progress": 0, "details": "已启动"})
        self._emit_task_card(card)
        self._emit_progress(card_id, status="RUNNING", progress=0, details="已启动")

        # 解析命令
        try:
            argv = _substitute_command(skill.script_command, params)
        except Exception as exc:  # noqa: BLE001
            await self._finalize_failed(card_id, f"命令解析失败: {exc}", stdout="", stderr="", returncode=-1)
            return
        if not argv:
            await self._finalize_failed(card_id, "空命令", stdout="", stderr="", returncode=-1)
            return

        cwd = str(skill.working_dir) if skill.working_dir else None
        timeout_s = skill.timeout_seconds if skill.timeout_seconds and skill.timeout_seconds > 0 else (
            self.default_timeout if self.default_timeout > 0 else None
        )

        # 启动子进程
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
        except FileNotFoundError as exc:
            await self._finalize_failed(card_id, f"可执行文件不存在: {exc}", stdout="", stderr=str(exc), returncode=-1)
            return
        except Exception as exc:  # noqa: BLE001
            await self._finalize_failed(card_id, f"启动失败: {exc}", stdout="", stderr=str(exc), returncode=-1)
            return

        stdout_lines: list[str] = []
        stderr_chunks: list[bytes] = []
        timed_out = False

        async def _read_stderr() -> None:
            try:
                data = await proc.stderr.read()
                stderr_chunks.append(data or b"")
            except Exception as exc:  # noqa: BLE001
                logger.warning("read stderr 失败 card=%s: %s", card_id, exc)

        stderr_task = asyncio.create_task(_read_stderr())
        start_ts = time.time()

        try:
            # 逐行读 stdout
            while True:
                if signal.aborted:
                    _kill_proc(proc)
                    break
                try:
                    line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
                except asyncio.TimeoutError:
                    # 没有新行，继续轮询 abort / timeout
                    if timeout_s is not None:
                        elapsed = time.time() - start_ts
                        if elapsed > timeout_s:
                            timed_out = True
                            _kill_proc(proc)
                            break
                    continue
                if not line_bytes:
                    break  # EOF
                try:
                    line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
                except Exception:  # noqa: BLE001
                    line = ""
                if not line:
                    continue
                m = _PROGRESS_RE.match(line)
                if m:
                    progress = max(0, min(100, int(m.group(1))))
                    prog_status = m.group(2)
                    details = m.group(3)
                    card["progress"] = progress
                    card["details"] = details
                    card["status"] = prog_status
                    self._persist_card(
                        card_id,
                        status=prog_status,
                        extra_meta={"progress": progress, "details": details, "last_progress_line": line},
                    )
                    self._emit_progress(card_id, status=prog_status, progress=progress, details=details)
                else:
                    stdout_lines.append(line)
                    # 周期性把最新 stdout 摘要写库（每 5 行写一次，避免 DB 压力）
                    if len(stdout_lines) % 5 == 0:
                        snippet = "\n".join(stdout_lines[-10:])
                        self._persist_card(
                            card_id,
                            extra_meta={"progress": card.get("progress"), "stdout_tail": snippet},
                        )
        except asyncio.CancelledError:
            _kill_proc(proc)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("读取 stdout 异常 card=%s: %s", card_id, exc, exc_info=True)
            _kill_proc(proc)
        finally:
            # 确保 stderr_task 结束
            try:
                await asyncio.wait_for(stderr_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                stderr_task.cancel()

            # 等待子进程退出
            try:
                await asyncio.wait_for(proc.wait(), timeout=_CANCEL_GRACE_SECONDS if signal.aborted else 5.0)
            except asyncio.TimeoutError:
                _kill_proc(proc)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass

        returncode = proc.returncode if proc.returncode is not None else -1
        stdout_text = "\n".join(stdout_lines)
        stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace")

        # 最终状态判定
        if signal.aborted or is_note_task_canceled(card.get("task_id") or ""):
            await self._finalize_canceled(card_id, reason=signal.reason or "已取消", stdout=stdout_text, stderr=stderr_text, returncode=returncode)
        elif timed_out:
            await self._finalize_failed(card_id, f"超时（{timeout_s}s）", stdout=stdout_text, stderr=stderr_text, returncode=returncode, timed_out=True)
        elif returncode == 0:
            await self._finalize_success(card_id, stdout=stdout_text, stderr=stderr_text, returncode=returncode)
        else:
            await self._finalize_failed(card_id, f"退出码 {returncode}", stdout=stdout_text, stderr=stderr_text, returncode=returncode)

    # ------------------------------------------------------------------ #
    # 终态收尾
    # ------------------------------------------------------------------ #
    async def _finalize_success(self, card_id: str, *, stdout: str, stderr: str, returncode: int) -> None:
        card = self._cards.get(card_id)
        if card is None:
            return
        card["status"] = "SUCCESS"
        card["progress"] = 100
        card["details"] = "完成"
        card["ended_at"] = _now_iso()
        summary = _build_summary(card, stdout=stdout, stderr=stderr, returncode=returncode, ok=True)
        self._persist_card(
            card_id,
            content=summary,
            status="SUCCESS",
            extra_meta={
                "progress": 100,
                "details": "完成",
                "returncode": returncode,
                "stdout": stdout[-4096:],
                "stderr": stderr[-1024:],
                "ended_at": card["ended_at"],
            },
        )
        self._emit_task_card(card)
        self._emit_progress(card_id, status="SUCCESS", progress=100, details="完成")
        logger.info("长任务 SUCCESS card=%s task=%s", card_id, card.get("task_id"))

        await self._maybe_follow_up(card, summary=summary, ok=True, stdout=stdout)

    async def _finalize_failed(
        self,
        card_id: str,
        message: str,
        *,
        stdout: str,
        stderr: str,
        returncode: int,
        timed_out: bool = False,
    ) -> None:
        card = self._cards.get(card_id)
        if card is None:
            return
        card["status"] = "FAILED"
        card["details"] = message
        card["ended_at"] = _now_iso()
        summary = _build_summary(card, stdout=stdout, stderr=stderr, returncode=returncode, ok=False, message=message, timed_out=timed_out)
        self._persist_card(
            card_id,
            content=summary,
            status="FAILED",
            error=True,
            extra_meta={
                "details": message,
                "returncode": returncode,
                "stdout": stdout[-4096:],
                "stderr": stderr[-1024:],
                "timed_out": timed_out,
                "ended_at": card["ended_at"],
            },
        )
        self._emit_task_card(card)
        self._emit_progress(card_id, status="FAILED", progress=card.get("progress") or 0, details=message)
        logger.warning("长任务 FAILED card=%s task=%s msg=%s", card_id, card.get("task_id"), message)

        await self._maybe_follow_up(card, summary=summary, ok=False, stdout=stdout)

    async def _finalize_canceled(
        self,
        card_id: str,
        *,
        reason: str,
        stdout: str,
        stderr: str,
        returncode: int,
    ) -> None:
        card = self._cards.get(card_id)
        if card is None:
            return
        if card.get("status") == "CANCELED":
            # cancel_task 已先更新过；这里只补 meta
            return
        card["status"] = "CANCELED"
        card["details"] = reason
        card["ended_at"] = _now_iso()
        self._persist_card(
            card_id,
            status="CANCELED",
            extra_meta={
                "details": reason,
                "returncode": returncode,
                "stdout": stdout[-4096:],
                "stderr": stderr[-1024:],
                "ended_at": card["ended_at"],
            },
        )
        self._emit_task_card(card)
        self._emit_progress(card_id, status="CANCELED", progress=card.get("progress") or 0, details=reason)
        logger.info("长任务 CANCELED (finalize) card=%s task=%s", card_id, card.get("task_id"))
        # CANCELED 不触发 follow_up（spec §6）

    # ------------------------------------------------------------------ #
    # follow_up
    # ------------------------------------------------------------------ #
    async def _maybe_follow_up(self, card: dict, *, summary: str, ok: bool, stdout: str) -> None:
        """如果开启 auto_follow_up 且持有 agent，排队后续 prompt。"""
        if not self.auto_follow_up or self.agent is None:
            return
        prompt_text = (
            f"长任务 {card.get('kind')} 已{'成功完成' if ok else '失败'}。"
            f"任务 id: {card.get('task_id')}。\n\n摘要:\n{summary}\n\n"
            "请基于上述结果继续协助用户（如总结要点、提示下一步动作等）。"
        )
        try:
            asyncio.create_task(self._agent_follow_up(prompt_text))  # fire-and-forget
        except Exception as exc:  # noqa: BLE001
            logger.warning("排队 follow_up 失败 card=%s: %s", card.get("card_id"), exc)

    async def _agent_follow_up(self, prompt_text: str) -> None:
        try:
            await self.agent.follow_up(prompt_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent.follow_up 失败: %s", exc)

    # ------------------------------------------------------------------ #
    # 持久化 + 事件派发
    # ------------------------------------------------------------------ #
    def _persist_card(
        self,
        card_id: str,
        *,
        content: Optional[str] = None,
        status: Optional[str] = None,
        error: bool = False,
        extra_meta: Optional[dict] = None,
    ) -> None:
        """更新 conversation_messages 中的卡片消息（best-effort）。"""
        card = self._cards.get(card_id)
        if card is None:
            return
        cid = card.get("conversation_id") or self._conversation_id
        if not cid:
            return
        patch: dict = {}
        if content is not None:
            patch["content"] = content
        if status is not None:
            patch["status"] = status
        if error:
            patch["error"] = True
        # 合并 meta：保留原有 + 新增
        base_meta = {
            "card_id": card_id,
            "task_id": card.get("task_id", ""),
            "kind": card.get("kind", ""),
            "title": card.get("title", ""),
        }
        if extra_meta:
            base_meta.update(extra_meta)
        patch["meta"] = base_meta

        try:
            asyncio.create_task(asyncio.to_thread(update_message, cid, card_id, patch))
        except Exception as exc:  # noqa: BLE001
            logger.warning("update_message 失败 card=%s: %s", card_id, exc)

    def _emit_task_card(self, card: dict) -> None:
        """发 SSE task_card 事件。"""
        if self.dispatcher is None:
            return
        event = {
            "type": "task_card",
            "card_id": card.get("card_id"),
            "kind": card.get("kind"),
            "task_id": card.get("task_id"),
            "status": card.get("status"),
            "title": card.get("title"),
            "progress": card.get("progress"),
        }
        self._dispatch(event)

    def _emit_progress(self, card_id: str, *, status: str, progress: int, details: str) -> None:
        """发 SSE task_card_progress 事件。"""
        if self.dispatcher is None:
            return
        event = {
            "type": "task_card_progress",
            "card_id": card_id,
            "status": status,
            "progress": progress,
            "details": details,
        }
        self._dispatch(event)

    def _dispatch(self, event: dict) -> None:
        if self.dispatcher is None:
            return
        try:
            maybe = self.dispatcher(event)
            if asyncio.iscoroutine(maybe):
                asyncio.create_task(maybe)
        except Exception as exc:  # noqa: BLE001
            logger.warning("dispatcher 派发事件失败: %s", exc)

    def _on_bg_done(self, card_id: str, task: asyncio.Task) -> None:
        """后台任务结束回调：清理 + 记录异常。"""
        self._tasks.pop(card_id, None)
        self._signals.pop(card_id, None)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("长任务后台执行异常 card=%s: %s", card_id, exc, exc_info=exc)
            card = self._cards.get(card_id)
            if card is not None and card.get("status") not in ("SUCCESS", "FAILED", "CANCELED"):
                card["status"] = "FAILED"
                card["details"] = f"内部异常: {exc}"
                card["ended_at"] = _now_iso()
                self._persist_card(card_id, status="FAILED", error=True, extra_meta={"details": card["details"]})
                self._emit_task_card(card)


# ---------------------------------------------------------------------------
# 助手
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _kill_proc(proc: asyncio.subprocess.Process) -> None:
    try:
        if proc.returncode is None:
            proc.kill()
    except (ProcessLookupError, Exception):  # noqa: BLE001
        pass


def _build_summary(
    card: dict,
    *,
    stdout: str,
    stderr: str,
    returncode: int,
    ok: bool,
    message: str = "",
    timed_out: bool = False,
) -> str:
    """构造卡片 content 文本（用于持久化与 follow_up 摘要）。"""
    lines = [
        f"# {card.get('title', card.get('kind', '长任务'))}",
        f"- 状态: {'成功' if ok else '失败' if not timed_out else '超时'}",
        f"- 任务 id: {card.get('task_id', '')}",
        f"- 退出码: {returncode}",
    ]
    if message:
        lines.append(f"- 说明: {message}")
    if stdout:
        snippet = stdout[-1024:]
        lines.append("\n## 输出\n```\n" + snippet + "\n```")
    if stderr:
        snippet = stderr[-512:]
        lines.append("\n## 错误输出\n```\n" + snippet + "\n```")
    return "\n".join(lines)


__all__ = [
    "LongTaskManager",
    "Dispatcher",
    "register_card",
    "find_manager_by_card",
    "unregister_card",
    "clear_registry",
]
