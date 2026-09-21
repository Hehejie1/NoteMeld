"""Anthropic Messages 原生协议适配（notemeld.model-add.v1）

- list_models: 无公开模型列表端点，返回内置 3 模型目录，用户仍可手动添加
- test_connection: POST {base_url}/v1/messages
  header: x-api-key + anthropic-version: 2023-06-01
  body:   {model, max_tokens: 1, messages: [{role: 'user', content: 'ping'}]}
"""
from __future__ import annotations

from typing import Any, Dict, List

import httpx

from app.services.vendor_registry import (
    ANTHROPIC_BUILTIN_MODELS,
    trim_url,
)

TEST_TIMEOUT = 12.0
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicMessagesProvider:
    @staticmethod
    def list_models() -> List[Dict[str, Any]]:
        return [
            {"id": item["id"], "context_window": item["context_window"]}
            for item in ANTHROPIC_BUILTIN_MODELS
        ]

    @staticmethod
    def test_connection(api_key: str, base_url: str, model: str) -> bool:
        if not api_key:
            raise RuntimeError("请填写 API 密钥")
        if not model:
            raise RuntimeError("请选择或填写要测试的模型 ID")
        url = f"{trim_url(base_url)}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
            "x-api-key": api_key,
        }
        payload = {
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }
        try:
            with httpx.Client(timeout=TEST_TIMEOUT) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError:
            # 不回显状态码以外的请求细节，密钥不进日志
            return False
        except httpx.HTTPError:
            return False
        except ValueError:
            return False
        return bool(isinstance(data, dict) and (data.get("content") is not None or data.get("id")))
