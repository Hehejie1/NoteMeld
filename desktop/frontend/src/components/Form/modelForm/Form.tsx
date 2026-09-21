import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
  FormDescription,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useNavigate, useParams, useLocation } from 'react-router-dom'
import { useProviderStore } from '@/store/providerStore'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import {
  testConnection,
  testSavedConnection,
  deleteModelById,
  type DecodedModelShare,
} from '@/services/model.ts'
import { Eye, EyeOff, Star, X } from 'lucide-react'
import { useModelStore } from '@/store/modelStore'
import { AddModelDialog } from '@/components/Form/modelForm/AddModelDialog'
import {
  MODEL_VENDORS,
  PROTOCOLS,
  getVendor,
  trimUrl,
  isLocalUrl,
  isValidHttpUrl,
  type ProtocolId,
} from '@/lib/modelVendorRegistry'

// notemeld.model-add.v1：Provider 两级协议表单
const ProviderSchema = z.object({
  name: z.string().min(1, '请填写名称'),
  vendorId: z.string().default('custom'),
  protocol: z.enum(['openai-compatible', 'anthropic-messages', 'ollama']),
  baseUrl: z.string().min(1, '请填写接口地址'),
  apiKey: z.string().optional(),
})

type ProviderFormValues = z.infer<typeof ProviderSchema>

interface EnabledModel {
  id: number
  provider_id?: string
  model_name: string
  model_id?: string
  display_name?: string
  is_default?: number
  test_status?: string
}

// 分享导入的初始模型（AddModelDialog 打开时预填勾选，不自动保存）
interface InitialModel {
  model_id: string
  display_name: string
  context_window: number
}

const baseUrlError = (value: string): string | undefined => {
  const url = trimUrl(value)
  if (!url) return '请填写接口地址'
  if (!isValidHttpUrl(url)) return '地址格式不正确'
  if (!isLocalUrl(url) && !/^https:\/\//i.test(url)) return '非本机地址必须使用 HTTPS'
  return undefined
}

const ProviderForm = ({ isCreate = false }: { isCreate?: boolean }) => {
  const { id } = useParams()
  const navigate = useNavigate()
  const isEditMode = !isCreate

  const loadProviderById = useProviderStore(state => state.loadProviderById)
  const updateProvider = useProviderStore(state => state.updateProvider)
  const addNewProvider = useProviderStore(state => state.addNewProvider)
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState(false)
  const [showKey, setShowKey] = useState(false)
  const [hasStoredKey, setHasStoredKey] = useState(false)
  const [maskedKey, setMaskedKey] = useState<string | undefined>(undefined)
  const loadModelsById = useModelStore(state => state.loadModelsById)
  const setModelDefault = useModelStore(state => state.setModelDefault)
  const [models, setModels] = useState<EnabledModel[]>([])
  const [addModelOpen, setAddModelOpen] = useState(false)
  // 分享导入预填（仅创建态）
  const location = useLocation()
  const routeState = location.state as
    | { importedShare?: DecodedModelShare; initialModels?: InitialModel[] }
    | null
  const importedShare = routeState?.importedShare
  const [initialModels, setInitialModels] = useState<InitialModel[]>([])
  const [importedBanner, setImportedBanner] = useState<string | null>(null)

  const providerForm = useForm<ProviderFormValues>({
    resolver: zodResolver(ProviderSchema),
    defaultValues: {
      name: '',
      vendorId: 'custom',
      protocol: 'openai-compatible',
      baseUrl: '',
      apiKey: '',
    },
  })

  const vendorId = providerForm.watch('vendorId')
  const protocol = providerForm.watch('protocol')
  const baseUrl = providerForm.watch('baseUrl')
  const apiKey = providerForm.watch('apiKey')
  const needsKey = protocol !== 'ollama'
  const selectedVendor = getVendor(vendorId)

  useEffect(() => {
    const load = async () => {
      if (isEditMode) {
        const data = await loadProviderById(id!)
        providerForm.reset({
          name: data.name || data.displayName || '',
          vendorId: data.vendorId || 'custom',
          protocol: (data.protocol as ProtocolId) || 'openai-compatible',
          baseUrl: data.baseUrl || '',
          apiKey: '',
        })
        setHasStoredKey(Boolean(data.hasApiKey))
        setMaskedKey(data.apiKeyMasked)
        const list = id ? await loadModelsById(id) : []
        if (list) setModels(list as EnabledModel[])
        // 创建态保存后跳转：透传导入的预填模型，供「添加模型」弹窗预选
        if (routeState?.initialModels?.length) {
          setInitialModels(routeState.initialModels)
          setImportedBanner(
            `供应商已创建，点击「添加模型」可直接勾选导入的 ${routeState.initialModels.length} 个模型。`,
          )
        }
      } else {
        if (importedShare) {
          // imported 态预填：厂商/协议/地址与模型勾选，不自动保存；密钥仍需用户填写
          const initial: InitialModel[] = importedShare.models.map(item => ({
            model_id: item.id,
            display_name: item.display_name,
            context_window: item.context_window,
          }))
          setInitialModels(initial)
          setImportedBanner(`已导入 ${importedShare.display_name} 的 ${initial.length} 个模型，保存供应商后可直接勾选确认。`)
          providerForm.reset({
            name: importedShare.display_name || '',
            vendorId: importedShare.vendor_id || 'custom',
            protocol: (importedShare.protocol as ProtocolId) || 'openai-compatible',
            baseUrl: importedShare.base_url || '',
            apiKey: '',
          })
        } else {
          providerForm.reset({
            name: '',
            vendorId: 'custom',
            protocol: 'openai-compatible',
            baseUrl: '',
            apiKey: '',
          })
        }
      }
      setLoading(false)
    }
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // 选择厂商网格：带出协议与地址；Bedrock 置灰；未知厂商地址留空不臆造
  const handleSelectVendor = (vendorIdValue: string) => {
    const vendor = getVendor(vendorIdValue)
    if (!vendor || vendor.unsupported) return
    const protocolValue = (PROTOCOLS.some(p => p.id === vendor.protocol)
      ? vendor.protocol
      : 'openai-compatible') as ProtocolId
    providerForm.setValue('vendorId', vendor.id, { shouldDirty: true })
    providerForm.setValue('protocol', protocolValue, { shouldDirty: true })
    if (vendor.base_url) providerForm.setValue('baseUrl', vendor.base_url, { shouldDirty: true })
    const currentName = providerForm.getValues('name')
    if (!currentName || getVendor(providerForm.getValues('vendorId') as string)?.custom !== false) {
      // 切换厂商时同步名称（用户自定义名称不覆盖）
    }
    if (!currentName) providerForm.setValue('name', vendor.custom ? '' : vendor.name, { shouldDirty: true })
  }

  const handleProtocolChange = (value: string) => {
    providerForm.setValue('protocol', value as ProtocolId, { shouldDirty: true })
  }

  const handelDelete = async (modelId: number) => {
    if (!window.confirm('确定要删除这个模型吗？')) return
    try {
      await deleteModelById(modelId)
      await refreshEnabledModels()
      toast.success('删除成功')
    } catch {
      toast.error('删除异常')
    }
  }

  const refreshEnabledModels = async () => {
    if (!id) return
    const nextModels = await loadModelsById(id)
    if (nextModels) setModels(nextModels as EnabledModel[])
  }

  // 已保存模型上直接设为供应商默认（POST /models/default）
  const handleSetDefault = async (modelId?: string) => {
    if (!id || !modelId) return
    if (!window.confirm(`确定将「${modelId}」设为该供应商的默认模型吗？`)) return
    try {
      await setModelDefault(id, modelId)
      await refreshEnabledModels()
      toast.success('默认模型已更新')
    } catch {
      toast.error('设置默认模型失败')
    }
  }

  const testStatusLabel = (status?: string): { text: string; className: string } | null => {
    if (status === 'ok') return { text: '已通过', className: 'bg-green-100 text-green-700' }
    if (status === 'failed') return { text: '未通过', className: 'bg-red-100 text-red-700' }
    if (status === 'testing') return { text: '测试中', className: 'bg-blue-100 text-blue-700' }
    return null
  }

  const validateBeforeAction = (): ProviderFormValues | null => {
    const values = providerForm.getValues()
    const urlError = baseUrlError(values.baseUrl)
    if (!values.name?.trim()) {
      toast.error('请填写名称')
      return null
    }
    if (urlError) {
      toast.error(urlError)
      return null
    }
    if (protocol !== 'ollama' && !(values.apiKey || '').trim() && !hasStoredKey) {
      toast.error('请填写 API Key')
      return null
    }
    return values
  }

  // 测试连通性：优先用表单中临时配置（含刚填写的 Key），编辑态留空则用库内密钥
  const handleTest = async () => {
    const values = validateBeforeAction()
    if (!values) return
    try {
      setTesting(true)
      const typedKey = (values.apiKey || '').trim()
      if (isEditMode && !typedKey && hasStoredKey) {
        await testSavedConnection({ provider_id: id!, model_id: models[0]?.model_id || '' })
      } else {
        await testConnection({
          api_key: typedKey,
          base_url: trimUrl(values.baseUrl),
          protocol: values.protocol,
          model_id: models[0]?.model_id || '',
        })
      }
      toast.success('连接测试通过')
    } catch (error: unknown) {
      const message =
        typeof error === 'object' && error !== null && 'response' in error
          ? (error as { response?: { data?: { msg?: string } } }).response?.data?.msg
          : undefined
      const fallback =
        typeof error === 'object' && error !== null && 'message' in error
          ? String((error as { message?: string }).message || '')
          : ''
      toast.error(`测试失败：${message || fallback || '未知错误'}`)
    } finally {
      setTesting(false)
    }
  }

  // 保存 Provider：编辑态留空 Key 不发送（绝不回传掩码），由后端保留库内密钥
  const onProviderSubmit = async (values: ProviderFormValues) => {
    const urlError = baseUrlError(values.baseUrl)
    if (urlError) {
      toast.error(urlError)
      return
    }
    const typedKey = (values.apiKey || '').trim()
    if (protocol !== 'ollama' && !typedKey && !(isEditMode && hasStoredKey)) {
      toast.error('请填写 API Key')
      return
    }
    const vendor = getVendor(values.vendorId)
    const authType = values.protocol === 'ollama' ? 'none' : 'api_key'
    if (isEditMode) {
      const payload: Record<string, unknown> = {
        id: id!,
        name: values.name.trim(),
        display_name: values.name.trim(),
        vendor_id: values.vendorId,
        protocol: values.protocol,
        base_url: trimUrl(values.baseUrl),
        logo: vendor?.id || 'custom',
        auth_type: authType,
      }
      // 仅在填写了新 Key 时提交；留空=保留；掩码串永不上传
      if (typedKey) payload.api_key = typedKey
      await updateProvider(payload as never)
      setHasStoredKey(protocol !== 'ollama' ? true : hasStoredKey)
      toast.success('更新供应商成功')
    } else {
      const createdProvider = await addNewProvider({
        name: values.name.trim(),
        displayName: values.name.trim(),
        vendorId: values.vendorId,
        protocol: values.protocol,
        baseUrl: trimUrl(values.baseUrl),
        logo: vendor?.id || 'custom',
        authType: authType,
        apiKey: typedKey,
      } as never)
      if (!createdProvider?.id) {
        throw new Error('新增供应商后未返回有效 id')
      }
      toast.success('新增供应商成功')
      navigate(`/settings/model/${createdProvider.id}`, {
        state: initialModels.length ? { initialModels } : undefined,
      })
    }
  }

  if (loading) return <div className="p-4 text-sm text-on-surface-variant">加载中...</div>

  return (
    <div className="flex min-h-full min-w-0 flex-col gap-5 bg-surface-container/40 p-3 pb-8 md:gap-8 md:bg-white md:p-6">
      {importedBanner && (
        <div
          data-imported-banner
          className="flex max-w-2xl items-start justify-between gap-3 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700"
        >
          <span>{importedBanner}</span>
          <button
            type="button"
            className="shrink-0 text-blue-400 hover:text-blue-600"
            aria-label="关闭导入提示"
            onClick={() => setImportedBanner(null)}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {/* Provider信息表单 */}
      <Form {...providerForm}>
        <form
          onSubmit={providerForm.handleSubmit(onProviderSubmit)}
          className="flex w-full max-w-2xl flex-col gap-4 rounded-2xl border border-border-subtle/70 bg-white p-4 shadow-[0_8px_28px_rgba(15,23,42,0.05)] md:rounded-none md:border-0 md:p-0 md:shadow-none"
        >
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div className="space-y-1">
              <div className="text-lg font-bold">
                {isEditMode ? '编辑模型供应商' : '新增模型供应商'}
              </div>
              <div className="text-xs text-on-surface-variant">
                选择厂商自动带出协议与接口地址；API 密钥加密存储，不会在分享与日志中出现。
              </div>
            </div>
            <div data-provider-header-actions className="flex shrink-0 flex-col gap-2 sm:flex-row">
              <Button type="submit" className="w-full sm:w-auto">
                {isEditMode ? '保存修改' : '保存创建'}
              </Button>
            </div>
          </div>

          {/* 厂商网格：22 家内置预设，Bedrock 置灰，自定义加宽 */}
          <div className="flex flex-col gap-1.5 md:flex-row md:gap-4">
            <FormLabel className="text-left md:w-24 md:pt-2 md:text-right">厂商</FormLabel>
            <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-3" data-vendor-grid>
              {MODEL_VENDORS.map(vendor => {
                const active = vendorId === vendor.id
                const unsupported = Boolean(vendor.unsupported)
                return (
                  <button
                    key={vendor.id}
                    type="button"
                    data-vendor-id={vendor.id}
                    disabled={unsupported}
                    title={unsupported ? vendor.unsupported : vendor.base_url || vendor.url_note}
                    onClick={() => handleSelectVendor(vendor.id)}
                    className={[
                      'truncate rounded-lg border px-2.5 py-2 text-left text-xs transition',
                      vendor.custom ? 'sm:col-span-3' : '',
                      unsupported
                        ? 'cursor-not-allowed border-border-subtle bg-neutral-50 text-neutral-400'
                        : active
                          ? 'border-blue-500 bg-blue-50 text-blue-700'
                          : 'border-border-subtle bg-white text-on-surface hover:border-blue-300',
                    ].join(' ')}
                  >
                    {vendor.name}
                  </button>
                )
              })}
            </div>
          </div>
          {selectedVendor?.url_note && (
            <div className="md:pl-28">
              <span className="text-xs text-amber-600">{selectedVendor.url_note}</span>
            </div>
          )}

          <FormField
            control={providerForm.control}
            name="name"
            render={({ field }) => (
              <FormItem className="flex min-w-0 flex-col gap-1.5 md:flex-row md:items-center md:gap-4">
                <FormLabel className="text-left md:w-24 md:text-right">名称</FormLabel>
                <FormControl>
                  <Input {...field} className="flex-1" placeholder="为该供应商起一个名字" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={providerForm.control}
            name="protocol"
            render={({ field }) => (
              <FormItem className="flex min-w-0 flex-col gap-1.5 md:flex-row md:items-center md:gap-4">
                <FormLabel className="text-left md:w-24 md:text-right">协议</FormLabel>
                <div className="flex-1">
                  <Select value={field.value} onValueChange={handleProtocolChange}>
                    <FormControl>
                      <SelectTrigger data-protocol-select className="w-full">
                        <SelectValue placeholder="选择协议类型" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {PROTOCOLS.map(item => (
                        <SelectItem key={item.id} value={item.id}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription className="text-xs">
                    {PROTOCOLS.find(p => p.id === field.value)?.needs_key
                      ? '该协议需要 API 密钥'
                      : '本地服务，无需 API 密钥'}
                  </FormDescription>
                </div>
                <FormMessage />
              </FormItem>
            )}
          />

          {needsKey && (
            <FormField
              control={providerForm.control}
              name="apiKey"
              render={({ field }) => (
                <FormItem className="flex min-w-0 flex-col gap-1.5 md:flex-row md:items-center md:gap-4">
                  <FormLabel className="text-left md:w-24 md:text-right">API Key</FormLabel>
                  <div className="relative flex-1">
                    <FormControl>
                      <Input
                        {...field}
                        type={showKey ? 'text' : 'password'}
                        className="w-full pr-9"
                        autoComplete="off"
                        data-api-key-input
                        placeholder={
                          isEditMode && hasStoredKey
                            ? `已保存密钥（${maskedKey || '••••'}）；留空保留不修改`
                            : '填写 API 密钥'
                        }
                      />
                    </FormControl>
                    <button
                      type="button"
                      data-key-toggle
                      onClick={() => setShowKey(previous => !previous)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600"
                      aria-label={showKey ? '隐藏密钥' : '显示密钥'}
                    >
                      {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          <FormField
            control={providerForm.control}
            name="baseUrl"
            render={({ field }) => (
              <FormItem className="flex min-w-0 flex-col gap-1.5 md:flex-row md:items-center md:gap-4">
                <FormLabel className="text-left md:w-24 md:text-right">API地址</FormLabel>
                <FormControl>
                  <Input {...field} className="flex-1" placeholder="https://api.example.com/v1" />
                </FormControl>
                <Button
                  type="button"
                  onClick={handleTest}
                  variant="ghost"
                  disabled={testing}
                  className="w-full md:w-auto"
                >
                  {testing ? '测试中...' : '测试连通性'}
                </Button>
                <FormMessage />
              </FormItem>
            )}
          />
          {baseUrl && baseUrlError(baseUrl) && (
            <div className="md:pl-28">
              <span className="text-xs text-red-500">{baseUrlError(baseUrl)}</span>
            </div>
          )}
          {needsKey && !apiKey && isEditMode && hasStoredKey && (
            <div className="md:pl-28">
              <span className="text-xs text-on-surface-variant">密钥已加密保存，留空提交不会修改。</span>
            </div>
          )}
        </form>
      </Form>

      {/* 模型信息表单 */}
      <div className="flex w-full max-w-2xl flex-col gap-4 rounded-2xl border border-border-subtle/70 bg-white p-4 shadow-[0_8px_28px_rgba(15,23,42,0.05)] md:rounded-none md:border-0 md:p-0 md:shadow-none">
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-3">
            <span className="font-bold">模型列表</span>
            <Button type="button" onClick={() => setAddModelOpen(true)} disabled={!id}>
              添加模型
            </Button>
          </div>
          {!isEditMode && (
            <div className="text-xs text-on-surface-variant">保存供应商后即可拉取并多选模型。</div>
          )}
          <div className="flex min-w-0 flex-wrap gap-2 rounded p-0 md:p-2.5">
            {models &&
              models.map(model => {
                const statusTag = testStatusLabel(model.test_status)
                return (
                  <span
                    key={model.id}
                    data-saved-model={model.model_id}
                    className="inline-flex min-w-0 max-w-full flex-wrap items-center gap-1.5 rounded-xl bg-blue-50 px-2.5 py-2 text-sm text-blue-700"
                  >
                    <span className="min-w-0 max-w-full truncate">
                      {model.display_name || model.model_name}
                    </span>
                    {model.is_default ? (
                      <span className="inline-flex items-center gap-0.5 rounded bg-green-100 px-1.5 py-0.5 text-[10px] text-green-700">
                        <Star className="h-2.5 w-2.5 fill-green-600" />
                        默认
                      </span>
                    ) : (
                      <button
                        type="button"
                        data-set-default={model.model_id}
                        onClick={() => handleSetDefault(model.model_id)}
                        title="设为供应商默认模型"
                        className="text-blue-300 hover:text-green-600"
                      >
                        <Star className="h-3 w-3" />
                      </button>
                    )}
                    {statusTag && (
                      <span
                        data-model-status={model.model_id}
                        className={`rounded px-1.5 py-0.5 text-[10px] ${statusTag.className}`}
                      >
                        {statusTag.text}
                      </span>
                    )}
                    <button type="button" onClick={() => handelDelete(model.id)} className="hover:text-blue-900">
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                )
              })}
          </div>
        </div>
        {id && (
          <AddModelDialog
            providerId={id}
            open={addModelOpen}
            onOpenChange={(openValue) => {
              setAddModelOpen(openValue)
              if (!openValue) setInitialModels([])
            }}
            onSaved={refreshEnabledModels}
            config={{ protocol, baseUrl: trimUrl(baseUrl) }}
            apiKey={(apiKey || '').trim()}
            hasStoredKey={hasStoredKey}
            initialModels={initialModels}
          />
        )}
      </div>
    </div>
  )
}

export default ProviderForm
