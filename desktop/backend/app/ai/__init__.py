"""notemeld-ai: 统一 LLM Provider 抽象与 Token 统计。

对外暴露 Models 集合、Provider 抽象、Tool/Type schema、Stream 事件、Usage 收集器和标准化异常。

使用示例::

    from app.ai import create_models, Type, Tool

    models = create_models()
    model = models.get_model(provider_id="prov_123", model_name="deepseek-chat")

    tools = [Tool(
        name="lookup_transcript",
        description="查询视频转写片段",
        parameters=Type.Object({
            "task_id": Type.String(),
            "keyword": Type.Optional(Type.String()),
        }),
    )]

    async for event in models.stream(model, ctx, options={"usage_context": {...}}):
        ...
"""

from app.ai.errors import (
    ProviderError,
    ProviderAuthError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderCapabilityError,
)
from app.ai.tool import Type, Tool
from app.ai.stream import StreamEvent, StreamEventType, CompleteResult
from app.ai.usage import Usage, UsageContext, UsageCost, UsageWriter
from app.ai.provider import (
    Provider,
    ProviderConfig,
    LLMContext,
    OpenAICompatibleProvider,
)
from app.ai.catalog import ModelCapabilities, CapabilityCatalog

__all__ = [
    # Type schema
    "Type",
    "Tool",
    # Errors
    "ProviderError",
    "ProviderAuthError",
    "ProviderNetworkError",
    "ProviderRateLimitError",
    "ProviderCapabilityError",
    # Stream
    "StreamEvent",
    "StreamEventType",
    "CompleteResult",
    # Usage
    "Usage",
    "UsageContext",
    "UsageCost",
    "UsageWriter",
    # Provider
    "Provider",
    "ProviderConfig",
    "LLMContext",
    "OpenAICompatibleProvider",
    # Catalog
    "ModelCapabilities",
    "CapabilityCatalog",
    # Factory
    "create_models",
]


def create_models():
    """创建 Models 集合实例（延迟导入避免循环依赖）。

    内部使用 ModelService 读取 providers/models/model_capabilities 表。
    """
    from app.ai.models import Models
    from app.services.model import ModelService

    return Models(model_service=ModelService)
