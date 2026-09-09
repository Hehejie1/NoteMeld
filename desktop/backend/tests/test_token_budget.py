from __future__ import annotations

import copy
import json

import pytest

from app.gpt.request_chunker import RequestChunker
from app.gpt.token_budget import (
    ContextBudgetExceededError,
    build_token_budget,
    count_message_images,
    estimate_messages_tokens,
    trim_messages_to_budget,
)


def _message_builder(segments, image_urls, **_kwargs):
    text = "".join(segment["text"] for segment in segments)
    content: list[dict] | str = text
    if image_urls:
        content = [{"type": "text", "text": text}]
        content.extend(
            {"type": "image_url", "image_url": {"url": image_url}}
            for image_url in image_urls
        )
    return [{"role": "user", "content": content}]


def test_4096_budget_uses_literal_spec_reserves():
    budget = build_token_budget(4096)

    assert budget.output_reserve_tokens == 1024
    assert budget.safety_margin_tokens == 410
    assert budget.image_reserve_tokens == 0
    assert budget.max_input_tokens == 2662


def test_image_budget_reserves_1200_tokens_per_image():
    budget = build_token_budget(4096, image_count=1)

    assert budget.output_reserve_tokens == 1024
    assert budget.safety_margin_tokens == 410
    assert budget.image_reserve_tokens == 1200
    assert budget.max_input_tokens == 1462


def test_message_estimate_uses_utf8_bytes_and_fixed_overhead():
    assert estimate_messages_tokens([{"role": "user", "content": "你好a"}]) == 7


def test_trim_keeps_system_and_latest_user_without_mutating_input():
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "x" * 900},
        {"role": "assistant", "content": "y" * 900},
        {"role": "user", "content": "latest"},
    ]
    original = copy.deepcopy(messages)
    budget = build_token_budget(512)

    trimmed = trim_messages_to_budget(messages, budget)

    assert messages == original
    assert trimmed == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "latest"},
    ]


def test_trim_rebuilds_budget_after_removing_old_history_images():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "a" * 1500},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,old1"}},
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "b" * 1500},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,old2"}},
            ],
        },
        {"role": "user", "content": "n" * 3000},
    ]

    trimmed = trim_messages_to_budget(messages, build_token_budget(4096))

    assert trimmed == [{"role": "user", "content": "n" * 3000}]
    assert count_message_images(trimmed) == 0


def test_trim_keeps_all_system_messages():
    messages = [
        {"role": "system", "content": "primary rules"},
        {"role": "user", "content": "x" * 900},
        {"role": "system", "content": "secondary rules"},
        {"role": "assistant", "content": "y" * 900},
        {"role": "user", "content": "latest"},
    ]

    trimmed = trim_messages_to_budget(messages, build_token_budget(512))

    assert trimmed == [
        {"role": "system", "content": "primary rules"},
        {"role": "system", "content": "secondary rules"},
        {"role": "user", "content": "latest"},
    ]


def test_trim_classifies_multiple_system_messages_that_cannot_fit():
    messages = [
        {"role": "system", "content": "a" * 500},
        {"role": "system", "content": "b" * 500},
        {"role": "user", "content": "latest"},
    ]

    with pytest.raises(ContextBudgetExceededError) as exc_info:
        trim_messages_to_budget(messages, build_token_budget(512))

    assert exc_info.value.code == "context_budget_exceeded"
    assert exc_info.value.max_input_tokens == 256


def test_trim_removes_assistant_tool_call_and_results_as_one_group():
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "old question"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{}"},
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "read", "arguments": "{}"},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "x" * 900},
        {"role": "tool", "tool_call_id": "call_2", "content": "second result"},
        {"role": "assistant", "content": "tool synthesis"},
        {"role": "user", "content": "latest"},
    ]
    budget = build_token_budget(512)

    trimmed = trim_messages_to_budget(messages, budget)

    retained_call_ids = {
        call["id"]
        for message in trimmed
        for call in message.get("tool_calls", [])
    }
    retained_result_ids = {
        message["tool_call_id"]
        for message in trimmed
        if message.get("role") == "tool"
    }
    assert retained_call_ids == retained_result_ids
    assert "call_1" not in retained_call_ids
    assert trimmed[-1] == {"role": "user", "content": "latest"}


def _tool_call(call_id: str):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "lookup", "arguments": "{}"},
    }


@pytest.mark.parametrize(
    ("history", "retained_marker"),
    [
        (
            [
                {"role": "tool", "tool_call_id": "call_1", "content": "early"},
                {"role": "assistant", "content": None, "tool_calls": [_tool_call("call_1")]},
            ],
            None,
        ),
        (
            [
                {"role": "assistant", "content": None, "tool_calls": [_tool_call("call_1")]},
                {"role": "assistant", "content": "keep separator"},
                {"role": "tool", "tool_call_id": "call_1", "content": "late"},
            ],
            "keep separator",
        ),
        (
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [_tool_call("call_1"), _tool_call("call_1")],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": "once"},
            ],
            None,
        ),
        (
            [
                {"role": "assistant", "content": None, "tool_calls": [_tool_call("")]},
                {"role": "tool", "tool_call_id": "", "content": "empty id"},
            ],
            None,
        ),
        (
            [
                {"role": "assistant", "content": None, "tool_calls": [_tool_call("call_1")]},
                {"role": "tool", "tool_call_id": "call_1", "content": "expected"},
                {"role": "tool", "tool_call_id": "call_extra", "content": "extra"},
            ],
            None,
        ),
        (
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [_tool_call("call_1"), _tool_call("call_2")],
                },
                {"role": "tool", "tool_call_id": "call_2", "content": "wrong first"},
                {"role": "tool", "tool_call_id": "call_1", "content": "wrong second"},
            ],
            None,
        ),
        (
            [
                {"role": "assistant", "content": None, "tool_calls": [_tool_call("call_1")]},
                {"role": "tool", "tool_call_id": "call_1", "content": "first"},
                {"role": "tool", "tool_call_id": "call_1", "content": "duplicate"},
            ],
            None,
        ),
        (
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [_tool_call("call_1"), _tool_call("call_2")],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": "only one"},
            ],
            None,
        ),
    ],
    ids=[
        "result_before_call",
        "ordinary_message_separates_result",
        "duplicate_call_id",
        "duplicate_result",
        "mixed_group_missing_result",
        "empty_call_id",
        "extra_result",
        "results_out_of_order",
    ],
)
def test_trim_discards_invalid_tool_protocol_groups_without_deleting_normal_messages(
    history,
    retained_marker,
):
    messages = [*history, {"role": "user", "content": "latest"}]

    trimmed = trim_messages_to_budget(messages, build_token_budget(4096))

    assert all(not message.get("tool_calls") for message in trimmed)
    assert all(message.get("role") != "tool" for message in trimmed)
    if retained_marker:
        assert {"role": "assistant", "content": retained_marker} in trimmed
    assert trimmed[-1] == {"role": "user", "content": "latest"}


def test_trim_rejects_latest_user_that_cannot_fit():
    budget = build_token_budget(512)

    with pytest.raises(ContextBudgetExceededError, match="输入超过模型上下文") as exc_info:
        trim_messages_to_budget(
            [{"role": "user", "content": "x" * 1000}],
            budget,
        )

    assert exc_info.value.code == "context_budget_exceeded"
    assert exc_info.value.max_input_tokens == 256


def test_tools_schema_is_included_in_input_budget():
    budget = build_token_budget(512)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "x" * 1000,
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    with pytest.raises(ContextBudgetExceededError, match="输入超过模型上下文"):
        trim_messages_to_budget(
            [{"role": "user", "content": "latest"}],
            budget,
            tools=tools,
        )


def test_request_chunker_splits_when_token_budget_is_exceeded_below_byte_limit():
    segments = [{"text": "a" * 90}, {"text": "b" * 90}]
    chunker = RequestChunker(
        _message_builder,
        max_bytes=45 * 1024 * 1024,
        max_tokens=40,
        token_estimator=estimate_messages_tokens,
    )

    chunks = chunker.chunk(segments, [])

    assert len(chunks) == 2
    assert ["".join(item["text"] for item in chunk.segments) for chunk in chunks] == [
        "a" * 90,
        "b" * 90,
    ]


def test_request_chunker_still_splits_when_byte_budget_is_exceeded():
    segments = [{"text": "a" * 90}, {"text": "b" * 90}]
    single_size = len(json.dumps(_message_builder([segments[0]], [])).encode("utf-8"))
    both_size = len(json.dumps(_message_builder(segments, [])).encode("utf-8"))
    chunker = RequestChunker(
        _message_builder,
        max_bytes=(single_size + both_size) // 2,
        max_tokens=10_000,
        token_estimator=estimate_messages_tokens,
    )

    chunks = chunker.chunk(segments, [])

    assert len(chunks) >= 2


def test_request_chunker_reassembles_single_long_segment_without_empty_chunks():
    original = "甲a🙂" * 120
    max_bytes = 150
    max_tokens = 25
    chunker = RequestChunker(
        _message_builder,
        max_bytes=max_bytes,
        max_tokens=max_tokens,
        token_estimator=estimate_messages_tokens,
    )

    chunks = chunker.chunk([{"text": original}], [])

    texts = ["".join(segment["text"] for segment in chunk.segments) for chunk in chunks]
    assert "".join(texts) == original
    assert all(texts)
    for chunk in chunks:
        messages = _message_builder(chunk.segments, chunk.image_urls)
        assert len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) <= max_bytes
        assert estimate_messages_tokens(messages) <= max_tokens


def test_image_url_length_is_not_double_counted_as_text_tokens():
    short = [{"role": "user", "content": [
        {"type": "text", "text": "caption"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,a"}},
    ]}]
    long = copy.deepcopy(short)
    long[0]["content"][1]["image_url"]["url"] = "data:image/png;base64," + "z" * 100_000

    assert estimate_messages_tokens(short) == estimate_messages_tokens(long)
