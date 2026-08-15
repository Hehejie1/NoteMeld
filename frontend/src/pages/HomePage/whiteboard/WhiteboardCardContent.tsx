import { lazy, Suspense } from 'react'
import { ArrowUpRight, Download, FileText, PanelsTopLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import ChatMarkdown from '@/pages/HomePage/components/ChatMarkdown'
import { getRuntimeApiBaseUrl, openExternalUrl } from '@/utils/runtime'
import type { WhiteboardCard } from './types'

interface WhiteboardCardContentProps {
  card: WhiteboardCard
  onOpenNested?: (whiteboardId: string) => void
}

function absoluteApiUrl(path: string) {
  const base = getRuntimeApiBaseUrl()
  if (base) return `${base.replace(/\/$/, '')}${path}`
  if (typeof window !== 'undefined') return new URL(path, window.location.origin).toString()
  return path
}

function WebCardContent({ card }: { card: Extract<WhiteboardCard, { type: 'web' }> }) {
  const { url, preview_title: previewTitle, preview_image: previewImage } = card.content
  return (
    <div className="space-y-2">
      {previewImage ? (
        <img className="h-24 w-full rounded-lg object-cover" src={previewImage} alt="" loading="lazy" />
      ) : null}
      <div className="truncate text-xs font-medium text-on-surface">{previewTitle || url}</div>
      <div className="truncate text-[11px] text-on-surface-variant">{url}</div>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="nodrag nopan h-7"
        onClick={() => void openExternalUrl(url)}
      >
        <ArrowUpRight className="h-3.5 w-3.5" />打开资源
      </Button>
    </div>
  )
}

function FileCardContent({ card }: { card: Extract<WhiteboardCard, { type: 'file' }> }) {
  const url = absoluteApiUrl(`/api/note/uploads/${encodeURIComponent(card.content.upload_id)}`)
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-container/40 p-2.5">
      <div className="flex items-center gap-2 text-xs font-medium text-on-surface">
        <FileText className="h-4 w-4 text-primary" />已存储文件
      </div>
      <div className="mt-1 truncate font-mono text-[10px] text-on-surface-variant">
        {card.content.upload_id}
      </div>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="nodrag nopan mt-2 h-7"
        onClick={() => void openExternalUrl(url)}
      >
        <Download className="h-3.5 w-3.5" />查看文件
      </Button>
    </div>
  )
}

const LazyWebCardContent = lazy(async () => ({ default: WebCardContent }))
const LazyFileCardContent = lazy(async () => ({ default: FileCardContent }))

export default function WhiteboardCardContent({ card, onOpenNested }: WhiteboardCardContentProps) {
  if (card.type === 'markdown') {
    return (
      <div className="nowheel max-h-48 overflow-auto rounded-lg border border-border-subtle/70 bg-white p-2.5">
        <ChatMarkdown content={card.content.markdown} />
      </div>
    )
  }

  if (card.type === 'whiteboard') {
    return (
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="nodrag nopan w-full justify-start"
        onClick={() => onOpenNested?.(card.content.child_whiteboard_id)}
      >
        <PanelsTopLeft className="h-4 w-4" />打开子白板
      </Button>
    )
  }

  return (
    <Suspense fallback={<div className="text-xs text-on-surface-variant">内容加载中…</div>}>
      {card.type === 'web' ? <LazyWebCardContent card={card} /> : <LazyFileCardContent card={card} />}
    </Suspense>
  )
}
