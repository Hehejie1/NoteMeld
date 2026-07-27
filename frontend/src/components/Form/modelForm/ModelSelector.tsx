import { useState, useEffect } from 'react'
import { useModelStore } from '@/store/modelStore'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import toast from 'react-hot-toast'
import { fetchModelsByConfig } from '@/services/model'

interface ModelSelectorProps {
  providerId?: string
  config?: {
    apiKey?: string
    baseUrl?: string
    name?: string
  }
  onSaved?: () => Promise<void> | void
  canSave?: boolean
}

export function ModelSelector({ providerId, config, onSaved, canSave = true }: ModelSelectorProps) {
  const { models, loading, selectedModel, loadModels, setSelectedModel, addNewModel } =
    useModelStore()
  const [search, setSearch] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [localLoading, setLocalLoading] = useState(false)

  const filteredModels = models.filter(model => {
    const keywords = search.trim().toLowerCase().split(/\s+/)
    const target = model.id.toLowerCase()
    return keywords.every(kw => target.includes(kw))
  })

  useEffect(() => {
    if (providerId) {
      loadModels(providerId)
    }
  }, [providerId])

  const handleRefreshByConfig = async () => {
    if (!config?.baseUrl) {
      toast.error('请先填写 API 地址')
      return
    }
    try {
      setLocalLoading(true)
      const res = await fetchModelsByConfig({
        api_key: config.apiKey,
        base_url: config.baseUrl,
        name: config.name,
      })
      let modelList: any[] = []
      if (Array.isArray(res.models)) {
        modelList = res.models
      } else if (res.models?.data && Array.isArray(res.models.data)) {
        modelList = res.models.data
      }
      useModelStore.setState({ models: modelList })
    } catch (error: any) {
      useModelStore.setState({ models: [] })
      const msg = error?.response?.data?.msg || error?.message || '刷新模型失败'
      toast.error(msg)
    } finally {
      setLocalLoading(false)
    }
  }

  const isLoading = loading || localLoading

  const handleSubmit = async () => {
    if (!providerId) {
      toast.error('请先保存供应商')
      return
    }
    if (!selectedModel) {
      toast.error('请选择一个模型')
      return
    }
    try {
      setSubmitting(true)
      await addNewModel(providerId, selectedModel)
      await onSaved?.()
      toast.success('保存模型成功 🎉')
    } catch (error) {
      toast.error('保存失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleRefresh = () => {
    if (providerId) {
      loadModels(providerId)
    } else {
      handleRefreshByConfig()
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <span className="font-bold">模型列表</span>
        <div data-model-list-header-actions>
          <Button
            onClick={handleSubmit}
            disabled={submitting || !selectedModel || !canSave || !providerId}
            className="w-full sm:w-auto"
          >
            {submitting ? '保存中...' : '保存模型'}
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-2 font-bold sm:flex-row sm:items-center">
        <span>选择模型</span>
        <Button
          variant="ghost"
          type="button"
          onClick={handleRefresh}
          disabled={isLoading}
          className="w-full sm:w-auto"
        >
          {isLoading ? '加载中...' : '刷新模型'}
        </Button>
      </div>

      <Select value={selectedModel} onValueChange={setSelectedModel}>
        <SelectTrigger className="w-full min-w-0">
          <SelectValue placeholder="请选择模型" />
        </SelectTrigger>
        <SelectContent className="max-w-[calc(100vw-32px)]">
          <div className="p-2">
            <Input
              placeholder="搜索模型..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="h-8"
            />
          </div>
          {filteredModels.map((model, index) => (
            <SelectItem key={`${model.id}-${index}`} value={model.id} className="max-w-full">
              {model.id}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
