from typing import Optional, Union

from openai import OpenAI
import httpx

from app.utils.logger import get_logger

logging = get_logger(__name__)


def _create_httpx_client(base_url: str) -> httpx.Client:
    """
    创建 httpx 客户端，根据 URL 判断是否禁用 HTTP/2。
    Ollama 等本地服务不支持 HTTP/2，需要禁用以避免 502 错误。
    """
    normalized_url = base_url.lower()
    # 本地服务（Ollama等）禁用 HTTP/2
    if "127.0.0.1:11434" in normalized_url or "localhost:11434" in normalized_url:
        transport = httpx.HTTPTransport(http2=False)
        return httpx.Client(transport=transport)
    return None


class OpenAICompatibleProvider:
    def __init__(self, api_key: str, base_url: str, model: Union[str, None] = None):
        httpx_client = _create_httpx_client(base_url)
        if httpx_client:
            self.client = OpenAI(api_key=api_key, base_url=base_url, http_client=httpx_client)
        else:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    @property
    def get_client(self):
        return self.client

    @staticmethod
    def test_connection(api_key: str, base_url: str) -> bool:
        try:
            httpx_client = _create_httpx_client(base_url)
            if httpx_client:
                client = OpenAI(api_key=api_key, base_url=base_url, http_client=httpx_client)
            else:
                client = OpenAI(api_key=api_key, base_url=base_url)
            model = client.models.list()
            logging.info("连通性测试成功")
            return True
        except Exception as e:
            logging.info(f"连通性测试失败：{e}")
            return False