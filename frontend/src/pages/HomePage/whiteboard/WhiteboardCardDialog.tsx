import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { WhiteboardCard, WhiteboardCardType, WhiteboardSourceRef } from './types'

export interface WhiteboardCardFormValue {
  type: WhiteboardCardType
  title: string
  description: string
  content: WhiteboardCard['content']
  source_refs: WhiteboardSourceRef[]
}

interface WhiteboardCardDialogProps {
  open: boolean
  initialType?: WhiteboardCardType
  card?: WhiteboardCard | null
  onOpenChange: (open: boolean) => void
  onSubmit: (value: WhiteboardCardFormValue) => Promise<void>
}

const contentValue = (card?: WhiteboardCard | null) => {
  if (!card) return ''
  if (card.type === 'markdown') return card.content.markdown
  if (card.type === 'web') return card.content.url
  if (card.type === 'file') return card.content.upload_id
  return card.content.child_whiteboard_id
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

export default function WhiteboardCardDialog({
  open,
  initialType = 'markdown',
  card,
  onOpenChange,
  onSubmit,
}: WhiteboardCardDialogProps) {
  const [type, setType] = useState<WhiteboardCardType>(initialType)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [content, setContent] = useState('')
  const [sources, setSources] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setType(card?.type || initialType)
    setTitle(card?.title || '')
    setDescription(card?.description || '')
    setContent(contentValue(card))
    setSources(card?.source_refs.length ? JSON.stringify(card.source_refs, null, 2) : '')
    setError('')
  }, [card, initialType, open])

  const submit = async () => {
    try {
      if (!title.trim()) throw new Error('请输入卡片标题')
      const raw = content.trim()
      let shapedContent: WhiteboardCard['content']
      if (type === 'markdown') {
        if (!raw) throw new Error('请输入 Markdown 内容')
        shapedContent = { markdown: content }
      } else if (type === 'web') {
        if (!/^https?:\/\//i.test(raw)) throw new Error('网页地址必须以 http:// 或 https:// 开头')
        shapedContent = { url: raw }
      } else if (type === 'file') {
        if (!raw || /[\\/]/.test(raw)) throw new Error('请输入已上传文件的 upload id')
        shapedContent = { upload_id: raw }
      } else {
        if (!raw || /[\\/]/.test(raw)) throw new Error('请输入同一会话内的白板 id')
        shapedContent = { child_whiteboard_id: raw }
      }
      const sourceRefs = parseSources(sources)
      setSaving(true)
      setError('')
      await onSubmit({
        type,
        title: title.trim(),
        description: description.trim(),
        content: shapedContent,
        source_refs: sourceRefs,
      })
      onOpenChange(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '卡片保存失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={saving ? undefined : onOpenChange}>
      <DialogContent className="nodrag nopan max-h-[86vh] max-w-[620px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{card ? '编辑卡片' : '创建卡片'}</DialogTitle>
          <DialogDescription>卡片默认保持紧凑，只有选中时才加载详细内容。</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <label className="block space-y-1.5 text-xs font-medium">
            类型
            <select className="h-9 w-full rounded-md border border-input bg-white px-3 text-sm" value={type} onChange={event => setType(event.target.value as WhiteboardCardType)}>
              <option value="markdown">Markdown</option>
              <option value="web">网页</option>
              <option value="file">文件</option>
              <option value="whiteboard">白板</option>
            </select>
          </label>
          <label className="block space-y-1.5 text-xs font-medium">标题<Input value={title} onChange={event => setTitle(event.target.value)} /></label>
          <label className="block space-y-1.5 text-xs font-medium">描述<Textarea className="min-h-20" value={description} onChange={event => setDescription(event.target.value)} /></label>
          <label className="block space-y-1.5 text-xs font-medium">
            {type === 'markdown' ? 'Markdown 内容' : type === 'web' ? '网页地址' : type === 'file' ? 'Upload ID' : '子白板 ID'}
            <Textarea className="min-h-28 font-mono text-xs" value={content} onChange={event => setContent(event.target.value)} />
          </label>
          <label className="block space-y-1.5 text-xs font-medium">
            来源（可选 JSON 数组）
            <Textarea className="min-h-24 font-mono text-xs" placeholder='[{"source_id":"note_1","source_type":"local_note","title":"来源标题"}]' value={sources} onChange={event => setSources(event.target.value)} />
          </label>
          {error ? <div className="rounded-md bg-destructive/8 px-3 py-2 text-xs text-destructive">{error}</div> : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" disabled={saving} onClick={() => onOpenChange(false)}>取消</Button>
          <Button type="button" disabled={saving} onClick={() => void submit()}>{saving ? '保存中…' : '保存'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
