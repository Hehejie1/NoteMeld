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
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useNavigate, useParams } from 'react-router-dom'
import { useProviderStore } from '@/store/providerStore'
import { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import {
  testConnection,
  deleteModelById,
  fetchProviderTemplates,
  saveProviderTemplate,
} from '@/services/model.ts'
import { X } from 'lucide-react'
import { useModelStore } from '@/store/modelStore'
import {
  mergeProviderTemplates,
  ProviderTemplate,
  providerTemplates,
} from '@/components/Form/modelForm/providerTemplates'
import ProviderNameCombobox from '@/components/Form/modelForm/ProviderNameCombobox'
import { AddModelDialog } from '@/components/Form/modelForm/AddModelDialog'

// ✅ Provider表单schema
const ProviderSchema = z.object({
  name: z.string().min(2, '名称不能少于 2 个字符'),
  logo: z.string().optional(),
  apiKey: z.string().optional(),
  baseUrl: z.string().url('必须是合法 URL'),
})

type ProviderFormValues = z.infer<typeof ProviderSchema>

interface EnabledModel {
  id: number
  provider_id?: string
  model_name: string
}
const ProviderForm = ({ isCreate = false }: { isCreate?: boolean }) => {
  let { id } = useParams()
  const navigate = useNavigate()
  const isEditMode = !isCreate

  const loadProviderById = useProviderStore(state => state.loadProviderById)
  const updateProvider = useProviderStore(state => state.updateProvider)
  const addNewProvider = useProviderStore(state => state.addNewProvider)
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState(false)
  const loadModelsById= useModelStore(state => state.loadModelsById)
  const [models, setModels]= useState<EnabledModel[]>([])
  const [addModelOpen, setAddModelOpen] = useState(false)
  const [savedTemplates, setSavedTemplates] = useState<ProviderTemplate[]>([])
  const allProviderTemplates = useMemo(
    () => mergeProviderTemplates(providerTemplates, savedTemplates),
    [savedTemplates],
  )

  const allowsEmptyApiKey = () => {
    const values = providerForm.getValues()
    const providerName = (values.name || '').trim().toLowerCase()
    const baseUrl = (values.baseUrl || '').trim().toLowerCase()
    return providerName === 'ollama' || baseUrl.includes('127.0.0.1:11434') || baseUrl.includes('localhost:11434')
  }

  const providerForm = useForm<ProviderFormValues>({
    resolver: zodResolver(ProviderSchema),
    defaultValues: {
      name: '',
      logo: 'custom',
      apiKey: '',
      baseUrl: '',
    },
  })

  useEffect(() => {

    const load = async () => {
      if (isEditMode) {

        const data = await loadProviderById(id!)
        providerForm.reset(data)
      } else {
        providerForm.reset({
          name: '',
          logo: 'custom',
          apiKey: '',
          baseUrl: '',
        })
      }
      const models = id ? await loadModelsById(id) : []
      if (models) {
        setModels(models)
      }
      setLoading(false)
    }
    load()
  }, [id])

  useEffect(() => {
    const loadTemplates = async () => {
      try {
        const templates = await fetchProviderTemplates()
        setSavedTemplates((templates || []).map((template: {
          id?: string
          name: string
          logo: string
          base_url: string
        }) => ({
          key: template.id || template.name,
          name: template.name,
          logo: template.logo,
          baseUrl: template.base_url,
        })))
      } catch (e) {
        console.error('加载供应商模板失败', e)
      }
    }
    loadTemplates()
  }, [])

  const applyProviderTemplate = (template: ProviderTemplate) => {
    providerForm.reset({
      name: template.name,
      logo: template.logo,
      apiKey: '',
      baseUrl: template.baseUrl,
    }, { keepDirty: true })
  }

  const handleNameEnter = () => {
    providerForm.handleSubmit(onProviderSubmit)()
  }

  const handleSaveTemplate = async () => {
    const values = providerForm.getValues()
    const isValid = await providerForm.trigger(['name', 'baseUrl'])
    if (!isValid) return
    await saveProviderTemplate({
      name: values.name,
      logo: values.logo || 'custom',
      base_url: values.baseUrl,
    })
    const savedTemplate = {
      key: values.name,
      name: values.name,
      logo: values.logo || 'custom',
      baseUrl: values.baseUrl,
    }
    setSavedTemplates(previous => mergeProviderTemplates(previous, [savedTemplate]))
    toast.success('已保存为模板')
  }
  const handelDelete=async (modelId)=>{
    if (!window.confirm('确定要删除这个模型吗？')) return

    try {
      await deleteModelById(modelId)
      await refreshEnabledModels()
      toast.success('删除成功')

    } catch (e) {
      toast.error('删除异常')
    }
  }

  const refreshEnabledModels = async () => {
    if (!id) return
    const nextModels = await loadModelsById(id)
    if (nextModels) {
      setModels(nextModels as EnabledModel[])
    }
  }

  // 测试连通性
  const handleTest = async () => {
    const values = providerForm.getValues()
    const apiKeyOptional = allowsEmptyApiKey()
    if (!values.baseUrl || (!apiKeyOptional && !values.apiKey)) {
      toast.error(apiKeyOptional ? '请填写 Base URL' : '请填写 API Key 和 Base URL')
      return
    }
    try {
      setTesting(true)
      await testConnection({
        api_key: values.apiKey || '',
        base_url: values.baseUrl,
      })

      toast.success('测试连通性成功 🎉')

    } catch (error: unknown) {
      const message =
        typeof error === 'object' && error !== null && 'response' in error
          ? (error as { response?: { data?: { msg?: string } } }).response?.data?.msg
          : undefined
      const fallback =
        typeof error === 'object' && error !== null && 'message' in error
          ? String((error as { message?: string }).message || '')
          : ''
      toast.error(`连接失败: ${message || fallback || '未知错误'}`)
    } finally {
      setTesting(false)
    }
  }

  // 保存Provider信息
  const onProviderSubmit = async (values: ProviderFormValues) => {
    const apiKeyOptional = allowsEmptyApiKey()
    if (!values.baseUrl || (!apiKeyOptional && !values.apiKey)) {
      toast.error(apiKeyOptional ? '请填写 Base URL' : '请填写 API Key 和 Base URL')
      return
    }
    if (isEditMode) {
      await updateProvider({ ...values, id: id! })
      toast.success('更新供应商成功')
    } else {
      const createdProvider = await addNewProvider({ ...values })
      if (!createdProvider?.id) {
        throw new Error('新增供应商后未返回有效 id')
      }
      toast.success('新增供应商成功')
      navigate(`/settings/model/${createdProvider.id}`)
    }
    // 刷新页面

  }

  if (loading) return <div className="p-4 text-sm text-on-surface-variant">加载中...</div>

  return (
    <div className="flex min-h-full min-w-0 flex-col gap-5 bg-surface-container/40 p-3 pb-8 md:gap-8 md:bg-white md:p-6">
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
                配置兼容 OpenAI SDK 的模型服务，并为知识抽取选择可用模型。
              </div>
            </div>
            <div data-provider-header-actions className="flex shrink-0 flex-col gap-2 sm:flex-row">
              <Button type="submit" disabled={!providerForm.formState.isDirty} className="w-full sm:w-auto">
                {isEditMode ? '保存修改' : '保存创建'}
              </Button>
              <Button type="button" variant="outline" onClick={handleSaveTemplate} className="w-full sm:w-auto">
                保存为模板
              </Button>
            </div>
          </div>
          <FormField
            control={providerForm.control}
            name="name"
            render={({ field }) => (
              <FormItem className="flex min-w-0 flex-col gap-1.5 md:flex-row md:items-center md:gap-4">
                <FormLabel className="text-left md:w-24 md:text-right">名称</FormLabel>
                <FormControl>
                  <ProviderNameCombobox
                    value={field.value}
                    templates={allProviderTemplates}
                    onChange={field.onChange}
                    onSelectTemplate={applyProviderTemplate}
                    onEnter={handleNameEnter}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={providerForm.control}
            name="apiKey"
            render={({ field }) => (
              <FormItem className="flex min-w-0 flex-col gap-1.5 md:flex-row md:items-center md:gap-4">
                <FormLabel className="text-left md:w-24 md:text-right">API Key</FormLabel>
                <FormControl>
                  <Input {...field} className="flex-1" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={providerForm.control}
            name="baseUrl"
            render={({ field }) => (
              <FormItem className="flex min-w-0 flex-col gap-1.5 md:flex-row md:items-center md:gap-4">
                <FormLabel className="text-left md:w-24 md:text-right">API地址</FormLabel>
                <FormControl>
                  <Input {...field} className="flex-1" />
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
          <div className="flex min-w-0 flex-wrap gap-2 rounded p-0 md:p-2.5">
            {
              models && models.map(model => {
                return (
                  <span key={model.id} className="inline-flex min-w-0 max-w-full flex-wrap items-center gap-2 rounded-xl bg-blue-50 px-2.5 py-2 text-sm text-blue-700">
                    <span className="min-w-0 max-w-full truncate">{model.model_name}</span>
                    <button type="button" onClick={() => handelDelete(model.id)} className="hover:text-blue-900">
                      <X className="h-3 w-3" />
                    </button>
                  </span>

                )
              })
            }

          </div>
        </div>
        {id && <AddModelDialog providerId={id} open={addModelOpen} onOpenChange={setAddModelOpen} onSaved={refreshEnabledModels} />}
      </div>
    </div>
  )
}

export default ProviderForm
