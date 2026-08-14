"""AbortSignal：基于 asyncio.Event 的取消信号。

Agent/工具执行中通过 ``signal.aborted`` 轮询，或 ``await signal.wait()`` 被动感知。
"""

from __future__ import annotations

import asyncio


class AbortSignal:
    """可取消信号。封装 asyncio.Event 并携带取消原因。"""

    __slots__ = ("_event", "_reason")

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._reason: str | None = None

    # ------------------------------------------------------------------ #
    # 生产者接口
    # ------------------------------------------------------------------ #
    def abort(self, reason: str = "aborted") -> None:
        """触发取消。幂等：多次调用以第一次 reason 为准。"""
        if self._event.is_set():
            return
        self._reason = reason
        self._event.set()

    # ------------------------------------------------------------------ #
    # 消费者接口
    # ------------------------------------------------------------------ #
    @property
    def aborted(self) -> bool:
        """是否已取消（快速轮询，不阻塞）。"""
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        """取消原因；未取消时为 None。"""
        return self._reason

    async def wait(self) -> None:
        """等待直到被取消。若已取消则立即返回。"""
        await self._event.wait()

    # 兼容直接作为 asyncio.Event 传给 notemeld-ai（需要 .is_set()）。
    def is_set(self) -> bool:  # pragma: no cover - 薄转发
        return self._event.is_set()
