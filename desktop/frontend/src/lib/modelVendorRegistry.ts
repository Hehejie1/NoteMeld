/**
 * 三端统一「添加模型」桌面前端 registry（notemeld.model-add.v1）
 *
 * 与 desktop/backend/app/services/vendor_registry.py 及
 * docs/new-product/assets/model-vendor-registry.js 保持 1:1 语义：
 *  - PROTOCOLS / MODEL_VENDORS：协议枚举与内置厂商预设
 *  - validateModelConfig：三端统一即时校验
 *  - buildSharePayload / encodeShare / decodeShare：notemeld://model-add 分享载荷
 *
 * 分享载荷永不包含 API Key；解码端拒绝任何携带密钥字段的载荷，
 * 并与 notemeld://pair?code= 配对码严格区分。
 */

export const SHARE_SCHEMA = 'notemeld.model-add.v1';

export const DEFAULT_CONTEXT = 128000;
export const CONTEXT_MIN = 512;
export const CONTEXT_MAX = 4_000_000;

export type ProtocolId = 'openai-compatible' | 'anthropic-messages' | 'ollama';

export interface ModelProtocol {
  id: ProtocolId;
  label: string;
  needs_key: boolean;
  models_path: string | null;
  test_kind: 'chat' | 'anthropic' | 'ollama';
}

export interface ModelVendor {
  id: string;
  name: string;
  protocol: string;
  base_url: string;
  icon: string;
  url_note?: string;
  unsupported?: string;
  custom?: boolean;
}

export interface ShareModelInput {
  id: string;
  display_name?: string | null;
  context_window?: number | null;
}

export interface DecodedModel {
  id: string;
  display_name: string;
  context_window: number;
}

export interface DecodedShare {
  vendor_id: string;
  display_name: string;
  protocol: string;
  base_url: string;
  models: DecodedModel[];
  imported: true;
}

// 协议枚举：bedrock、azure 为预留，v1 不支持直连
export const PROTOCOLS: ModelProtocol[] = [
  { id: 'openai-compatible', label: 'OpenAI 兼容', needs_key: true, models_path: '/models', test_kind: 'chat' },
  { id: 'anthropic-messages', label: 'Anthropic / Claude', needs_key: true, models_path: null, test_kind: 'anthropic' },
  { id: 'ollama', label: '本地 Ollama', needs_key: false, models_path: '/api/tags', test_kind: 'ollama' },
];

// base_url 为空表示官方公开地址待确认，选择后仍需用户补一次，不臆造
export const MODEL_VENDORS: ModelVendor[] = [
  { id: 'deepseek', name: 'DeepSeek', protocol: 'openai-compatible', base_url: 'https://api.deepseek.com', icon: 'bot' },
  { id: 'volcengine-ark', name: '火山引擎', protocol: 'openai-compatible', base_url: 'https://ark.cn-beijing.volces.com/api/v3', icon: 'flame' },
  { id: 'volcengine-agent-plan', name: '火山 Agent Plan', protocol: 'openai-compatible', base_url: 'https://ark.cn-beijing.volces.com/api/plan/v3', icon: 'flame' },
  { id: 'volcengine-coding-plan', name: '火山 Coding Plan', protocol: 'openai-compatible', base_url: 'https://ark.cn-beijing.volces.com/api/coding/v3', icon: 'flame' },
  { id: 'minimax-cn', name: 'MiniMax CN', protocol: 'openai-compatible', base_url: 'https://api.minimaxi.com/v1', icon: 'audio-lines' },
  { id: 'minimax-global', name: 'MiniMax Global', protocol: 'openai-compatible', base_url: 'https://api.minimax.io/v1', icon: 'audio-lines' },
  { id: 'bigmodel', name: 'Bigmodel', protocol: 'openai-compatible', base_url: 'https://open.bigmodel.cn/api/paas/v4', icon: 'sparkles' },
  { id: 'aliyun-bailian', name: '阿里云', protocol: 'openai-compatible', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', icon: 'cloud' },
  { id: 'xiaomi-mimo', name: 'Xiaomi MIMO', protocol: 'openai-compatible', base_url: '', icon: 'smartphone', url_note: '官方 OpenAI 兼容地址待确认，请按服务商文档填写' },
  { id: 'siliconflow', name: '硅基流动', protocol: 'openai-compatible', base_url: 'https://api.siliconflow.cn/v1', icon: 'layers' },
  { id: 'zai', name: 'Z.ai', protocol: 'openai-compatible', base_url: 'https://api.z.ai/api/paas/v4', icon: 'sigma' },
  { id: 'openrouter', name: 'OpenRouter', protocol: 'openai-compatible', base_url: 'https://openrouter.ai/api/v1', icon: 'shuffle' },
  { id: 'kimi-cn', name: 'Kimi CN', protocol: 'openai-compatible', base_url: 'https://api.moonshot.cn/v1', icon: 'moon' },
  { id: 'kimi-global', name: 'Kimi Global', protocol: 'openai-compatible', base_url: 'https://api.moonshot.ai/v1', icon: 'moon' },
  { id: 'byteplus', name: 'BytePlus', protocol: 'openai-compatible', base_url: 'https://ark.mlp.bytepluses.com/api/v3', icon: 'zap' },
  { id: 'aws-bedrock', name: 'AWS', protocol: 'bedrock', base_url: '', icon: 'server', unsupported: 'Bedrock 使用 SigV4 签名鉴权，v1 暂不支持直连，请通过 OpenAI 兼容网关接入' },
  { id: 'tencent-hunyuan', name: '腾讯云', protocol: 'openai-compatible', base_url: 'https://api.hunyuan.cloud.tencent.com/v1', icon: 'message-circle' },
  { id: 'moli-fangzhou', name: '模力方舟', protocol: 'openai-compatible', base_url: '', icon: 'compass', url_note: '官方兼容地址待确认，请按服务商文档填写' },
  { id: 'ppio', name: 'PPIO', protocol: 'openai-compatible', base_url: 'https://api.ppinfra.com/v1/openai', icon: 'radio' },
  { id: 'openai', name: 'OpenAI', protocol: 'openai-compatible', base_url: 'https://api.openai.com/v1', icon: 'globe' },
  { id: 'anthropic', name: 'Anthropic / Claude', protocol: 'anthropic-messages', base_url: 'https://api.anthropic.com', icon: 'brain-circuit' },
  { id: 'gemini', name: 'Google Gemini', protocol: 'openai-compatible', base_url: 'https://generativelanguage.googleapis.com/v1beta/openai/', icon: 'sparkle' },
  { id: 'ollama', name: '本地 Ollama', protocol: 'ollama', base_url: 'http://localhost:11434', icon: 'hard-drive' },
  { id: 'custom', name: '自定义', protocol: 'openai-compatible', base_url: '', icon: 'settings-2', custom: true },
];

// Anthropic 无标准公开模型列表接口，用内置常用目录兜底
export const ANTHROPIC_BUILTIN_MODELS: Array<{ id: string; context_window: number }> = [
  { id: 'claude-opus-4-1', context_window: 200000 },
  { id: 'claude-sonnet-4-5', context_window: 200000 },
  { id: 'claude-3-5-haiku-latest', context_window: 200000 },
];

const LOCAL_URL_RE = /^http:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(\/|$)/i;
const TRAILING_SLASH_RE = /\/+$/;
const SHARE_LINK_RE = /^notemeld:\/\/model-add\?d=([A-Za-z0-9_-]+)$/;

// 解码后禁止出现的密钥相关字段（任何层级，大小写/命名风格均拦截）
const SECRET_FIELD_RE = /^(api[_-]?key|x[_-]?api[_-]?key|authorization|token|credential|secret)$/i;

export function getVendor(vendorId?: string | null): ModelVendor | undefined {
  if (!vendorId) return undefined;
  return MODEL_VENDORS.find((v) => v.id === vendorId);
}

export function getProtocol(protocolId?: string | null): ModelProtocol | undefined {
  if (!protocolId) return undefined;
  return PROTOCOLS.find((p) => p.id === protocolId);
}

export function trimUrl(url?: string | null): string {
  return String(url ?? '').trim().replace(TRAILING_SLASH_RE, '');
}

export function isLocalUrl(url: string): boolean {
  return LOCAL_URL_RE.test(url ?? '');
}

export function isValidHttpUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return (parsed.protocol === 'http:' || parsed.protocol === 'https:') && Boolean(parsed.host);
  } catch {
    return false;
  }
}

export interface ValidateModelInput {
  display_name?: string | null;
  protocol?: string | null;
  base_url?: string | null;
  api_key?: string | null;
  has_stored_key?: boolean;
  models?: unknown;
  duplicate_names?: unknown;
}

/** 三端统一即时校验；返回 {field: message}，空对象表示通过。 */
export function validateModelConfig(data: ValidateModelInput): Record<string, string> {
  const errors: Record<string, string> = {};
  const displayName = String(data.display_name ?? '').trim();
  const protocol = data.protocol || 'openai-compatible';
  const baseUrl = trimUrl(data.base_url);
  const key = String(data.api_key ?? '').trim();
  const hasStoredKey = Boolean(data.has_stored_key);
  const models = Array.isArray(data.models) ? data.models : [];

  if (!displayName) errors.display_name = '请填写名称';
  if (!baseUrl) {
    errors.base_url = '请填写接口地址';
  } else if (!isValidHttpUrl(baseUrl)) {
    errors.base_url = '地址格式不正确';
  } else if (!isLocalUrl(baseUrl) && !/^https:\/\//i.test(baseUrl)) {
    errors.base_url = '非本机地址必须使用 HTTPS';
  }

  const proto = getProtocol(protocol);
  if (!proto) {
    errors.protocol = '请选择协议类型';
  } else if (proto.needs_key && !key && !hasStoredKey && protocol !== 'ollama') {
    errors.api_key = '请填写 API 密钥';
  }

  if (!models.length) errors.models = '请至少选择或添加一个模型';
  models.forEach((model, index) => {
    const item = (model && typeof model === 'object' ? model : {}) as Record<string, unknown>;
    const rawCtx = item.context_window;
    const modelId = (item.id as string) ?? index;
    if (typeof rawCtx !== 'number' || typeof rawCtx === 'boolean') {
      errors[`model_context:${index}`] = `「${modelId}」上下文需为 ${CONTEXT_MIN.toLocaleString()}–${CONTEXT_MAX.toLocaleString()} 的整数`;
    } else if (rawCtx < CONTEXT_MIN || rawCtx > CONTEXT_MAX) {
      errors[`model_context:${index}`] = `「${modelId}」上下文需为 ${CONTEXT_MIN.toLocaleString()}–${CONTEXT_MAX.toLocaleString()} 的整数`;
    }
  });

  if (Array.isArray(data.duplicate_names) && data.duplicate_names.length) {
    errors.models = `模型已存在：${data.duplicate_names.map(String).join('、')}，请勿重复添加`;
  }
  return errors;
}

// ---------------------------------------------------------------------------
// 跨端分享：notemeld://model-add?d=<base64url(JSON)>，永不包含 API Key
// ---------------------------------------------------------------------------

export function buildSharePayload(input: {
  vendor_id?: string | null;
  display_name: string;
  protocol: string;
  base_url: string;
  models: ShareModelInput[];
}): Record<string, unknown> {
  const payload: Record<string, unknown> = { s: SHARE_SCHEMA, v: 1 };
  const vendor = getVendor(input.vendor_id);
  if (vendor && !vendor.custom && vendor.protocol !== 'bedrock') {
    // 协议与 base_url 由接收端 registry 解析，保持二维码精简
    payload.vendor = input.vendor_id;
  } else {
    payload.vendor = 'custom';
    payload.name = input.display_name;
    payload.protocol = input.protocol;
    payload.url = trimUrl(input.base_url);
  }
  payload.models = (input.models ?? []).map((model) => {
    const item: Record<string, unknown> = { id: model.id };
    if (model.display_name && model.display_name !== model.id) item.n = model.display_name;
    if (model.context_window && model.context_window !== DEFAULT_CONTEXT) item.c = model.context_window;
    return item;
  });
  return payload;
}

export function encodeShare(payload: Record<string, unknown>): string {
  // 保留 Unicode 厂商/模型名，UTF-8 base64url
  const raw = JSON.stringify(payload);
  const b64 = btoa(unescape(encodeURIComponent(raw)));
  const encoded = b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `notemeld://model-add?d=${encoded}`;
}

function containsSecretFields(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(containsSecretFields);
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).some(
      ([k, v]) => SECRET_FIELD_RE.test(k.trim()) || containsSecretFields(v),
    );
  }
  return false;
}

/**
 * 解析分享文本为统一配置；非法、配对码、夹带密钥或 schema 不符一律返回 null。
 */
export function decodeShare(text?: string | null): DecodedShare | null {
  const raw = String(text ?? '').trim();
  if (!raw) return null;
  // 与配对码严格区分，显式拒绝
  if (raw.startsWith('notemeld://pair')) return null;

  let jsonText = raw;
  const match = SHARE_LINK_RE.exec(raw);
  if (match) {
    try {
      let encoded = match[1].replace(/-/g, '+').replace(/_/g, '/');
      encoded += '='.repeat((4 - (encoded.length % 4)) % 4);
      jsonText = decodeURIComponent(escape(atob(encoded)));
    } catch {
      return null;
    }
  }

  let payload: unknown;
  try {
    payload = JSON.parse(jsonText);
  } catch {
    return null;
  }
  if (!payload || typeof payload !== 'object') return null;
  const obj = payload as Record<string, unknown>;
  if (obj.s !== SHARE_SCHEMA || !Array.isArray(obj.models)) return null;
  // 安全红线：任何密钥字段都拒绝导入
  if (containsSecretFields(obj)) return null;

  const normalizedModels: DecodedModel[] = [];
  for (const entry of obj.models as unknown[]) {
    if (!entry || typeof entry !== 'object') return null;
    const item = entry as Record<string, unknown>;
    if (!item.id) return null;
    const ctx = (item.c ?? DEFAULT_CONTEXT) as number;
    if (typeof ctx !== 'number' || typeof ctx === 'boolean' || ctx < CONTEXT_MIN || ctx > CONTEXT_MAX) {
      return null;
    }
    normalizedModels.push({
      id: String(item.id),
      display_name: String(item.n ?? item.id),
      context_window: ctx,
    });
  }
  if (!normalizedModels.length) return null;

  const vendorId = obj.vendor as string | undefined;
  const vendor = getVendor(vendorId);
  if (vendorId && vendorId !== 'custom' && vendor && !vendor.custom) {
    // Bedrock 等预留/不支持协议即使伪造为预设厂商载荷也拒绝导入
    if (vendor.protocol === 'bedrock' || vendor.unsupported) return null;
    return {
      vendor_id: vendor.id,
      display_name: vendor.name,
      protocol: vendor.protocol,
      base_url: vendor.base_url,
      models: normalizedModels,
      imported: true,
    };
  }
  const protocol = (obj.protocol as string) || 'openai-compatible';
  if (!getProtocol(protocol) || protocol === 'bedrock') return null;
  return {
    vendor_id: 'custom',
    display_name: String(obj.name ?? ''),
    protocol,
    base_url: String(obj.url ?? ''),
    models: normalizedModels,
    imported: true,
  };
}
