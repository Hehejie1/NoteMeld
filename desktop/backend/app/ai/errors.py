"""notemeld-ai 标准化异常分类。

所有 Provider 层的异常都映射到这些类型，上层可以分类处理：
- ProviderAuthError: API Key 缺失/失效，401/403
- ProviderNetworkError: 超时、连接重置、DNS 失败
- ProviderRateLimitError: 429 限流
- ProviderCapabilityError: 模型不支持 tools/vision/thinking 等能力
"""

from __future__ import annotations


class ProviderError(Exception):
    """Provider 层异常基类。"""

    def __init__(self, message: str, *, provider_id: str | None = None, model_name: str | None = None):
        super().__init__(message)
        self.provider_id = provider_id
        self.model_name = model_name


class ProviderAuthError(ProviderError):
    """API Key 缺失、失效，或 provider 返回 401/403。"""

    def __init__(self, message: str, *, provider_id: str | None = None, model_name: str | None = None):
        super().__init__(message, provider_id=provider_id, model_name=model_name)


class ProviderNetworkError(ProviderError):
    """超时、连接重置、DNS 失败等网络问题。"""

    def __init__(self, message: str, *, provider_id: str | None = None, model_name: str | None = None, cause: Exception | None = None):
        super().__init__(message, provider_id=provider_id, model_name=model_name)
        self.__cause__ = cause


class ProviderRateLimitError(ProviderError):
    """Provider 返回 429 限流。"""

    def __init__(self, message: str, *, provider_id: str | None = None, model_name: str | None = None):
        super().__init__(message, provider_id=provider_id, model_name=model_name)


class ProviderCapabilityError(ProviderError):
    """模型不支持请求的能力（tools/vision/thinking 等）。

    error_message 中包含 model id + capability 缺失类型，方便上层定位。
    """

    def __init__(self, message: str, *, provider_id: str | None = None, model_name: str | None = None, capability: str | None = None):
        super().__init__(message, provider_id=provider_id, model_name=model_name)
        self.capability = capability
