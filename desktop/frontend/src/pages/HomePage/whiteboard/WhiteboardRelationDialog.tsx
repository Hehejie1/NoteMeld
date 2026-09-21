import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type {
  WhiteboardLineType,
  WhiteboardRelation,
  WhiteboardRelationDirection,
  WhiteboardRelationPatch,
  WhiteboardRelationType,
  WhiteboardSourceRef,
} from './types'

interface WhiteboardRelationDialogProps {
  open: boolean
  relation: WhiteboardRelation | null
  onOpenChange: (open: boolean) => void
  onSubmit: (patch: WhiteboardRelationPatch) => Promise<void>
}

const parseSources = (raw: string): WhiteboardSourceRef[] => {
  if (!raw.trim()) return []
  const parsed: unknown = JSON.parse(raw)
  if (!Array.isArray(parsed)) throw new Error('来源必须是 JSON 数组')
  return parsed.map(item => {
    if (!item || typeof item !== 'object') throw new Error('来源条目格式不正确')
    const source = item as Partial<WhiteboardSourceRef>
    if (!source.source_id?.trim() || !source.source_type?.trim() || !source.title?.trim()) {
      throw new Error('每条来源都需要 source_id、source_type 和 title')
    }
    return {
      source_id: source.source_id.trim(),
      source_type: source.source_type.trim(),
      title: source.title.trim(),
      url: source.url || null,
      task_id: source.task_id || null,
    }
  })
}

export default function WhiteboardRelationDialog({
  open,
  relation,
  onOpenChange,
  onSubmit,
}: WhiteboardRelationDialogProps) {
  const [relationType, setRelationType] = useState<WhiteboardRelationType>('related')
  const [label, setLabel] = useState('')
  const [description, setDescription] = useState('')
  const [lineType, setLineType] = useState<WhiteboardLineType>('bezier')
  const [direction, setDirection] = useState<WhiteboardRelationDirection>('forward')
  const [sources, setSources] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open || !relation) return
    setRelationType(relation.relation_type)
    setLabel(relation.label)
    setDescription(relation.description)
    setLineType(relation.line_type)
    setDirection(relation.direction)
    setSources(relation.source_refs.length ? JSON.stringify(relation.source_refs, null, 2) : '')
    setError('')
  }, [open, relation])

  const submit = async () => {
    try {
      setSaving(true)
      setError('')
      await onSubmit({
        relation_type: relationType,
        label: label.trim(),
        description: description.trim(),
        line_type: lineType,
        direction,
        source_refs: parseSources(sources),
      })
      onOpenChange(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '关系保存失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={saving ? undefined : onOpenChange}>
      <DialogContent className="nodrag nopan max-w-[560px]">
        <DialogHeader>
          <DialogTitle>编辑关系</DialogTitle>
          <DialogDescription>名称显示在连线中点，描述用于解释两张卡片为何相关。</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-4 py-2">
          <label className="space-y-1.5 text-xs font-medium">
            关系类型
            <select className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm" value={relationType} onChange={event => setRelationType(event.target.value as WhiteboardRelationType)}>
              <option value="related">相关</option>
              <option value="supports">支持</option>
              <option value="challenges">反驳</option>
              <option value="depends_on">依赖</option>
              <option value="contains">包含</option>
              <option value="custom">自定义</option>
            </select>
          </label>
          <label className="space-y-1.5 text-xs font-medium">
            方向
            <select className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm" value={direction} onChange={event => setDirection(event.target.value as WhiteboardRelationDirection)}>
              <option value="none">无方向</option>
              <option value="forward">正向</option>
              <option value="backward">反向</option>
              <option value="both">双向</option>
            </select>
          </label>
          <label className="col-span-2 space-y-1.5 text-xs font-medium">关系名称<Input value={label} onChange={event => setLabel(event.target.value)} /></label>
          <label className="col-span-2 space-y-1.5 text-xs font-medium">关系备注<Textarea className="min-h-24" value={description} onChange={event => setDescription(event.target.value)} /></label>
          <label className="space-y-1.5 text-xs font-medium">
            线型
            <select className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm" value={lineType} onChange={event => setLineType(event.target.value as WhiteboardLineType)}>
              <option value="bezier">曲线</option>
              <option value="straight">直线</option>
              <option value="smoothstep">折线</option>
            </select>
          </label>
          <label className="col-span-2 space-y-1.5 text-xs font-medium">
            来源（可选 JSON 数组）
            <Textarea className="min-h-20 font-mono text-xs" value={sources} onChange={event => setSources(event.target.value)} />
          </label>
          {error ? <div className="col-span-2 rounded-md bg-destructive/8 px-3 py-2 text-xs text-destructive">{error}</div> : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" disabled={saving} onClick={() => onOpenChange(false)}>取消</Button>
          <Button type="button" disabled={saving || !relation} onClick={() => void submit()}>{saving ? '保存中…' : '保存'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
