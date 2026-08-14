"""Usage 收集器 + 自动写 model_usage_records。

复用现有 ``record_usage()`` 函数，保证写入 ``model_usage_records`` 的字段语义
与旧 GPTFactory 路径 100% 一致（验收标准 §7.1）。

关键设计：
- ``UsageWriter.write()`` 调用现有 ``record_usage()``，不绕过、不重建 payload
- token 值通过 ``SimpleNamespace`` 适配为 ``record_usage`` 期望的 ``response_usage`` 对象
- cost 在内存中计算但不写入 DB（DB 表无 cost 列，与现有行为一致）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from app.services.usage_tracker import record_usage
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class UsageCost:
    """成本明细（内存中计算，不写入 DB）。"""

    input: float = 0.0
    output: float = 0.0
    total: float = 0.0


@dataclass
class Usage:
    """单次 LLM 调用的 token 用量。

    Attributes:
        input_tokens: prompt token 数。
        output_tokens: completion token 数。
        total_tokens: 总 token 数（通常 = input + output）。
        cost: 成本明细（内存中计算，不写入 DB）。
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost: UsageCost = field(default_factory=UsageCost)

    @staticmethod
    def from_openai_usage(usage_obj: object | None) -> Usage:
        """从 OpenAI SDK 的 usage 对象提取 token 数。

        兼容 ``response.usage``（非流式）和 ``stream.usage`` / ``last_chunk.usage``（流式）。
        """
        if usage_obj is None:
            return Usage()
        return Usage(
            input_tokens=getattr(usage_obj, "prompt_tokens", None),
            output_tokens=getattr(usage_obj, "completion_tokens", None),
            total_tokens=getattr(usage_obj, "total_tokens", None),
        )


@dataclass
class UsageContext:
    """用量记录上下文，映射到 ``record_usage()`` 的参数。

    字段与 ``model_usage_records`` 表逐字段对应，确保迁移后字段一致。
    """

    provider_id: str
    provider_name: str
    model_name: str
    phase: str = "chat"
    task_id: Optional[str] = None
    platform: Optional[str] = None
    video_id: Optional[str] = None
    video_title: Optional[str] = None
    request_meta: Optional[dict] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class UsageWriter:
    """用量写入器，封装 ``record_usage()`` 调用。

    每次调用 ``write()`` 写入一条 ``model_usage_records`` 记录，
    字段语义与旧 GPTFactory 路径完全一致。
    """

    @staticmethod
    def write(
        usage: Usage,
        ctx: UsageContext,
        *,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        """写入一条 usage 记录。

        复用 ``record_usage()``，通过 ``SimpleNamespace`` 适配 token 字段名
        （notemeld-ai 用 ``input_tokens``，DB/record_usage 用 ``prompt_tokens``）。

        Args:
            usage: Usage 对象（含 token 数）。
            ctx: UsageContext 对象（含 provider/task 等上下文）。
            status: ``success`` 或 ``failed``。
            error_message: 失败时的错误信息（截断到 1000 字符，与现有行为一致）。
        """
        now = datetime.now(timezone.utc)
        started_at = ctx.started_at or now
        finished_at = ctx.finished_at or now

        # 适配 record_usage 期望的 response_usage 对象
        # record_usage 内部用 getattr(usage, "prompt_tokens", None) 提取
        response_usage = SimpleNamespace(
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )

        try:
            record_usage(
                provider_id=ctx.provider_id,
                provider_name=ctx.provider_name,
                model_name=ctx.model_name,
                phase=ctx.phase,
                task_id=ctx.task_id,
                platform=ctx.platform,
                video_id=ctx.video_id,
                video_title=ctx.video_title,
                response_usage=response_usage,
                status=status,
                error_message=error_message,
                started_at=started_at,
                finished_at=finished_at,
                request_meta=ctx.request_meta,
            )
        except Exception as exc:
            # 与现有 record_usage 行为一致：写入失败只 log warning，不阻塞主流程
            logger.warning(f"notemeld-ai 写入 token 记录失败: {exc}")
