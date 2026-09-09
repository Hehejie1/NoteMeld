import { useEffect, useMemo, useState } from 'react'
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

interface ModelSelectorProps {
  providerId: string
  value: string
  onValueChange: (modelName: string) => void
}

export function ModelSelector({ providerId, value, onValueChange }: ModelSelectorProps) {
  const { models, loading, loadModels } = useModelStore()
  const [search, setSearch] = useState('')
  const filteredModels = useMemo(() => {
    const keywords = search.trim().toLowerCase().split(/\s+/).filter(Boolean)
    return models.filter(model => keywords.every(keyword => model.id.toLowerCase().includes(keyword)))
  }, [models, search])

  useEffect(() => {
    loadModels(providerId)
  }, [providerId, loadModels])

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex flex-col gap-2 font-bold sm:flex-row sm:items-center">
        <span>选择模型</span>
        <Button type="button" variant="ghost" onClick={() => loadModels(providerId)} disabled={loading} className="w-full sm:w-auto">
          {loading ? '加载中...' : '刷新模型'}
        </Button>
      </div>
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger className="w-full min-w-0"><SelectValue placeholder="请选择模型" /></SelectTrigger>
        <SelectContent className="max-w-[calc(100vw-32px)]">
          <div className="p-2"><Input placeholder="搜索模型..." value={search} onChange={event => setSearch(event.target.value)} className="h-8" /></div>
          {filteredModels.map((model, index) => <SelectItem key={`${model.id}-${index}`} value={model.id} className="max-w-full">{model.id}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  )
}
