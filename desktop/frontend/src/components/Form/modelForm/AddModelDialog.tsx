import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useModelStore } from '@/store/modelStore'
import {
  fetchModelsByConfig,
  fetchModelsBySaved,
  testConnection,
  testSavedConnection,
} from '@/services/model'
import {
  ANTHROPIC_BUILTIN_MODELS,
  CONTEXT_MAX,
  CONTEXT_MIN,
  DEFAULT_CONTEXT,
  type ProtocolId,
} from '@/lib/modelVendorRegistry'

interface AddModelDialogProps {
  providerId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => Promise<void> | void
  // Provider 表单当前配置：协议与已 trim 的 base_url
  config: { protocol: ProtocolId; baseUrl: string }
  // 新建 Provider 刚填写、尚未落库的临时 Key；编辑态通常为空（改用库内密钥）
  apiKey?: string
  // 编辑态库内是否已有 Key（决定能否走 /connect_test_saved 与 /model_list_saved）
  hasStoredKey?: boolean
  // 分享导入的初始模型：弹窗打开时预填到远端目录并默认勾选，不自动保存
  initialModels?: Array<{
    model_id: string
    display_name: string
    context_window: number
  }>
}

interface RemoteModel {
  model_id: string
  display_name: string
  context_window: number
  builtin?: boolean
}

interface SelectedModel extends RemoteModel {
  // 用户可编辑展示名
  displayName: string
  // 字符串态输入，失焦/保存时统一校验
  contextInput: string
  testStatus: 'unknown' | 'testing' | 'ok' | 'failed'
}

const normalizeRemote = (raw: unknown): RemoteModel | null => {
  if (!raw || typeof raw !== 'object') return null
  const item = raw as Record<string, unknown>
  const modelId = String(item.id ?? item.model_id ?? '').trim()
  if (!modelId) return null
  const ctx = Number(item.context_window ?? item.context_window_tokens ?? DEFAULT_CONTEXT)
  const validCtx = Number.isInteger(ctx) && ctx >= CONTEXT_MIN && ctx <= CONTEXT_MAX ? ctx : DEFAULT_CONTEXT
  const displayName = String(item.display_name ?? item.name ?? modelId)
  return {
    model_id: modelId,
    display_name: displayName,
    context_window: validCtx,
    builtin: Boolean(item.builtin),
  }
}

export function AddModelDialog({
  providerId,
  open,
  onOpenChange,
  onSaved,
  config,
  apiKey = '',
  hasStoredKey = false,
  initialModels = [],
}: AddModelDialogProps) {
  const saveModels = useModelStore(state => state.saveModels)

  const [remoteModels, setRemoteModels] = useState<RemoteModel[]>([])
  const [loadingList, setLoadingList] = useState(false)
  const [fetched, setFetched] = useState(false)
  const [selected, setSelected] = useState<Record<string, SelectedModel>>({})
  const [defaultModelId, setDefaultModelId] = useState<string>('')
  const [manualId, setManualId] = useState('')
  const [manualContext, setManualContext] = useState(String(DEFAULT_CONTEXT))
  const [saving, setSaving] = useState(false)

  const protocol = config.protocol
  const baseUrl = config.baseUrl
  const typedKey = apiKey.trim()
  const canUseSavedKey = hasStoredKey && !typedKey
  const selectedList = useMemo(() => Object.values(selected), [selected])

  const resetState = () => {
    setRemoteModels([])
    setFetched(false)
    setLoadingList(false)
    setSelected({})
    setDefaultModelId('')
    setManualId('')
    setManualContext(String(DEFAULT_CONTEXT))
    setSaving(false)
  }

  useEffect(() => {
    if (open) resetState()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, providerId])

  // 分享导入：打开时将导入模型预填到目录并默认勾选（不自动保存）
  useEffect(() => {
    if (!open || !initialModels.length) return
    const incoming: RemoteModel[] = initialModels
      .map(item =>
        normalizeRemote({
          model_id: item.model_id,
          display_name: item.display_name,
          context_window: item.context_window,
        }),
      )
      .filter((item): item is RemoteModel => Boolean(item))
    upsertRemoteModels(incoming, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialModels])

  const upsertRemoteModels = (incoming: RemoteModel[], preselect: boolean) => {
    setRemoteModels(previous => {
      const merged = new Map<string, RemoteModel>()
      previous.forEach(item => merged.set(item.model_id, item))
      incoming.forEach(item => {
        if (!merged.has(item.model_id)) merged.set(item.model_id, item)
      })
      return Array.from(merged.values())
    })
    if (preselect) {
      setSelected(previous => {
        const next = { ...previous }
        incoming.forEach(item => {
          if (!next[item.model_id]) {
            next[item.model_id] = {
              ...item,
              displayName: item.display_name,
              contextInput: String(item.context_window),
              testStatus: 'unknown',
            }
          }
        })
        return next
      })
    }
  }

  const handleFetch = async () => {
    if (!baseUrl && protocol !== 'anthropic-messages') {
      toast.error('请先填写接口地址')
      return
    }
    if (protocol !== 'ollama' && !typedKey && !canUseSavedKey) {
      toast.error('请先填写 API Key')
      return
    }
    try {
      setLoadingList(true)
      let list: unknown[] = []
      if (canUseSavedKey) {
        const response = await fetchModelsBySaved(providerId)
        list = Array.isArray(response?.models) ? response.models : []
      } else {
        const response = await fetchModelsByConfig({
          api_key: typedKey || undefined,
          base_url: baseUrl,
          protocol,
        })
        list = Array.isArray(response?.models) ? response.models : []
      }
      const normalized = list.map(normalizeRemote).filter((item): item is RemoteModel => Boolean(item))
      // Anthropic 无标准公开列表接口：合并内置常用目录并默认预选
      if (protocol === 'anthropic-messages') {
        const builtins: RemoteModel[] = ANTHROPIC_BUILTIN_MODELS.map(item => ({
          model_id: item.id,
          display_name: item.id,
          context_window: item.context_window,
          builtin: true,
        }))
        upsertRemoteModels(builtins, true)
      }
      upsertRemoteModels(normalized, protocol !== 'anthropic-messages')
      setFetched(true)
      if (!normalized.length && protocol !== 'anthropic-messages') {
        toast('未获取到模型，可手动添加', { icon: 'ℹ️' })
      }
    } catch (error: unknown) {
      const message =
        typeof error === 'object' && error !== null && 'response' in error
          ? (error as { response?: { data?: { msg?: string } } }).response?.data?.msg
          : undefined
      toast.error(`获取模型列表失败：${message || '请检查地址、密钥与网络'}`)
    } finally {
      setLoadingList(false)
    }
  }

  const toggleModel = (model: RemoteModel, checked: boolean) => {
    setSelected(previous => {
      const next = { ...previous }
      if (checked) {
        next[model.model_id] = {
          ...model,
          displayName: model.display_name,
          contextInput: String(model.context_window),
          testStatus: 'unknown',
        }
      } else {
        delete next[model.model_id]
        if (defaultModelId === model.model_id) setDefaultModelId('')
      }
      return next
    })
  }

  const updateContext = (modelId: string, value: string) => {
    setSelected(previous =>
      previous[modelId]
        ? { ...previous, [modelId]: { ...previous[modelId], contextInput: value } }
        : previous,
    )
  }

  const contextError = (value: string): string | null => {
    if (!/^\d+$/.test(value.trim())) return '需为整数'
    const number = Number(value)
    if (!Number.isInteger(number) || number < CONTEXT_MIN || number > CONTEXT_MAX) {
      return `范围 ${CONTEXT_MIN.toLocaleString()}–${CONTEXT_MAX.toLocaleString()}`
    }
    return null
  }

  const handleAddManual = () => {
    const modelId = manualId.trim()
    if (!modelId) {
      toast.error('请填写模型 ID')
      return
    }
    if (selected[modelId] || remoteModels.some(item => item.model_id === modelId)) {
      toast.error('该模型已在列表中')
      return
    }
    const ctxError = contextError(manualContext)
    if (ctxError) {
      toast.error(`上下文长度${ctxError}`)
      return
    }
    const model: RemoteModel = {
      model_id: modelId,
      display_name: modelId,
      context_window: Number(manualContext),
    }
    upsertRemoteModels([model], false)
    setSelected(previous => ({
      ...previous,
      [modelId]: {
        ...model,
        displayName: modelId,
        contextInput: manualContext.trim(),
        testStatus: 'unknown',
      },
    }))
    setManualId('')
    setManualContext(String(DEFAULT_CONTEXT))
  }

  const handleTestModel = async (modelId: string) => {
    setSelected(previous =>
      previous[modelId] ? { ...previous, [modelId]: { ...previous[modelId], testStatus: 'testing' } } : previous,
    )
    try {
      if (canUseSavedKey) {
        await testSavedConnection({ provider_id: providerId, model_id: modelId })
      } else {
        await testConnection({
          api_key: typedKey || undefined,
          base_url: baseUrl,
          protocol,
          model_id: modelId,
        })
      }
      setSelected(previous =>
        previous[modelId] ? { ...previous, [modelId]: { ...previous[modelId], testStatus: 'ok' } } : previous,
      )
      toast.success(`「${modelId}」连接测试通过`)
    } catch {
      setSelected(previous =>
        previous[modelId]
          ? { ...previous, [modelId]: { ...previous[modelId], testStatus: 'failed' } }
          : previous,
      )
      toast.error(`「${modelId}」连接测试失败`)
    }
  }

  const handleSave = async () => {
    if (!selectedList.length) {
      toast.error('请至少选择或添加一个模型')
      return
    }
    for (const item of selectedList) {
      const error = contextError(item.contextInput)
      if (error) {
        toast.error(`「${item.model_id}」上下文长度${error}`)
        return
      }
    }
    try {
      setSaving(true)
      await saveModels({
        provider_id: providerId,
        models: selectedList.map(item => ({
          model_id: item.model_id,
          display_name: item.displayName.trim() || item.model_id,
          context_window_tokens: Number(item.contextInput),
          supports_vision: false,
          supports_stream: true,
          test_status:
            item.testStatus === 'ok' ? 'ok' : item.testStatus === 'failed' ? 'failed' : 'unknown',
        })),
        default_model_id: defaultModelId || null,
      })
      await onSaved?.()
      toast.success('模型保存成功 🎉')
      onOpenChange(false)
    } catch (error: unknown) {
      const message =
        typeof error === 'object' && error !== null && 'response' in error
          ? (error as { response?: { data?: { msg?: string } } }).response?.data?.msg
          : undefined
      toast.error(`保存失败：${message || '请稍后重试'}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>添加模型</DialogTitle>
          <DialogDescription>
            按 {baseUrl || '当前接口地址'} 拉取模型目录并多选；也可手动填写模型 ID。上下文长度需在
            {' '}
            {CONTEXT_MIN.toLocaleString()}–{CONTEXT_MAX.toLocaleString()} 之间。
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-1">
          {/* 拉取区 */}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" onClick={handleFetch} disabled={loadingList || saving}>
              {loadingList ? '拉取中...' : fetched ? '重新拉取模型列表' : '拉取模型列表'}
            </Button>
            {canUseSavedKey && (
              <span className="text-xs text-on-surface-variant">将使用已保存的加密密钥拉取</span>
            )}
            {protocol === 'anthropic-messages' && (
              <span className="text-xs text-on-surface-variant">Anthropic 使用内置常用目录，可直接勾选</span>
            )}
          </div>

          {/* 手动添加区 */}
          <div className="grid gap-2 rounded-lg border border-border-subtle p-3 sm:grid-cols-[1fr_160px_auto] sm:items-end">
            <div className="grid gap-1">
              <Label htmlFor="manual-model-id">模型 ID</Label>
              <Input
                id="manual-model-id"
                data-manual-model-id
                value={manualId}
                onChange={event => setManualId(event.target.value)}
                placeholder="例如 gpt-4o-mini"
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="manual-model-context">上下文长度</Label>
              <Input
                id="manual-model-context"
                data-manual-model-context
                type="number"
                min={CONTEXT_MIN}
                max={CONTEXT_MAX}
                value={manualContext}
                onChange={event => setManualContext(event.target.value)}
              />
            </div>
            <Button type="button" variant="outline" onClick={handleAddManual} disabled={saving}>
              <Plus className="mr-1 h-4 w-4" />
              添加
            </Button>
          </div>

          {/* 远端目录多选 */}
          <div className="max-h-56 overflow-y-auto rounded-lg border border-border-subtle">
            {remoteModels.length === 0 ? (
              <div className="p-4 text-center text-xs text-on-surface-variant">
                {loadingList ? '正在拉取...' : '暂无模型，请先拉取或手动添加'}
              </div>
            ) : (
              <ul className="divide-y divide-border-subtle">
                {remoteModels.map(model => {
                  const checked = Boolean(selected[model.model_id])
                  return (
                    <li key={model.model_id} className="flex items-center gap-3 px-3 py-2">
                      <input
                        type="checkbox"
                        data-model-checkbox={model.model_id}
                        className="h-4 w-4 shrink-0 accent-blue-600"
                        checked={checked}
                        onChange={event => toggleModel(model, event.target.checked)}
                      />
                      <span className="min-w-0 flex-1 truncate text-sm" title={model.model_id}>
                        {model.model_id}
                        {model.builtin && (
                          <span className="ml-2 rounded bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-600">
                            内置
                          </span>
                        )}
                      </span>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          {/* 已选模型：逐模型上下文 + 默认 + 测试 + 移除 */}
          {selectedList.length > 0 && (
            <div className="flex flex-col gap-2" data-selected-models>
              <Label>已选模型（{selectedList.length}）</Label>
              <div className="max-h-64 overflow-y-auto rounded-lg border border-border-subtle">
                <ul className="divide-y divide-border-subtle">
                  {selectedList.map(item => {
                    const error = contextError(item.contextInput)
                    return (
                      <li key={item.model_id} className="flex flex-wrap items-center gap-2 px-3 py-2">
                        <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2">
                          <input
                            type="radio"
                            name="default-model"
                            data-default-model={item.model_id}
                            className="h-4 w-4 shrink-0 accent-green-600"
                            checked={defaultModelId === item.model_id}
                            onChange={() => setDefaultModelId(item.model_id)}
                          />
                          <span className="min-w-0 truncate text-sm" title={item.model_id}>
                            {item.model_id}
                          </span>
                        </label>
                        <div className="flex items-center gap-1">
                          <Input
                            type="number"
                            min={CONTEXT_MIN}
                            max={CONTEXT_MAX}
                            data-model-context={item.model_id}
                            value={item.contextInput}
                            onChange={event => updateContext(item.model_id, event.target.value)}
                            className="h-8 w-32 text-xs"
                            aria-label={`${item.model_id} 上下文长度`}
                          />
                          <Button
                            type="button"
                            variant="ghost"
                            className="h-8 px-2 text-xs"
                            onClick={() => handleTestModel(item.model_id)}
                            disabled={item.testStatus === 'testing' || saving}
                            data-model-test={item.model_id}
                          >
                            {item.testStatus === 'testing'
                              ? '测试中'
                              : item.testStatus === 'ok'
                                ? '已通过'
                                : item.testStatus === 'failed'
                                  ? '未通过'
                                  : '测试'}
                          </Button>
                          <button
                            type="button"
                            className="rounded p-1 text-neutral-400 hover:text-neutral-600"
                            onClick={() => toggleModel(item, false)}
                            aria-label={`移除 ${item.model_id}`}
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                        {error && <span className="w-full pl-6 text-xs text-red-500">{error}</span>}
                      </li>
                    )
                  })}
                </ul>
              </div>
              <span className="text-xs text-on-surface-variant">选中左侧圆点可将该模型设为供应商默认模型。</span>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            取消
          </Button>
          <Button type="button" onClick={handleSave} disabled={saving || !selectedList.length}>
            {saving ? '保存中...' : `保存选中模型${selectedList.length ? `（${selectedList.length}）` : ''}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
