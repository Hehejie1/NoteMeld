import assert from 'node:assert/strict'
import { access, readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'

import {
  ANTHROPIC_BUILTIN_MODELS,
  DEFAULT_CONTEXT,
  MODEL_VENDORS,
  PROTOCOLS,
  buildSharePayload,
  decodeShare,
  encodeShare,
  getVendor,
  isValidHttpUrl,
  validateModelConfig,
} from '../src/lib/modelVendorRegistry.ts'

const root = path.resolve(import.meta.dirname, '..')
const readSource = relativePath => readFile(path.join(root, relativePath), 'utf8')

const dialogPath = path.join(root, 'src/components/Form/modelForm/AddModelDialog.tsx')
await access(dialogPath)

// ---------------------------------------------------------------------------
// registry 纯函数契约（notemeld.model-add.v1）
// ---------------------------------------------------------------------------

test('registry：协议枚举与内置厂商预设满足协议约束', () => {
  assert.deepEqual(
    PROTOCOLS.map(p => p.id),
    ['openai-compatible', 'anthropic-messages', 'ollama'],
  )
  assert.ok(MODEL_VENDORS.length >= 22, '至少内置 22 个厂商预设')
  // Bedrock v1 不支持直连，必须显式置灰
  const bedrock = getVendor('aws-bedrock')
  assert.equal(bedrock.protocol, 'bedrock')
  assert.ok(bedrock.unsupported)
  // 不确定地址留空，不臆造
  for (const vendor of MODEL_VENDORS) {
    if (vendor.base_url === '') assert.ok(vendor.url_note || vendor.unsupported || vendor.custom)
    if (vendor.base_url) assert.ok(isValidHttpUrl(vendor.base_url), `${vendor.id} 地址非法`)
  }
  assert.ok(ANTHROPIC_BUILTIN_MODELS.length >= 3)
  assert.equal(DEFAULT_CONTEXT, 128000)
})

test('registry：validateModelConfig 统一即时校验', () => {
  assert.deepEqual(
    validateModelConfig({
      display_name: '  ',
      protocol: 'nope',
      base_url: 'ftp://x',
      models: [],
    }).display_name,
    '请填写名称',
  )
  const ok = validateModelConfig({
    display_name: 'DeepSeek',
    protocol: 'openai-compatible',
    base_url: 'https://api.deepseek.com',
    api_key: 'sk-xxx',
    models: [{ id: 'deepseek-chat', context_window: 64000 }],
  })
  assert.deepEqual(ok, {})

  const badCtx = validateModelConfig({
    display_name: 'X',
    base_url: 'https://api.example.com',
    api_key: 'k',
    models: [{ id: 'm', context_window: 8 }],
  })
  assert.match(badCtx['model_context:0'], /512/)
  // ollama 本地 http 允许且不需要 key
  const ollama = validateModelConfig({
    display_name: 'Local',
    protocol: 'ollama',
    base_url: 'http://localhost:11434',
    models: [{ id: 'llama3', context_window: 8192 }],
  })
  assert.deepEqual(ollama, {})
})

test('registry：分享载荷不含密钥且与配对码严格区分', () => {
  const payload = buildSharePayload({
    vendor_id: 'deepseek',
    display_name: 'DeepSeek',
    protocol: 'openai-compatible',
    base_url: 'https://api.deepseek.com/',
    models: [
      { id: 'deepseek-chat', display_name: 'DeepSeek Chat', context_window: 64000 },
      { id: 'deepseek-reasoner' },
    ],
  })
  const text = encodeShare(payload)
  assert.match(text, /^notemeld:\/\/model-add\?d=/)
  assert.doesNotMatch(text, /api[_-]?key/i)
  const decoded = decodeShare(text)
  assert.equal(decoded.vendor_id, 'deepseek')
  assert.equal(decoded.models[0].context_window, 64000)
  assert.equal(decoded.models[1].context_window, DEFAULT_CONTEXT)
  assert.equal(decoded.imported, true)

  // 配对码必须拒绝
  assert.equal(decodeShare('notemeld://pair?code=ABC123'), null)
  // 夹带密钥必须拒绝
  const evil = encodeShare({ s: 'notemeld.model-add.v1', models: [{ id: 'm' }], api_key: 'sk-leak' })
  assert.equal(decodeShare(evil), null)
  // 非法 schema 拒绝
  assert.equal(decodeShare('notemeld://model-add?d=' + Buffer.from('{"s":"other"}').toString('base64url')), null)
  // 自定义厂商往返
  const custom = encodeShare(
    buildSharePayload({
      vendor_id: 'custom',
      display_name: '我的网关',
      protocol: 'openai-compatible',
      base_url: 'https://gw.example.com/v1',
      models: [{ id: 'gpt-4o-mini' }],
    }),
  )
  const customDecoded = decodeShare(custom)
  assert.equal(customDecoded.vendor_id, 'custom')
  assert.equal(customDecoded.base_url, 'https://gw.example.com/v1')
})

// ---------------------------------------------------------------------------
// 源码结构契约：Form / Dialog / service / store
// ---------------------------------------------------------------------------

test('Form：仅挂载统一 Dialog，不内联模型选择控件', async () => {
  const form = await readSource('src/components/Form/modelForm/Form.tsx')
  assert.match(form, /AddModelDialog/, 'Provider 编辑区必须通过统一 Dialog 添加模型')
  assert.match(form, /providerId=\{id\}/)
  assert.match(form, /hasStoredKey=\{hasStoredKey\}/, '必须告知 Dialog 库内是否已有密钥')
  assert.doesNotMatch(form, /<ModelSelector[\s\S]*providerId=/, '不得内联渲染旧模型选择控件')
})

test('AddModelDialog：拉取走 saved/config 双路，浏览器不直连', async () => {
  const dialog = await readSource('src/components/Form/modelForm/AddModelDialog.tsx')
  assert.match(dialog, /fetchModelsBySaved/, '编辑态必须用库内密钥经后端拉取')
  assert.match(dialog, /fetchModelsBySaved\(providerId\)/)
  assert.match(dialog, /fetchModelsByConfig\(\{[\s\S]*api_key:[\s\S]*base_url:[\s\S]*protocol/)
  assert.match(dialog, /canUseSavedKey\s*=\s*hasStoredKey\s*&&\s*!typedKey/)
  // Anthropic 合并内置目录
  assert.match(dialog, /ANTHROPIC_BUILTIN_MODELS/)
  assert.match(dialog, /protocol === 'anthropic-messages'/)
  // ollama 不要 key
  assert.match(dialog, /protocol !== 'ollama'/)
})

test('AddModelDialog：多选 + 手动添加 + 逐模型校验/测试/默认', async () => {
  const dialog = await readSource('src/components/Form/modelForm/AddModelDialog.tsx')
  // 手动区
  assert.match(dialog, /data-manual-model-id/)
  assert.match(dialog, /data-manual-model-context/)
  // 远端多选
  assert.match(dialog, /data-model-checkbox=\{model\.model_id\}/)
  assert.match(dialog, /toggleModel\(model, event\.target\.checked\)/)
  // 已选区
  assert.match(dialog, /data-selected-models/)
  assert.match(dialog, /data-default-model=\{item\.model_id\}/)
  assert.match(dialog, /name="default-model"/)
  assert.match(dialog, /data-model-context=\{item\.model_id\}/)
  assert.match(dialog, /data-model-test=\{item\.model_id\}/)
  // 上下文范围
  assert.match(dialog, new RegExp(`number < CONTEXT_MIN || number > CONTEXT_MAX`))
  assert.match(dialog, /需为整数/)
  // 测试双路
  assert.match(dialog, /testSavedConnection\(\{ provider_id: providerId, model_id: modelId \}\)/)
  assert.match(dialog, /testConnection\(\{[\s\S]*model_id: modelId/)
  // 标题/按钮文案
  assert.match(dialog, /添加模型/)
  assert.match(dialog, /拉取模型列表/)
  assert.match(dialog, /保存选中模型/)
})

test('AddModelDialog：批量保存成功才刷新并关闭，失败保留弹窗', async () => {
  const dialog = await readSource('src/components/Form/modelForm/AddModelDialog.tsx')
  assert.match(
    dialog,
    /await saveModels\(\{[\s\S]*provider_id: providerId,[\s\S]*models: selectedList\.map\(item => \(\{[\s\S]*model_id: item\.model_id,[\s\S]*context_window_tokens: Number\(item\.contextInput\),[\s\S]*test_status:[\s\S]*\}\)\),[\s\S]*default_model_id: defaultModelId \|\| null,?[\s\S]*\}\)/,
    '必须按批量协议提交 provider_id/models/default_model_id',
  )
  assert.match(dialog, /await onSaved\?\.\(\)[\s\S]*onOpenChange\(false\)/, '成功后刷新并关闭')
  assert.doesNotMatch(dialog, /catch[\s\S]{0,240}onOpenChange\(false\)/, '失败必须保留弹窗')
  // 空选择拦截
  assert.match(dialog, /请至少选择或添加一个模型/)
})

test('service/store：批量保存/默认模型/库内端点/分享解码齐备', async () => {
  const service = await readSource('src/services/model.ts')
  const store = await readSource('src/store/modelStore/index.ts')

  for (const [name, source] of [['service', service], ['store', store]]) {
    for (const field of ['provider_id', 'context_window_tokens', 'model_id', 'test_status']) {
      assert.match(source, new RegExp(field), `${name} 必须保留协议字段 ${field}`)
    }
  }
  assert.match(service, /post\('\/model_list_saved'/)
  assert.match(service, /post\('\/model_list_by_config'/)
  assert.match(service, /post\('\/connect_test_saved'/)
  assert.match(service, /post\('\/models\/batch'/)
  assert.match(service, /post\('\/models\/default'/)
  assert.match(service, /post\('\/model_share\/decode'/)
  assert.match(store, /saveModels:\s*async \(data\) => \(await saveModelsBatch\(data\)\)/)
  assert.match(store, /setModelDefault:[\s\S]*setDefaultModel\(\{ provider_id: providerId, model_id: modelId \}\)/)
})

// 4d：Provider 卡片协议徽标/密钥状态/行内分享 + 粘贴导入 + 默认标记/测试状态

test('providerCard：协议徽标/密钥三态/行内分享（前端编码，不经后端）', async () => {
  const card = await readSource('src/components/Form/modelForm/components/providerCard.tsx')
  assert.match(card, /data-provider-protocol=\{id\}/)
  assert.match(card, /data-provider-credential=\{id\}/)
  assert.match(card, /无需密钥/)
  assert.match(card, /密钥已保存/)
  assert.match(card, /待填密钥/)
  assert.match(card, /data-provider-share=\{id\}/)
  assert.match(card, /buildSharePayload/)
  assert.match(card, /encodeShare/)
  assert.match(card, /navigator\.clipboard\.writeText/)
  assert.match(card, /不含 API 密钥/)
})

test('Provider：导入配置入口走 decode 端点，imported 态不自动保存', async () => {
  const provider = await readSource('src/components/Form/modelForm/Provider.tsx')
  assert.match(provider, /data-import-config/)
  assert.match(provider, /data-import-text/)
  assert.match(provider, /decodeModelShare/)
  assert.match(provider, /state: \{ importedShare: decoded \}/)
  assert.match(provider, /不会自动保存/)
})

test('Form/AddModelDialog：导入预填透传、默认星标与测试状态徽标', async () => {
  const form = await readSource('src/components/Form/modelForm/Form.tsx')
  assert.match(form, /data-imported-banner/)
  assert.match(form, /data-saved-model=\{model\.model_id\}/)
  assert.match(form, /data-set-default=\{model\.model_id\}/)
  assert.match(form, /data-model-status=\{model\.model_id\}/)
  assert.match(form, /setModelDefault\(id, modelId\)/)
  // 创建后跳转透传导入模型，避免重挂载丢失
  assert.match(form, /state: initialModels\.length \? \{ initialModels \} : undefined/)

  const dialog = await readSource('src/components/Form/modelForm/AddModelDialog.tsx')
  assert.match(dialog, /initialModels\?: Array<\{[\s\S]*model_id: string[\s\S]*display_name: string[\s\S]*context_window: number[\s\S]*\}>/)
  assert.match(dialog, /upsertRemoteModels\(incoming, true\)/)
})
