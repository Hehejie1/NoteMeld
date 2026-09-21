/*
 * NoteMeld 三端统一「添加模型」共享资产（原型）
 * D09 / C06 / M07 共同引用：
 *  - MODEL_VENDORS：内置厂商预设目录（选厂商自动带出协议与 Base URL）
 *  - ModelProtocol：按协议拉取模型列表 / 最小请求测试
 *  - validateModelConfig：三端统一即时校验
 *  - ModelShare：notemeld://model-add 分享载荷（二维码 / 复制 JSON），永不包含 API Key
 * 详见 config/feature-registry.json 的 model-config-contract。
 */
(function () {
  'use strict';

  // 协议枚举：OpenAI 兼容 / Anthropic 原生 / 本地 Ollama；bedrock、azure 为预留
  const PROTOCOLS = [
    { id: 'openai-compatible', label: 'OpenAI 兼容', needsKey: true, modelsPath: '/models', testKind: 'chat' },
    { id: 'anthropic-messages', label: 'Anthropic / Claude', needsKey: true, modelsPath: null, testKind: 'anthropic' },
    { id: 'ollama', label: '本地 Ollama', needsKey: false, modelsPath: '/api/tags', testKind: 'ollama' }
  ];

  // base_url 为空表示官方公开地址待确认，选择后仍需用户补一次，不臆造
  const MODEL_VENDORS = [
    { id: 'deepseek', name: 'DeepSeek', protocol: 'openai-compatible', baseUrl: 'https://api.deepseek.com', icon: 'bot' },
    { id: 'volcengine-ark', name: '火山引擎', protocol: 'openai-compatible', baseUrl: 'https://ark.cn-beijing.volces.com/api/v3', icon: 'flame' },
    { id: 'volcengine-agent-plan', name: '火山 Agent Plan', protocol: 'openai-compatible', baseUrl: 'https://ark.cn-beijing.volces.com/api/plan/v3', icon: 'flame' },
    { id: 'volcengine-coding-plan', name: '火山 Coding Plan', protocol: 'openai-compatible', baseUrl: 'https://ark.cn-beijing.volces.com/api/coding/v3', icon: 'flame' },
    { id: 'minimax-cn', name: 'MiniMax CN', protocol: 'openai-compatible', baseUrl: 'https://api.minimaxi.com/v1', icon: 'audio-lines' },
    { id: 'minimax-global', name: 'MiniMax Global', protocol: 'openai-compatible', baseUrl: 'https://api.minimax.io/v1', icon: 'audio-lines' },
    { id: 'bigmodel', name: 'Bigmodel', protocol: 'openai-compatible', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', icon: 'sparkles' },
    { id: 'aliyun-bailian', name: '阿里云', protocol: 'openai-compatible', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', icon: 'cloud' },
    { id: 'xiaomi-mimo', name: 'Xiaomi MIMO', protocol: 'openai-compatible', baseUrl: '', icon: 'smartphone', urlNote: '官方 OpenAI 兼容地址待确认，请按服务商文档填写' },
    { id: 'siliconflow', name: '硅基流动', protocol: 'openai-compatible', baseUrl: 'https://api.siliconflow.cn/v1', icon: 'layers' },
    { id: 'zai', name: 'Z.ai', protocol: 'openai-compatible', baseUrl: 'https://api.z.ai/api/paas/v4', icon: 'sigma' },
    { id: 'openrouter', name: 'OpenRouter', protocol: 'openai-compatible', baseUrl: 'https://openrouter.ai/api/v1', icon: 'shuffle' },
    { id: 'kimi-cn', name: 'Kimi CN', protocol: 'openai-compatible', baseUrl: 'https://api.moonshot.cn/v1', icon: 'moon' },
    { id: 'kimi-global', name: 'Kimi Global', protocol: 'openai-compatible', baseUrl: 'https://api.moonshot.ai/v1', icon: 'moon' },
    { id: 'byteplus', name: 'BytePlus', protocol: 'openai-compatible', baseUrl: 'https://ark.mlp.bytepluses.com/api/v3', icon: 'zap' },
    { id: 'aws-bedrock', name: 'AWS', protocol: 'bedrock', baseUrl: '', icon: 'server', unsupported: 'Bedrock 使用 SigV4 签名鉴权，v1 暂不支持直连，请通过 OpenAI 兼容网关接入' },
    { id: 'tencent-hunyuan', name: '腾讯云', protocol: 'openai-compatible', baseUrl: 'https://api.hunyuan.cloud.tencent.com/v1', icon: 'message-circle' },
    { id: 'moli-fangzhou', name: '模力方舟', protocol: 'openai-compatible', baseUrl: '', icon: 'compass', urlNote: '官方兼容地址待确认，请按服务商文档填写' },
    { id: 'ppio', name: 'PPIO', protocol: 'openai-compatible', baseUrl: 'https://api.ppinfra.com/v1/openai', icon: 'radio' },
    { id: 'openai', name: 'OpenAI', protocol: 'openai-compatible', baseUrl: 'https://api.openai.com/v1', icon: 'globe' },
    { id: 'anthropic', name: 'Anthropic / Claude', protocol: 'anthropic-messages', baseUrl: 'https://api.anthropic.com', icon: 'brain-circuit' },
    { id: 'gemini', name: 'Google Gemini', protocol: 'openai-compatible', baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai/', icon: 'sparkle' },
    { id: 'ollama', name: '本地 Ollama', protocol: 'ollama', baseUrl: 'http://localhost:11434', icon: 'hard-drive' },
    { id: 'custom', name: '自定义', protocol: 'openai-compatible', baseUrl: '', icon: 'settings-2', custom: true }
  ];

  // Anthropic 无标准公开模型列表接口，用内置常用目录兜底
  const ANTHROPIC_BUILTIN_MODELS = [
    { id: 'claude-opus-4-1', contextWindow: 200000 },
    { id: 'claude-sonnet-4-5', contextWindow: 200000 },
    { id: 'claude-3-5-haiku-latest', contextWindow: 200000 }
  ];

  const DEFAULT_CONTEXT = 128000;
  const CONTEXT_MIN = 512;
  const CONTEXT_MAX = 4000000;

  const getVendor = id => MODEL_VENDORS.find(v => v.id === id) || null;
  const getProtocol = id => PROTOCOLS.find(p => p.id === id) || null;
  const trimUrl = url => String(url || '').trim().replace(/\/+$/, '');
  const isLocalUrl = url => /^http:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(\/|$)/i.test(url);
  const isValidHttpUrl = url => {
    try { const u = new URL(url); return u.protocol === 'http:' || u.protocol === 'https:'; }
    catch { return false; }
  };

  // 三端统一即时校验；返回 { field: message }，空对象表示通过
  function validateModelConfig(input) {
    const errors = {};
    const displayName = (input.displayName || '').trim();
    const vendorId = input.vendorId || 'custom';
    const protocol = input.protocol || 'openai-compatible';
    const baseUrl = trimUrl(input.baseUrl);
    const key = (input.apiKey || '').trim();
    const hasStoredKey = !!input.hasStoredKey; // 编辑态已保存密钥、留空保留
    const models = Array.isArray(input.models) ? input.models : [];

    if (!displayName) errors.displayName = '请填写名称';
    if (!baseUrl) errors.baseUrl = '请填写接口地址';
    else if (!isValidHttpUrl(baseUrl)) errors.baseUrl = '地址格式不正确';
    else if (!isLocalUrl(baseUrl) && !/^https:\/\//i.test(baseUrl)) errors.baseUrl = '非本机地址必须使用 HTTPS';

    const proto = getProtocol(protocol);
    if (!proto) errors.protocol = '请选择协议类型';
    else if (proto.needsKey && !key && !hasStoredKey && protocol !== 'ollama') {
      errors.apiKey = '请填写 API 密钥';
    }
    if (!models.length) errors.models = '请至少选择或添加一个模型';
    models.forEach((m, i) => {
      const ctx = Number(m.contextWindow);
      if (!Number.isInteger(ctx) || ctx < CONTEXT_MIN || ctx > CONTEXT_MAX) {
        errors[`modelContext:${i}`] = `「${m.id}」上下文需为 ${CONTEXT_MIN.toLocaleString()}–${CONTEXT_MAX.toLocaleString()} 的整数`;
      }
    });
    if (input.duplicateNames && input.duplicateNames.length) {
      errors.models = `模型已存在：${input.duplicateNames.join('、')}，请勿重复添加`;
    }
    return errors;
  }

  async function fetchModelList({ protocol, baseUrl, apiKey, signal }) {
    const url = trimUrl(baseUrl);
    const headers = {};
    if (apiKey) headers.Authorization = `Bearer ${apiKey}`;

    if (protocol === 'ollama') {
      const res = await fetch(`${url}/api/tags`, { method: 'GET', cache: 'no-store', credentials: 'omit', signal });
      if (!res.ok) throw new Error('list_failed');
      const data = await res.json();
      const list = Array.isArray(data.models)
        ? data.models.map(m => ({ id: m.name, contextWindow: DEFAULT_CONTEXT }))
        : [];
      if (!list.length) throw new Error('empty_list');
      return list;
    }

    if (protocol === 'anthropic-messages') {
      // Anthropic 无公开 list models 端点，返回内置目录；用户仍可手动添加
      return ANTHROPIC_BUILTIN_MODELS.map(m => ({ ...m }));
    }

    const res = await fetch(`${url}/models`, { method: 'GET', cache: 'no-store', credentials: 'omit', signal, headers });
    if (!res.ok) throw new Error('list_failed');
    const data = await res.json();
    const raw = Array.isArray(data.data) ? data.data : Array.isArray(data.models) ? data.models : [];
    const list = raw
      .map(item => (typeof item === 'string' ? item : item.id || item.name))
      .filter(Boolean)
      .map(id => ({ id: String(id), contextWindow: DEFAULT_CONTEXT }));
    if (!list.length) throw new Error('empty_list');
    return list;
  }

  // 最小非流式请求；按协议发不同探测
  async function testConnection({ protocol, baseUrl, apiKey, model, signal }) {
    const url = trimUrl(baseUrl);
    if (protocol === 'ollama') {
      const res = await fetch(`${url}/api/tags`, { method: 'GET', cache: 'no-store', credentials: 'omit', signal });
      if (!res.ok) throw new Error('test_failed');
      return { ok: true, message: '本地 Ollama 可连接。' };
    }
    if (protocol === 'anthropic-messages') {
      const res = await fetch(`${url}/v1/messages`, {
        method: 'POST', cache: 'no-store', credentials: 'omit', signal,
        headers: { 'Content-Type': 'application/json', 'anthropic-version': '2023-06-01', ...(apiKey ? { 'x-api-key': apiKey } : {}) },
        body: JSON.stringify({ model, max_tokens: 1, messages: [{ role: 'user', content: 'ping' }] })
      });
      if (!res.ok) throw new Error('test_failed');
      const data = await res.json();
      if (!data.content && !data.id) throw new Error('bad_response');
      return { ok: true, message: '连接成功，模型已返回响应。' };
    }
    const res = await fetch(`${url}/chat/completions`, {
      method: 'POST', cache: 'no-store', credentials: 'omit', signal,
      headers: { 'Content-Type': 'application/json', ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}) },
      body: JSON.stringify({ model, messages: [{ role: 'user', content: 'ping' }], max_tokens: 1, stream: false })
    });
    if (!res.ok) throw new Error('test_failed');
    const data = await res.json();
    if (!Array.isArray(data.choices)) throw new Error('bad_response');
    return { ok: true, message: '连接成功，模型已返回响应。' };
  }

  // —— 跨端分享：不含 api_key；预设厂商只带 vendor_id，接收端查本地 registry ——
  const SHARE_SCHEMA = 'notemeld.model-add.v1';
  function buildSharePayload({ vendorId, displayName, protocol, baseUrl, models }) {
    const payload = { s: SHARE_SCHEMA, v: 1 };
    const vendor = getVendor(vendorId);
    if (vendor && !vendor.custom && vendor.protocol !== 'bedrock') {
      payload.vendor = vendorId; // 协议与 base_url 由接收端 registry 解析，保持二维码精简
    } else {
      payload.vendor = 'custom';
      payload.name = displayName;
      payload.protocol = protocol;
      payload.url = trimUrl(baseUrl);
    }
    payload.models = (models || []).map(m => ({
      id: m.id,
      ...(m.displayName && m.displayName !== m.id ? { n: m.displayName } : {}),
      ...(m.contextWindow && m.contextWindow !== DEFAULT_CONTEXT ? { c: m.contextWindow } : {})
    }));
    return payload;
  }
  function encodeShare(payload) {
    const json = JSON.stringify(payload);
    // 用 UTF-8 安全 base64url，兼容 Unicode 厂商/模型名
    const bytes = new TextEncoder().encode(json);
    let bin = '';
    bytes.forEach(b => { bin += String.fromCharCode(b); });
    const b64 = btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    return `notemeld://model-add?d=${b64}`;
  }
  function decodeShare(text) {
    const raw = String(text || '').trim();
    let json = raw;
    const match = raw.match(/^notemeld:\/\/model-add\?d=([A-Za-z0-9_-]+)$/);
    if (match) {
      const b64 = match[1].replace(/-/g, '+').replace(/_/g, '/');
      const bin = atob(b64);
      const bytes = Uint8Array.from(bin, c => c.charCodeAt(0));
      json = new TextDecoder().decode(bytes);
    }
    let payload;
    try { payload = JSON.parse(json); } catch { return null; }
    if (!payload || payload.s !== SHARE_SCHEMA || !Array.isArray(payload.models)) return null;
    const vendor = getVendor(payload.vendor);
    if (payload.vendor && payload.vendor !== 'custom' && vendor && !vendor.custom) {
      return {
        vendorId: vendor.id, displayName: vendor.name, protocol: vendor.protocol, baseUrl: vendor.baseUrl,
        models: payload.models.map(m => ({ id: m.id, displayName: m.n || m.id, contextWindow: m.c || DEFAULT_CONTEXT })),
        imported: true
      };
    }
    return {
      vendorId: 'custom', displayName: payload.name || '', protocol: payload.protocol || 'openai-compatible',
      baseUrl: payload.url || '',
      models: payload.models.map(m => ({ id: m.id, displayName: m.n || m.id, contextWindow: m.c || DEFAULT_CONTEXT })),
      imported: true
    };
  }

  window.ModelVendorRegistry = {
    PROTOCOLS, MODEL_VENDORS, ANTHROPIC_BUILTIN_MODELS,
    DEFAULT_CONTEXT, CONTEXT_MIN, CONTEXT_MAX,
    getVendor, getProtocol, trimUrl, isLocalUrl, isValidHttpUrl,
    validateModelConfig, fetchModelList, testConnection,
    buildSharePayload, encodeShare, decodeShare, SHARE_SCHEMA
  };
})();
