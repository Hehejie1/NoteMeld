import { useMemo, useState, type FormEvent } from 'react'
import CloudClient, { type CatalogProvider, type CatalogDiscoveredModel } from '../../services/cloud'
import { useCloudLocale } from '../../pages/CloudPage/cloudLocale'
import {
  ANTHROPIC_BUILTIN_MODELS,
  DEFAULT_CONTEXT,
  MODEL_VENDORS,
  PROTOCOLS,
  decodeShare,
  encodeShare,
  buildSharePayload,
  getProtocol,
  isLocalUrl,
  trimUrl,
  validateModelConfig,
} from '../../lib/modelVendorRegistry'

type SelectedModel = {
  model_id: string
  display_name: string
  context_window: number
  is_default: boolean
}

export function CloudModelForm({
  client,
  onCreated,
  providerToEdit,
  readOnly = false,
}: {
  client: CloudClient
  onCreated?: () => void
  providerToEdit?: CatalogProvider
  readOnly?: boolean
}) {
  const { t } = useCloudLocale()
  const editableVendors = MODEL_VENDORS.filter(vendor => !vendor.unsupported)

  const initialVendor = editableVendors.find(vendor => vendor.id === providerToEdit?.vendor_id)
  const [vendorId, setVendorId] = useState(initialVendor?.id ?? 'volcengine-ark')
  const [displayName, setDisplayName] = useState(providerToEdit?.display_name ?? '')
  const [protocol, setProtocol] = useState(providerToEdit?.protocol ?? 'openai-compatible')
  const [baseUrl, setBaseUrl] = useState(providerToEdit?.base_url ?? '')
  const [apiKey, setApiKey] = useState('')
  const [discovered, setDiscovered] = useState<CatalogDiscoveredModel[]>([])
  const [models, setModels] = useState<SelectedModel[]>([])
  const [busy, setBusy] = useState(false)
  const [discovering, setDiscovering] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [shareText, setShareText] = useState('')

  const selectedVendor = editableVendors.find(vendor => vendor.id === vendorId)
  const proto = getProtocol(protocol)
  const needsKey = proto?.needs_key ?? true
  const hasStoredKey = Boolean(providerToEdit?.has_api_key)
  const existingModelIds = useMemo(
    () => new Set((providerToEdit?.models ?? []).map(item => item.model_id)),
    [providerToEdit]
  )

  function applyVendor(id: string) {
    const vendor = editableVendors.find(item => item.id === id) ?? editableVendors[editableVendors.length - 1]
    setVendorId(vendor.id)
    setProtocol((vendor.protocol || 'openai-compatible') as typeof protocol)
    setBaseUrl(vendor.base_url)
    setDisplayName(providerToEdit ? displayName : vendor.name)
    setDiscovered([])
    setModels([])
  }

  function applyDiscovered(selections: CatalogDiscoveredModel[]) {
    setModels(
      selections.map((item, index) => ({
        model_id: item.id,
        display_name: item.name || item.id,
        context_window: item.context_window ?? DEFAULT_CONTEXT,
        is_default: index === 0,
      }))
    )
  }

  function addManualModel() {
    const nextId = window.prompt(t('models.prompt-model-id', '请输入模型 ID'))?.trim()
    if (!nextId || models.some(item => item.model_id === nextId)) return
    setModels(current => [
      ...current,
      { model_id: nextId, display_name: nextId, context_window: DEFAULT_CONTEXT, is_default: false },
    ])
  }

  function updateModel(rowId: string, patch: Partial<SelectedModel>) {
    setModels(current =>
      current.map(item =>
        item.model_id === rowId
          ? { ...item, ...patch, is_default: patch.is_default ? true : item.is_default }
          : patch.is_default
            ? { ...item, is_default: false }
            : item
      )
    )
  }

  function removeModel(rowId: string) {
    setModels(current => current.filter(item => item.model_id !== rowId))
  }

  async function discover() {
    setDiscovering(true); setError(null); setMessage(null)
    try {
      const list = await client.discoverCatalogModels({
        protocol,
        base_url: baseUrl,
        ...(apiKey ? { api_key: apiKey } : {}),
      })
      setDiscovered(list)
      applyDiscovered(list)
      setMessage(
        list.length
          ? t('models.discovered', `已发现 ${list.length} 个模型，请勾选要保存的模型。`)
          : t('models.none-discovered', '厂商没有返回可用模型，可手动添加模型 ID。')
      )
    } catch (reason) {
      setDiscovered([])
      setError(reason instanceof Error ? reason.message : t('models.discovery-failed', '模型目录读取失败，请检查地址和凭据。'))
    } finally { setDiscovering(false) }
  }

  async function testConnection() {
    setTesting(true); setError(null); setMessage(null)
    try {
      const result = await client.testCatalogConnection({
        protocol,
        base_url: baseUrl,
        ...(apiKey ? { api_key: apiKey } : {}),
        model_id: models.find(item => item.is_default)?.model_id ?? models[0]?.model_id ?? null,
      })
      if (result.ok) setMessage(t('models.test-ok', '连接成功。'))
      else setError(result.message || t('models.test-failed', '连接失败。'))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('models.test-failed', '连接失败。'))
    } finally { setTesting(false) }
  }

  async function importShare() {
    setError(null); setMessage(null)
    const decoded = decodeShare(shareText)
    if (!decoded) {
      setError(t('models.share-invalid', '分享内容无效：必须为 notemeld://model-add 链接，且不得包含密钥。'))
      return
    }
    const vendor = editableVendors.find(item => item.id === decoded.vendor_id)
    setVendorId(vendor?.id ?? 'custom')
    setDisplayName(decoded.display_name)
    setProtocol(decoded.protocol as typeof protocol)
    setBaseUrl(decoded.base_url)
    setDiscovered([])
    setModels(decoded.models.map((item, index) => ({
      model_id: item.id,
      display_name: item.display_name,
      context_window: item.context_window,
      is_default: index === 0,
    })))
    setMessage(t('models.share-loaded', '已载入分享配置，补全 API Key 后即可保存。'))
  }

  async function copyShare() {
    const payload = buildSharePayload({
      vendor_id: vendorId,
      display_name: displayName,
      protocol,
      base_url: baseUrl,
      models: models.map(item => ({
        id: item.model_id,
        display_name: item.display_name,
        context_window: item.context_window,
      })),
    })
    const uri = encodeShare(payload)
    try {
      await navigator.clipboard.writeText(uri)
      setMessage(t('models.share-copied', '分享链接已复制（不含 API Key）。'))
    } catch {
      setShareText(uri)
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(null); setMessage(null)
    const freshModels = models.filter(item => !existingModelIds.has(item.model_id))
    const validation = validateModelConfig({
      display_name: displayName,
      protocol,
      base_url: baseUrl,
      api_key: apiKey,
      has_stored_key: hasStoredKey,
      models: providerToEdit ? freshModels : models,
    })
    if (Object.keys(validation).length) {
      setError(Object.values(validation)[0])
      return
    }
    setBusy(true)
    try {
      let provider = providerToEdit
      if (!provider) {
        const created = await client.createCatalogProvider({
          display_name: displayName.trim(),
          vendor_id: selectedVendor?.custom || vendorId === 'custom' ? 'custom' : vendorId,
          protocol,
          base_url: trimUrl(baseUrl),
          auth_type: protocol === 'ollama' ? 'none' : protocol === 'anthropic-messages' ? 'x-api-key' : 'bearer',
          ...(apiKey ? { api_key: apiKey } : {}),
        })
        provider = created
      } else if (displayName.trim() !== provider.display_name || apiKey) {
        provider = await client.updateCatalogProvider(provider.id, {
          ...(displayName.trim() !== provider.display_name ? { display_name: displayName.trim() } : {}),
          ...(apiKey ? { api_key: apiKey } : {}),
        })
      }
      if (freshModels.length && provider) {
        const defaultId = freshModels.find(item => item.is_default)?.model_id
        await client.saveCatalogModelsBatch(
          provider.id,
          freshModels.map(item => ({
            model_id: item.model_id,
            display_name: item.display_name,
            context_window: item.context_window,
            is_default: Boolean(defaultId && item.model_id === defaultId),
          }))
        )
      }
      setApiKey('')
      setMessage(t('models.saved-count', '配置已保存，列表已刷新。'))
      onCreated?.()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('models.save-failed', '配置保存失败，请重试。'))
    } finally { setBusy(false) }
  }

  const discoverDisabled =
    discovering || !baseUrl || (!isLocalUrl(baseUrl) && needsKey && !apiKey && !hasStoredKey)

  return <form onSubmit={submit} aria-labelledby="model-form-title" className="flex max-h-[80vh] max-w-md flex-col gap-3 overflow-y-auto p-3">
    <h2 id="model-form-title" className="text-base font-semibold">
      {providerToEdit ? t('models.edit-title', '编辑云端厂商') : t('models.add-cloud-title', '添加云端模型')}
    </h2>
    {readOnly ? <p role="alert" className="text-sm text-[var(--error)]">{t('models.read-only', '组织成员仅可查看模型，不能修改。')}</p> : null}
    {!providerToEdit ? <>
      <label htmlFor="model-vendor" className="text-sm font-medium">{t('models.provider-preset', '厂商预设')}</label>
      <select id="model-vendor" value={vendorId} onChange={event => applyVendor(event.target.value)} className="rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2">
        {MODEL_VENDORS.map(vendor => <option key={vendor.id} value={vendor.id} disabled={Boolean(vendor.unsupported)}>
          {vendor.name}{vendor.unsupported ? `（${t('models.unsupported', '暂不支持')}）` : ''}
        </option>)}
      </select>
      {selectedVendor?.url_note ? <p className="text-xs text-[var(--muted)]">{selectedVendor.url_note}</p> : null}
    </> : null}
    <label htmlFor="model-name" className="text-sm font-medium">{t('models.display-name', '厂商显示名称')}</label>
    <input id="model-name" required value={displayName} onChange={event => setDisplayName(event.target.value)} className="rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2" />
    {!providerToEdit ? <>
      <label htmlFor="model-protocol" className="text-sm font-medium">{t('models.protocol', '协议')}</label>
      <select id="model-protocol" value={protocol} onChange={event => setProtocol(event.target.value as typeof protocol)} className="rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2">
        {PROTOCOLS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select>
    </> : null}
    <label htmlFor="model-base-url" className="text-sm font-medium">{t('models.base-url', 'Base URL')}</label>
    <input id="model-base-url" type="url" required value={baseUrl} onChange={event => setBaseUrl(event.target.value)} className="rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2" />
    {needsKey ? <>
      <label htmlFor="model-api-key" className="text-sm font-medium">
        {hasStoredKey ? t('models.api-key-keep', 'API Key（留空保持不变）') : t('models.api-key', 'API Key')}
      </label>
      <input id="model-api-key" type="password" autoComplete="new-password" value={apiKey} onChange={event => setApiKey(event.target.value)} className="rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2" />
    </> : null}
    <div className="flex gap-2">
      <button type="button" disabled={discoverDisabled} onClick={() => void discover()} className="flex-1 rounded border border-[var(--border-subtle)] px-3 py-2 text-sm hover:bg-[var(--surface-container)] disabled:opacity-50">
        {discovering ? t('models.discovering', '读取模型中…') : t('models.discover', '读取模型列表')}
      </button>
      <button type="button" disabled={testing || discoverDisabled} onClick={() => void testConnection()} className="flex-1 rounded border border-[var(--border-subtle)] px-3 py-2 text-sm hover:bg-[var(--surface-container)] disabled:opacity-50">
        {testing ? t('models.testing', '测试中…') : t('models.test', '测试连接')}
      </button>
      <button type="button" onClick={addManualModel} className="rounded border border-[var(--border-subtle)] px-3 py-2 text-sm hover:bg-[var(--surface-container)]">
        {t('models.add-id', '+ ID')}
      </button>
    </div>
    {protocol === 'anthropic-messages' && !discovered.length ? <p className="text-xs text-[var(--muted)]">
      {t('models.anthropic-catalog', `Anthropic 无公开列表接口，使用内置目录：${ANTHROPIC_BUILTIN_MODELS.map(item => item.id).join('、')}`)}
    </p> : null}
    {models.length ? <ul role="list" className="max-h-40 space-y-1 overflow-y-auto rounded border border-[var(--border-subtle)] p-2">
      {models.map(item => <li key={item.model_id} className="flex items-center gap-2 text-sm">
        <input type="radio" name="cloud-default-model" checked={item.is_default} onChange={() => updateModel(item.model_id, { is_default: true })} aria-label={t('models.default', '默认')} />
        <span className="min-w-0 flex-1 truncate">{item.display_name} <span className="text-xs text-[var(--muted)]">{item.model_id}</span></span>
        <input type="number" min={512} max={4_000_000} value={item.context_window} onChange={event => updateModel(item.model_id, { context_window: Number(event.target.value) })} className="w-28 rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-2 py-1 text-xs" aria-label={t('models.context-window', '上下文窗口')} />
        {!existingModelIds.has(item.model_id) ? <button type="button" onClick={() => removeModel(item.model_id)} className="text-xs text-[var(--error)]">{t('models.remove', '移除')}</button> : <span className="text-xs text-[var(--muted)]">{t('models.saved', '已保存')}</span>}
      </li>)}
    </ul> : null}
    {!providerToEdit ? <div className="rounded border border-[var(--border-subtle)] p-2">
      <p className="mb-1 text-sm font-medium">{t('models.share-import', '分享 / 导入')}</p>
      <div className="flex gap-2">
        <input value={shareText} onChange={event => setShareText(event.target.value)} placeholder="notemeld://model-add?d=…" className="min-w-0 flex-1 rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-2 py-1 text-xs" />
        <button type="button" onClick={() => void importShare()} className="rounded border border-[var(--border-subtle)] px-2 py-1 text-xs">{t('models.import', '导入')}</button>
        <button type="button" onClick={() => void copyShare()} className="rounded border border-[var(--border-subtle)] px-2 py-1 text-xs">{t('models.share', '分享')}</button>
      </div>
    </div> : null}
    <button type="submit" disabled={busy || readOnly} className="rounded bg-[var(--primary)] px-3 py-2 text-sm text-white disabled:opacity-50">
      {busy ? t('models.saving', '保存中…') : t('models.save', '保存配置')}
    </button>
    {message ? <p role="status" className="text-sm text-emerald-700">{message}</p> : null}
    {error ? <p role="alert" className="text-sm text-[var(--error)]">{error}</p> : null}
  </form>
}
