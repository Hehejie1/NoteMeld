import warnings

from openai import OpenAI

from app.gpt.base import GPT
from app.gpt.provider.OpenAI_compatible_provider import OpenAICompatibleProvider
from app.gpt.universal_gpt import UniversalGPT
from app.models.model_config import ModelConfig


class GPTFactory:
    """旧 GPT 工厂，过渡期保留供回滚和非 chat-completion 路径使用。

    迁移说明（notemeld-ai 抽象层，P0）：
    - 所有 chat-completion 调用点已切到 ``app.gpt.notemeld_gpt.NotemeldGPT``
      （继承 ``UniversalGPT``，override ``create_chat_completion`` 走 notemeld-ai）。
    - ``model.py`` 的 ``list_models`` 仍走 ``GPTFactory``（非 chat-completion 路径，
      未迁移，刻意保留）。
    - 至少保留 1 个 Beta 版本不删除，便于回滚。新代码请优先使用
      ``NotemeldGPT.from_config``。
    """

    @staticmethod
    def from_config(config: ModelConfig) -> GPT:
        warnings.warn(
            "GPTFactory.from_config 已进入过渡期：chat-completion 路径请改用 "
            "app.gpt.notemeld_gpt.NotemeldGPT.from_config（走 notemeld-ai 抽象层）。"
            "model.py 的 list_models 路径仍可在过渡期内继续使用本工厂。"
            "至少保留 1 个 Beta 版本后删除。",
            DeprecationWarning,
            stacklevel=2,
        )
        client = OpenAICompatibleProvider(api_key=config.api_key, base_url=config.base_url).get_client
        return UniversalGPT(
            client=client,
            model=config.model_name,
            usage_context=config.usage_context or {},
            provider_id=config.provider,
            provider_name=config.name,
            base_url=config.base_url,
        )
