"""
三端统一「添加模型」桌面端 registry（notemeld.model-add.v1）

与 docs/new-product/assets/model-vendor-registry.js 保持 1:1 语义：
  - PROTOCOLS / MODEL_VENDORS：协议枚举与内置厂商预设
  - validate_model_config：三端统一即时校验
  - build_share_payload / encode_share / decode_share：notemeld://model-add 分享载荷

分享载荷永不包含 API Key；解码端拒绝任何携带密钥字段的载荷，
并与 notemeld://pair?code= 配对码严格区分。
"""
from __future__ import annotations

import base64
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

SHARE_SCHEMA = "notemeld.model-add.v1"
SHARE_LINK_RE = re.compile(r"^notemeld://model-add\?d=([A-Za-z0-9_-]+)$")

DEFAULT_CONTEXT = 128000
CONTEXT_MIN = 512
CONTEXT_MAX = 4_000_000

# 协议枚举：bedrock、azure 为预留，v1 不支持直连
PROTOCOLS: List[Dict[str, Any]] = [
    {"id": "openai-compatible", "label": "OpenAI 兼容", "needs_key": True, "models_path": "/models", "test_kind": "chat"},
    {"id": "anthropic-messages", "label": "Anthropic / Claude", "needs_key": True, "models_path": None, "test_kind": "anthropic"},
    {"id": "ollama", "label": "本地 Ollama", "needs_key": False, "models_path": "/api/tags", "test_kind": "ollama"},
]

# base_url 为空表示官方公开地址待确认，选择后仍需用户补一次，不臆造
MODEL_VENDORS: List[Dict[str, Any]] = [
    {"id": "deepseek", "name": "DeepSeek", "protocol": "openai-compatible", "base_url": "https://api.deepseek.com", "icon": "bot"},
    {"id": "volcengine-ark", "name": "火山引擎", "protocol": "openai-compatible", "base_url": "https://ark.cn-beijing.volces.com/api/v3", "icon": "flame"},
    {"id": "volcengine-agent-plan", "name": "火山 Agent Plan", "protocol": "openai-compatible", "base_url": "https://ark.cn-beijing.volces.com/api/plan/v3", "icon": "flame"},
    {"id": "volcengine-coding-plan", "name": "火山 Coding Plan", "protocol": "openai-compatible", "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3", "icon": "flame"},
    {"id": "minimax-cn", "name": "MiniMax CN", "protocol": "openai-compatible", "base_url": "https://api.minimaxi.com/v1", "icon": "audio-lines"},
    {"id": "minimax-global", "name": "MiniMax Global", "protocol": "openai-compatible", "base_url": "https://api.minimax.io/v1", "icon": "audio-lines"},
    {"id": "bigmodel", "name": "Bigmodel", "protocol": "openai-compatible", "base_url": "https://open.bigmodel.cn/api/paas/v4", "icon": "sparkles"},
    {"id": "aliyun-bailian", "name": "阿里云", "protocol": "openai-compatible", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "icon": "cloud"},
    {"id": "xiaomi-mimo", "name": "Xiaomi MIMO", "protocol": "openai-compatible", "base_url": "", "icon": "smartphone", "url_note": "官方 OpenAI 兼容地址待确认，请按服务商文档填写"},
    {"id": "siliconflow", "name": "硅基流动", "protocol": "openai-compatible", "base_url": "https://api.siliconflow.cn/v1", "icon": "layers"},
    {"id": "zai", "name": "Z.ai", "protocol": "openai-compatible", "base_url": "https://api.z.ai/api/paas/v4", "icon": "sigma"},
    {"id": "openrouter", "name": "OpenRouter", "protocol": "openai-compatible", "base_url": "https://openrouter.ai/api/v1", "icon": "shuffle"},
    {"id": "kimi-cn", "name": "Kimi CN", "protocol": "openai-compatible", "base_url": "https://api.moonshot.cn/v1", "icon": "moon"},
    {"id": "kimi-global", "name": "Kimi Global", "protocol": "openai-compatible", "base_url": "https://api.moonshot.ai/v1", "icon": "moon"},
    {"id": "byteplus", "name": "BytePlus", "protocol": "openai-compatible", "base_url": "https://ark.mlp.bytepluses.com/api/v3", "icon": "zap"},
    {"id": "aws-bedrock", "name": "AWS", "protocol": "bedrock", "base_url": "", "icon": "server", "unsupported": "Bedrock 使用 SigV4 签名鉴权，v1 暂不支持直连，请通过 OpenAI 兼容网关接入"},
    {"id": "tencent-hunyuan", "name": "腾讯云", "protocol": "openai-compatible", "base_url": "https://api.hunyuan.cloud.tencent.com/v1", "icon": "message-circle"},
    {"id": "moli-fangzhou", "name": "模力方舟", "protocol": "openai-compatible", "base_url": "", "icon": "compass", "url_note": "官方兼容地址待确认，请按服务商文档填写"},
    {"id": "ppio", "name": "PPIO", "protocol": "openai-compatible", "base_url": "https://api.ppinfra.com/v1/openai", "icon": "radio"},
    {"id": "openai", "name": "OpenAI", "protocol": "openai-compatible", "base_url": "https://api.openai.com/v1", "icon": "globe"},
    {"id": "anthropic", "name": "Anthropic / Claude", "protocol": "anthropic-messages", "base_url": "https://api.anthropic.com", "icon": "brain-circuit"},
    {"id": "gemini", "name": "Google Gemini", "protocol": "openai-compatible", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "icon": "sparkle"},
    {"id": "ollama", "name": "本地 Ollama", "protocol": "ollama", "base_url": "http://localhost:11434", "icon": "hard-drive"},
    {"id": "custom", "name": "自定义", "protocol": "openai-compatible", "base_url": "", "icon": "settings-2", "custom": True},
]

# Anthropic 无标准公开模型列表接口，用内置常用目录兜底
ANTHROPIC_BUILTIN_MODELS: List[Dict[str, Any]] = [
    {"id": "claude-opus-4-1", "context_window": 200000},
    {"id": "claude-sonnet-4-5", "context_window": 200000},
    {"id": "claude-3-5-haiku-latest", "context_window": 200000},
]

_LOCAL_URL_RE = re.compile(r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(/|$)", re.IGNORECASE)
_TRAILING_SLASH_RE = re.compile(r"/+$")

# 解码后禁止出现的密钥相关字段（任何层级，大小写/命名风格均拦截）
_SECRET_FIELD_RE = re.compile(r"^(api[_-]?key|x[_-]?api[_-]?key|authorization|token|credential|secret)$", re.IGNORECASE)


def get_vendor(vendor_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not vendor_id:
        return None
    return next((v for v in MODEL_VENDORS if v["id"] == vendor_id), None)


def get_protocol(protocol_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not protocol_id:
        return None
    return next((p for p in PROTOCOLS if p["id"] == protocol_id), None)


def trim_url(url: Optional[str]) -> str:
    return _TRAILING_SLASH_RE.sub("", str(url or "").strip())


def is_local_url(url: str) -> bool:
    return bool(_LOCAL_URL_RE.match(url or ""))


def is_valid_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_model_config(data: Dict[str, Any]) -> Dict[str, str]:
    """三端统一即时校验；返回 {field: message}，空 dict 表示通过。"""
    errors: Dict[str, str] = {}
    display_name = str(data.get("display_name") or "").strip()
    protocol = data.get("protocol") or "openai-compatible"
    base_url = trim_url(data.get("base_url"))
    key = str(data.get("api_key") or "").strip()
    has_stored_key = bool(data.get("has_stored_key"))
    models = data.get("models") if isinstance(data.get("models"), list) else []

    if not display_name:
        errors["display_name"] = "请填写名称"
    if not base_url:
        errors["base_url"] = "请填写接口地址"
    elif not is_valid_http_url(base_url):
        errors["base_url"] = "地址格式不正确"
    elif not is_local_url(base_url) and not re.match(r"^https://", base_url, re.IGNORECASE):
        errors["base_url"] = "非本机地址必须使用 HTTPS"

    proto = get_protocol(protocol)
    if not proto:
        errors["protocol"] = "请选择协议类型"
    elif proto["needs_key"] and not key and not has_stored_key and protocol != "ollama":
        errors["api_key"] = "请填写 API 密钥"

    if not models:
        errors["models"] = "请至少选择或添加一个模型"
    for index, model in enumerate(models):
        raw_ctx = model.get("context_window") if isinstance(model, dict) else None
        if isinstance(raw_ctx, bool) or not isinstance(raw_ctx, int):
            errors[f"model_context:{index}"] = (
                f"「{model.get('id', index) if isinstance(model, dict) else index}」"
                f"上下文需为 {CONTEXT_MIN:,}–{CONTEXT_MAX:,} 的整数"
            )
        elif raw_ctx < CONTEXT_MIN or raw_ctx > CONTEXT_MAX:
            model_id = model.get("id", index) if isinstance(model, dict) else index
            errors[f"model_context:{index}"] = f"「{model_id}」上下文需为 {CONTEXT_MIN:,}–{CONTEXT_MAX:,} 的整数"

    duplicate_names = data.get("duplicate_names")
    if isinstance(duplicate_names, list) and duplicate_names:
        errors["models"] = f"模型已存在：{'、'.join(str(n) for n in duplicate_names)}，请勿重复添加"
    return errors


# ---------------------------------------------------------------------------
# 跨端分享：notemeld://model-add?d=<base64url(JSON)>，永不包含 API Key
# ---------------------------------------------------------------------------

def build_share_payload(*, vendor_id: Optional[str], display_name: str,
                        protocol: str, base_url: str,
                        models: List[Dict[str, Any]]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"s": SHARE_SCHEMA, "v": 1}
    vendor = get_vendor(vendor_id)
    if vendor and not vendor.get("custom") and vendor.get("protocol") != "bedrock":
        # 协议与 base_url 由接收端 registry 解析，保持二维码精简
        payload["vendor"] = vendor_id
    else:
        payload["vendor"] = "custom"
        payload["name"] = display_name
        payload["protocol"] = protocol
        payload["url"] = trim_url(base_url)
    payload["models"] = []
    for model in models or []:
        item: Dict[str, Any] = {"id": model["id"]}
        model_name = model.get("display_name")
        if model_name and model_name != model["id"]:
            item["n"] = model_name
        ctx = model.get("context_window")
        if ctx and ctx != DEFAULT_CONTEXT:
            item["c"] = ctx
        payload["models"].append(item)
    return payload


def encode_share(payload: Dict[str, Any]) -> str:
    # ensure_ascii=False 保留 Unicode 厂商/模型名，UTF-8 base64url
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"notemeld://model-add?d={encoded}"


def _contains_secret_fields(value: Any) -> bool:
    """递归检查载荷中是否夹带任何密钥字段。"""
    if isinstance(value, dict):
        for key, sub in value.items():
            if isinstance(key, str) and _SECRET_FIELD_RE.match(key.strip()):
                return True
            if _contains_secret_fields(sub):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_fields(item) for item in value)
    return False


def decode_share(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    解析分享文本为统一配置；非法、配对码、夹带密钥或 schema 不符一律返回 None。
    返回结构：{vendor_id, display_name, protocol, base_url, models: [{id, display_name, context_window}], imported: True}
    """
    raw = str(text or "").strip()
    if not raw:
        return None
    # 与配对码严格区分，显式拒绝
    if raw.startswith("notemeld://pair"):
        return None

    json_text = raw
    match = SHARE_LINK_RE.match(raw)
    if match:
        encoded = match.group(1).replace("-", "+").replace("_", "/")
        encoded += "=" * (-len(encoded) % 4)
        try:
            json_text = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None

    try:
        payload = json.loads(json_text)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("s") != SHARE_SCHEMA or not isinstance(payload.get("models"), list):
        return None
    # 安全红线：任何密钥字段都拒绝导入
    if _contains_secret_fields(payload):
        return None

    normalized_models: List[Dict[str, Any]] = []
    for item in payload["models"]:
        if not isinstance(item, dict) or not item.get("id"):
            return None
        ctx = item.get("c", DEFAULT_CONTEXT)
        if not isinstance(ctx, int) or isinstance(ctx, bool) or ctx < CONTEXT_MIN or ctx > CONTEXT_MAX:
            return None
        normalized_models.append({
            "id": str(item["id"]),
            "display_name": str(item.get("n") or item["id"]),
            "context_window": ctx,
        })
    if not normalized_models:
        return None

    vendor = get_vendor(payload.get("vendor"))
    if payload.get("vendor") and payload["vendor"] != "custom" and vendor and not vendor.get("custom"):
        # Bedrock 等预留/不支持协议即使伪造为预设厂商载荷也拒绝导入
        if vendor.get("protocol") == "bedrock" or vendor.get("unsupported"):
            return None
        return {
            "vendor_id": vendor["id"],
            "display_name": vendor["name"],
            "protocol": vendor["protocol"],
            "base_url": vendor["base_url"],
            "models": normalized_models,
            "imported": True,
        }
    protocol = payload.get("protocol") or "openai-compatible"
    if not get_protocol(protocol) or protocol == "bedrock":
        return None
    return {
        "vendor_id": "custom",
        "display_name": str(payload.get("name") or ""),
        "protocol": protocol,
        "base_url": str(payload.get("url") or ""),
        "models": normalized_models,
        "imported": True,
    }
