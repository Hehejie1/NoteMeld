"""Conservative context budgeting without a tokenizer dependency."""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from typing import Any


MESSAGE_OVERHEAD_TOKENS = 4
IMAGE_RESERVE_TOKENS = 1200


@dataclass(frozen=True)
class TokenBudget:
    context_window_tokens: int
    output_reserve_tokens: int
    safety_margin_tokens: int
    image_reserve_tokens: int
    max_input_tokens: int


class ContextBudgetExceededError(ValueError):
    """A required input cannot fit in the configured model context window."""

    code = "context_budget_exceeded"

    def __init__(
        self,
        *,
        estimated_input_tokens: int,
        max_input_tokens: int,
        context_window_tokens: int,
    ) -> None:
        self.estimated_input_tokens = estimated_input_tokens
        self.max_input_tokens = max_input_tokens
        self.context_window_tokens = context_window_tokens
        super().__init__(
            "输入超过模型上下文："
            f"估算输入 {estimated_input_tokens} tokens，"
            f"模型输入预算 {max_input_tokens} tokens（上下文窗口 {context_window_tokens}）"
        )


def build_token_budget(context_window_tokens: int, image_count: int = 0) -> TokenBudget:
    context_window_tokens = int(context_window_tokens)
    image_count = int(image_count)
    if context_window_tokens <= 0:
        raise ValueError("context_window_tokens must be positive")
    if image_count < 0:
        raise ValueError("image_count must not be negative")

    output_reserve = min(4096, max(512, math.ceil(context_window_tokens * 0.25)))
    safety_margin = max(256, math.ceil(context_window_tokens * 0.10))
    image_reserve = image_count * IMAGE_RESERVE_TOKENS
    max_input = max(
        256,
        context_window_tokens - output_reserve - safety_margin - image_reserve,
    )
    return TokenBudget(
        context_window_tokens=context_window_tokens,
        output_reserve_tokens=output_reserve,
        safety_margin_tokens=safety_margin,
        image_reserve_tokens=image_reserve,
        max_input_tokens=max_input,
    )


def _text_tokens(value: str) -> int:
    return math.ceil(len(value.encode("utf-8")) / 3)


def _structured_tokens(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return _text_tokens(value)
    try:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        raw = str(value)
    return _text_tokens(raw)


def _content_tokens(content: Any) -> int:
    if isinstance(content, str):
        return _text_tokens(content)
    if not isinstance(content, list):
        return _structured_tokens(content)

    total = 0
    for part in content:
        if not isinstance(part, dict):
            total += _structured_tokens(part)
        elif part.get("type") == "image_url":
            # Image cost is reserved by build_token_budget(), not by URL/base64 length.
            continue
        elif part.get("type") == "text":
            total += _text_tokens(str(part.get("text") or ""))
        else:
            total += _structured_tokens(part)
    return total


def estimate_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for message in messages or []:
        total += MESSAGE_OVERHEAD_TOKENS
        total += _content_tokens(message.get("content"))
        for key, value in message.items():
            if key in {"role", "content"}:
                continue
            total += _structured_tokens(value)
    return total


def _normalize_tools(tools: list[Any] | None) -> list[Any]:
    normalized: list[Any] = []
    for tool in tools or []:
        to_openai = getattr(tool, "to_openai_function", None)
        normalized.append(to_openai() if callable(to_openai) else tool)
    return normalized


def estimate_tools_tokens(tools: list[Any] | None) -> int:
    normalized = _normalize_tools(tools)
    return _structured_tokens(normalized) if normalized else 0


def count_message_images(messages: list[dict]) -> int:
    count = 0
    for message in messages or []:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        count += sum(
            1
            for part in content
            if isinstance(part, dict) and part.get("type") == "image_url"
        )
    return count


def _tool_group_indices(messages: list[dict]) -> tuple[list[set[int]], set[int]]:
    """Validate OpenAI tool protocol groups with one strict forward scan."""
    groups: list[set[int]] = []
    invalid_indices: set[int] = set()
    index = 0

    while index < len(messages):
        message = messages[index]
        role = message.get("role")
        tool_calls = message.get("tool_calls")

        if role == "tool":
            invalid_indices.add(index)
            index += 1
            continue

        if role != "assistant" or not tool_calls:
            index += 1
            continue

        group = {index}
        result_ids: list[str] = []
        next_index = index + 1
        while next_index < len(messages) and messages[next_index].get("role") == "tool":
            group.add(next_index)
            result_ids.append(str(messages[next_index].get("tool_call_id") or ""))
            next_index += 1

        call_ids = [
            str(call.get("id") or "") if isinstance(call, dict) else ""
            for call in tool_calls
        ]
        valid = (
            bool(call_ids)
            and all(call_ids)
            and len(set(call_ids)) == len(call_ids)
            and result_ids == call_ids
        )
        if valid:
            groups.append(group)
        else:
            invalid_indices.update(group)
        index = next_index

    return groups, invalid_indices


def trim_messages_to_budget(
    messages: list[dict],
    budget: TokenBudget,
    tools: list[Any] | None = None,
) -> list[dict]:
    """Return a trimmed deep copy while preserving required message semantics."""
    copied = copy.deepcopy(list(messages or []))
    tools_tokens = estimate_tools_tokens(tools)

    latest_user = next(
        (index for index in range(len(copied) - 1, -1, -1) if copied[index].get("role") == "user"),
        None,
    )
    pinned = {
        index for index, message in enumerate(copied) if message.get("role") == "system"
    }
    if latest_user is not None:
        pinned.add(latest_user)

    def effective_budget(candidate_messages: list[dict]) -> TokenBudget:
        return build_token_budget(
            budget.context_window_tokens,
            image_count=count_message_images(candidate_messages),
        )

    required_messages = [message for index, message in enumerate(copied) if index in pinned]
    required_tokens = estimate_messages_tokens(required_messages) + tools_tokens
    required_budget = effective_budget(required_messages)
    if required_tokens > required_budget.max_input_tokens:
        raise ContextBudgetExceededError(
            estimated_input_tokens=required_tokens,
            max_input_tokens=required_budget.max_input_tokens,
            context_window_tokens=budget.context_window_tokens,
        )

    tool_groups, invalid_tool_indices = _tool_group_indices(copied)
    group_by_index: dict[int, set[int]] = {}
    for group in tool_groups:
        for index in group:
            group_by_index[index] = group

    retained = set(range(len(copied))) - invalid_tool_indices

    def retained_messages() -> list[dict]:
        return [copied[index] for index in range(len(copied)) if index in retained]

    def fits_current() -> bool:
        candidate = retained_messages()
        return (
            estimate_messages_tokens(candidate) + tools_tokens
            <= effective_budget(candidate).max_input_tokens
        )

    if fits_current():
        return retained_messages()

    visited_groups: set[int] = set()
    for index in range(len(copied)):
        if index not in retained or index in pinned:
            continue
        group = group_by_index.get(index, {index})
        group_key = min(group)
        if group_key in visited_groups or group & pinned:
            continue
        visited_groups.add(group_key)
        retained.difference_update(group)
        if fits_current():
            return retained_messages()

    candidate = retained_messages()
    estimated = estimate_messages_tokens(candidate) + tools_tokens
    candidate_budget = effective_budget(candidate)
    if estimated > candidate_budget.max_input_tokens:
        raise ContextBudgetExceededError(
            estimated_input_tokens=estimated,
            max_input_tokens=candidate_budget.max_input_tokens,
            context_window_tokens=budget.context_window_tokens,
        )
    return candidate
