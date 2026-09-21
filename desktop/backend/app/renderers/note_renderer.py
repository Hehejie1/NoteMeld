from typing import Optional

from app.models.summary_input import WeightedContextPack
from app.models.summary_plan import SummaryPlan


class NoteRenderer:
    SECTION_TITLES = {
        "page": "网页与页面结构上下文",
        "search": "网页搜索补充上下文",
        "vision": "视觉理解上下文",
        "social": "评论与受众反馈上下文",
        "transcript": "转写主干上下文",
    }

    def build_final_context(self, pack: WeightedContextPack, plan: SummaryPlan) -> str:
        allowed_sources = set(plan.context_policy.get("final", ["page", "vision", "social"]))
        chunks: list[str] = []
        for block in pack.context_blocks:
            if block.include_policy not in ("always", "final_stage"):
                continue
            if allowed_sources and block.source_type not in allowed_sources:
                continue
            title = self.SECTION_TITLES.get(block.source_type, block.source_type)
            chunks.append(
                f"## {title}\n"
                f"- role: {block.role}\n"
                f"- weight: {block.weight}\n"
                f"- confidence: {block.confidence}\n"
                f"{block.content}"
            )
        context = "\n\n".join(chunks).strip()
        return self._truncate(context, int(pack.token_budget.get("max_context_chars", 8000)))

    def build_extras_with_context(
        self,
        existing_extras: Optional[str],
        pack: WeightedContextPack,
        plan: SummaryPlan,
    ) -> str:
        context = self.build_final_context(pack, plan)
        if not context:
            return existing_extras or ""
        prefix = (
            "请将以下结构化上下文作为辅助信息使用。"
            "字幕/转写是视频事实主源；视觉上下文是画面证据；"
            "网页搜索只作为外部背景和事实校验，不要写成视频作者原话。\n\n"
        )
        merged_context = prefix + context
        if existing_extras:
            return existing_extras + "\n\n" + merged_context
        return merged_context

    def _truncate(self, value: str, limit: int) -> str:
        if limit <= 0 or len(value) <= limit:
            return value
        return value[:limit].rstrip() + "..."
