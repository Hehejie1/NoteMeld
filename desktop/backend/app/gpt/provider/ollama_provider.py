"""Ollama 本地协议适配（notemeld.model-add.v1）

- list_models: GET {base_url}/api/tags
- test_connection: 同端点（免 Key）
本地服务不支持 HTTP/2，统一关闭。
"""
from __future__ import annotations

from typing import Any, Dict, List

import httpx

from app.services.vendor_registry import DEFAULT_CONTEXT, trim_url

LIST_TIMEOUT = 8.0
TEST_TIMEOUT = 12.0


def _client(timeout: float) -> httpx.Client:
    return httpx.Client(timeout=timeout, http2=False)


class OllamaProvider:
    @staticmethod
    def list_models(base_url: str) -> List[Dict[str, Any]]:
        url = f"{trim_url(base_url)}/api/tags"
        try:
            with _client(LIST_TIMEOUT) as client:
                resp = client.get(url, headers={"Accept": "application/json"})
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"获取模型列表失败（HTTP {exc.response.status_code}）") from None
        except httpx.HTTPError as exc:
            raise RuntimeError("无法连接本地 Ollama 服务，请确认服务已启动且地址正确") from None
        except ValueError:
            raise RuntimeError("Ollama 返回内容不是有效 JSON") from None

        raw_models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(raw_models, list) or not raw_models:
            raise RuntimeError("未获取到模型，请先在 Ollama 中拉取模型")
        result: List[Dict[str, Any]] = []
        for item in raw_models:
            model_id = item.get("name") if isinstance(item, dict) else None
            if model_id:
                result.append({"id": str(model_id), "context_window": DEFAULT_CONTEXT})
        if not result:
            raise RuntimeError("未获取到模型，请先在 Ollama 中拉取模型")
        return result

    @staticmethod
    def test_connection(base_url: str) -> bool:
        url = f"{trim_url(base_url)}/api/tags"
        try:
            with _client(TEST_TIMEOUT) as client:
                resp = client.get(url, headers={"Accept": "application/json"})
                resp.raise_for_status()
        except httpx.HTTPError:
            return False
        return True
