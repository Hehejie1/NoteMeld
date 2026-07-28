import json
import logging
import os
from datetime import datetime, timezone

from app.services.usage_tracker import record_usage


logger = logging.getLogger(__name__)


class WikiPageMerger:
    MERGE_TIMEOUT_SECONDS = float(os.getenv("NOTEMELD_WIKI_MERGE_TIMEOUT_SECONDS", "20"))

    def merge(
        self,
        page_type: str,
        page_title: str,
        current_markdown: str,
        contribution_payload: list[dict],
        gpt=None,
        fallback_markdown: str = "",
    ) -> str:
        if gpt is None or not getattr(gpt, "client", None) or not getattr(gpt, "model", None):
            return fallback_markdown

        provider_id = getattr(gpt, "usage_context", {}).get("provider_id") or "unknown"
        provider_name = getattr(gpt, "usage_context", {}).get("provider_name") or "unknown"

        prompt = self._build_prompt(page_type, page_title, current_markdown, contribution_payload)
        started_at = datetime.now(timezone.utc)
        try:
            response = gpt.client.chat.completions.create(
                model=gpt.model,
                temperature=0.2,
                timeout=self.MERGE_TIMEOUT_SECONDS,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是 Wiki 页面合并器。你必须输出 Markdown。"
                            "保留来源反链、Claims、Evidence、冲突事实。"
                            "不能编造信息，不能丢失任何有来源支撑的事实。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            finished_at = datetime.now(timezone.utc)
            record_usage(
                provider_id=provider_id,
                provider_name=provider_name,
                model_name=gpt.model,
                phase="wiki_merge",
                response=response,
                status="success",
                started_at=started_at,
                finished_at=finished_at,
                request_meta={"page_type": page_type, "page_title": page_title},
            )
            content = ((response.choices or [None])[0].message.content or "").strip()
            return content or fallback_markdown
        except Exception as exc:
            finished_at = datetime.now(timezone.utc)
            record_usage(
                provider_id=provider_id,
                provider_name=provider_name,
                model_name=gpt.model,
                phase="wiki_merge",
                status="failed",
                error_message=str(exc)[:1000],
                started_at=started_at,
                finished_at=finished_at,
                request_meta={"page_type": page_type, "page_title": page_title},
            )
            logger.warning("LLM Wiki merger failed for %s:%s, fallback to deterministic merge: %s", page_type, page_title, exc)
            return fallback_markdown

    def _build_prompt(self, page_type: str, page_title: str, current_markdown: str, contribution_payload: list[dict]) -> str:
        payload = json.dumps(contribution_payload, ensure_ascii=False, indent=2)
        return (
            f"页面类型: {page_type}\n"
            f"页面标题: {page_title}\n\n"
            "现有页面 Markdown:\n"
            f"{current_markdown or '(empty)'}\n\n"
            "新的贡献切片 JSON:\n"
            f"{payload}\n\n"
            "请合并为一个 Markdown 页面，要求：\n"
            "1. 保留 Descriptions / Claims / Evidence / Sources 结构。\n"
            "2. 如果来源之间存在差异，不要抹平，保留并列事实。\n"
            "3. 所有证据都必须保留来源反链。\n"
            "4. 只输出最终 Markdown，不要解释。"
        )
