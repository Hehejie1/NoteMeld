"""模型能力 catalog：从 ``model_capabilities`` 表加载能力声明。

复用现有 ``ModelCapabilityService.get()`` 读取能力，不修改探测逻辑。

能力维度：
- ``supports_json_mode``: 是否支持 ``response_format={"type": "json_object"}``
- ``supports_vision``: 是否支持图片输入
- ``tool_calling``: 是否支持 function calling（本期从 catalog 声明，探测逻辑不动）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.model_capability import ModelCapabilityService


@dataclass
class ModelCapabilities:
    """模型能力声明。

    所有字段为 ``None`` 表示未知（未探测过），调用方需容错。
    """

    supports_json_mode: Optional[bool] = None
    supports_vision: Optional[bool] = None
    supports_tool_calling: Optional[bool] = None
    raw: dict | None = None

    @staticmethod
    def from_dict(data: dict | None) -> ModelCapabilities:
        if not data:
            return ModelCapabilities()
        return ModelCapabilities(
            supports_json_mode=data.get("supports_json_mode"),
            supports_vision=data.get("supports_vision"),
            supports_tool_calling=data.get("supports_tool_calling"),
            raw=data,
        )

    def with_saved_vision(self, supports_vision: bool) -> ModelCapabilities:
        """返回以用户保存值为 vision 权威的能力快照。

        ``model_capabilities`` 是探测缓存，可以与用户确认的运行配置不同；
        运行时不得用探测的 ``true`` 覆盖保存的 ``false``。
        """
        return ModelCapabilities(
            supports_json_mode=self.supports_json_mode,
            supports_vision=bool(supports_vision),
            supports_tool_calling=self.supports_tool_calling,
            raw=self.raw,
        )


class CapabilityCatalog:
    """能力 catalog，从 ``model_capabilities`` 表加载。

    只读，不触发探测。探测逻辑保留在 ``ModelCapabilityService`` 中不动。
    """

    @staticmethod
    def get(provider_id: str, model_name: str) -> ModelCapabilities:
        """读取模型能力声明。

        Args:
            provider_id: provider 表主键。
            model_name: 模型名称。

        Returns:
            ModelCapabilities 对象，未探测过的字段为 None。
        """
        data = ModelCapabilityService.get(provider_id, model_name)
        return ModelCapabilities.from_dict(data)
