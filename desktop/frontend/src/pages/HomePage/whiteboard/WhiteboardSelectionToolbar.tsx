import { Copy, MessageSquarePlus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface WhiteboardSelectionToolbarProps {
  cardCount: number
  relationCount: number
  pending: boolean
  addingContext: boolean
  onCopy: () => void
  onDelete: () => void
  onAddToConversation: () => void
}

export default function WhiteboardSelectionToolbar({
  cardCount,
  relationCount,
  pending,
  addingContext,
  onCopy,
  onDelete,
  onAddToConversation,
}: WhiteboardSelectionToolbarProps) {
  if (cardCount + relationCount === 0) return null
  return (
    <div className="absolute bottom-4 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1 rounded-xl border border-border-subtle bg-white/95 p-1.5 shadow-lg backdrop-blur">
      <span className="px-2 text-[11px] text-on-surface-variant">
        {cardCount} 张卡片 · {relationCount} 条关系
      </span>
      <Button type="button" size="sm" variant="ghost" disabled={pending} onClick={onCopy}>
        <Copy className="h-3.5 w-3.5" />复制
      </Button>
      <Button type="button" size="sm" variant="ghost" disabled={pending} onClick={onDelete}>
        <Trash2 className="h-3.5 w-3.5" />删除
      </Button>
      <Button type="button" size="sm" disabled={pending || addingContext} onClick={onAddToConversation}>
        <MessageSquarePlus className="h-3.5 w-3.5" />
        {addingContext ? '正在添加…' : '添加到对话'}
      </Button>
    </div>
  )
}
