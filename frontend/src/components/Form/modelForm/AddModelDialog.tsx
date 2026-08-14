import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { ModelSelector } from '@/components/Form/modelForm/ModelSelector'
import { useModelStore } from '@/store/modelStore'
import { fetchModelDefaults } from '@/services/model'

interface AddModelDialogProps {
  providerId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: () => Promise<void> | void
}

const FALLBACK_RUNTIME_CONFIG = { contextWindowTokens: 4096, supportsVision: false, supportsStream: true }

export function AddModelDialog({ providerId, open, onOpenChange, onSaved }: AddModelDialogProps) {
  const addNewModel = useModelStore(state => state.addNewModel)
  const [selectedModel, setSelectedModel] = useState('')
  const [contextWindowTokens, setContextWindowTokens] = useState(String(FALLBACK_RUNTIME_CONFIG.contextWindowTokens))
  const [supportsVision, setSupportsVision] = useState(FALLBACK_RUNTIME_CONFIG.supportsVision)
  const [supportsStream, setSupportsStream] = useState(FALLBACK_RUNTIME_CONFIG.supportsStream)
  const [loadingDefaults, setLoadingDefaults] = useState(false)
  const [saving, setSaving] = useState(false)
  const requestVersionRef = useRef(0)
  const runtimeConfigDirtyRef = useRef(false)
  const loadingDefaultsRef = useRef(false)

  const updateLoadingDefaults = (loading: boolean) => {
    loadingDefaultsRef.current = loading
    setLoadingDefaults(loading)
  }

  const resetRuntimeConfig = () => {
    runtimeConfigDirtyRef.current = false
    setContextWindowTokens(String(FALLBACK_RUNTIME_CONFIG.contextWindowTokens))
    setSupportsVision(FALLBACK_RUNTIME_CONFIG.supportsVision)
    setSupportsStream(FALLBACK_RUNTIME_CONFIG.supportsStream)
  }

  useEffect(() => {
    requestVersionRef.current += 1
    updateLoadingDefaults(false)
    if (!open) return
    setSelectedModel('')
    resetRuntimeConfig()
  }, [open])

  const handleModelChange = async (modelName: string) => {
    setSelectedModel(modelName)
    resetRuntimeConfig()
    const requestVersion = ++requestVersionRef.current
    updateLoadingDefaults(true)
    try {
      const defaults = await fetchModelDefaults(modelName)
      if (requestVersion !== requestVersionRef.current || runtimeConfigDirtyRef.current) return
      setContextWindowTokens(String(defaults.context_window_tokens))
      setSupportsVision(defaults.supports_vision)
      setSupportsStream(defaults.supports_stream)
    } catch {
      if (requestVersion === requestVersionRef.current) toast.error('未能获取模型默认配置，已使用安全默认值')
    } finally {
      if (requestVersion === requestVersionRef.current) updateLoadingDefaults(false)
    }
  }

  const markRuntimeConfigDirty = () => { runtimeConfigDirtyRef.current = true }

  const handleSave = async () => {
    if (loadingDefaultsRef.current) return
    const parsedContextWindowTokens = Number(contextWindowTokens)
    if (!selectedModel) return toast.error('请选择一个模型')
    if (!Number.isInteger(parsedContextWindowTokens) || parsedContextWindowTokens < 512 || parsedContextWindowTokens > 4_000_000) {
      return toast.error('上下文长度需在 512 到 4,000,000 之间')
    }
    try {
      setSaving(true)
      await addNewModel({
        provider_id: providerId,
        model_name: selectedModel,
        context_window_tokens: parsedContextWindowTokens,
        supports_vision: supportsVision,
        supports_stream: supportsStream,
      })
      await onSaved?.()
      toast.success('添加模型成功 🎉')
      onOpenChange(false)
    } catch {
      toast.error('添加模型失败')
    } finally {
      setSaving(false)
    }
  }

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      requestVersionRef.current += 1
      updateLoadingDefaults(false)
    }
    onOpenChange(nextOpen)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader><DialogTitle>添加模型</DialogTitle><DialogDescription>确认模型的运行配置后保存；建议值可按实际服务能力调整。</DialogDescription></DialogHeader>
        <div className="flex flex-col gap-5 py-1">
          <div className="grid gap-2"><Label>选择模型</Label><ModelSelector providerId={providerId} value={selectedModel} onValueChange={handleModelChange} /></div>
          <div className="grid gap-2"><Label htmlFor="model-context-window">上下文长度</Label><Input id="model-context-window" type="number" min={512} max={4_000_000} value={contextWindowTokens} onChange={event => { markRuntimeConfigDirty(); setContextWindowTokens(event.target.value) }} /></div>
          <div className="flex items-center justify-between gap-4"><Label htmlFor="model-supports-vision">支持图像</Label><Switch id="model-supports-vision" checked={supportsVision} onCheckedChange={checked => { markRuntimeConfigDirty(); setSupportsVision(checked) }} /></div>
          <div className="flex items-center justify-between gap-4"><Label htmlFor="model-supports-stream">支持流式</Label><Switch id="model-supports-stream" checked={supportsStream} onCheckedChange={checked => { markRuntimeConfigDirty(); setSupportsStream(checked) }} /></div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={saving}>取消</Button>
          <Button type="button" onClick={handleSave} disabled={saving || loadingDefaults || !selectedModel}>{saving ? '添加中...' : loadingDefaults ? '读取配置中...' : '添加模型'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
