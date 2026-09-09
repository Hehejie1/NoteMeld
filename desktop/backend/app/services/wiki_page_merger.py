import json
import logging
import os

logger = logging.getLogger(__name__)


class WikiPageMerger:
    """Wiki 页面合并器：调 LLM 将贡献切片合并到现有 Markdown 页面。

    T11 迁移完成：通过 ``gpt.create_chat_completion()`` 走 notemeld-ai 适配器
    （NotemeldGPT），usage 由适配器自动写入（success/failed 各一条）。

    - ``timeout``：通过 NotemeldGPT / LLMContext 透传，默认 20 秒。
    - ``temperature``：通过临时覆盖 ``gpt.temperature`` 实现 0.2 低温合并。
    """

    MERGE_TEMPERATURE = 0.2
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
        if gpt is None or not getattr(gpt, "model", None):
            return fallback_markdown

        if not hasattr(gpt, "create_chat_completion"):
            # 兜底：无 create_chat_completion 方法的 GPT 实例，走 fallback
            logger.warning("GPT 实例无 create_chat_completion 方法，走 fallback merge: %s", page_title)
            return fallback_markdown

        prompt = self._build_prompt(page_type, page_title, current_markdown, contribution_payload)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Wiki 页面合并器。你必须输出 Markdown。"
                    "保留来源反链、Claims、Evidence、冲突事实。"
                    "不能编造信息，不能丢失任何有来源支撑的事实。"
                ),
            },
            {"role": "user", "content": prompt},
        ]

        # 临时覆盖 temperature 为低温合并（0.2），调用后恢复
        original_temperature = getattr(gpt, "temperature", None)
        try:
            gpt.temperature = self.MERGE_TEMPERATURE
            response = gpt.create_chat_completion(
                messages=messages,
                phase_label="wiki_merge",
                request_meta={
                    "stage": "wiki_merge",
                    "page_type": page_type,
                    "page_title": page_title,
                },
                timeout=self.MERGE_TIMEOUT_SECONDS,
            )
            content = gpt._extract_message_content(response, "wiki_merge")
            return content or fallback_markdown
        except Exception as exc:
            logger.warning(
                "LLM Wiki merger failed for %s:%s, fallback to deterministic merge: %s",
                page_type, page_title, exc,
            )
            return fallback_markdown
        finally:
            if original_temperature is not None:
                gpt.temperature = original_temperature

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
