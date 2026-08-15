import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { AlertCircle, ArrowUpRight, Download, FileText, Loader2, PanelsTopLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import ChatMarkdown from '@/pages/HomePage/components/ChatMarkdown'
import { getRuntimeApiBaseUrl, getRuntimeSessionToken, openExternalUrl } from '@/utils/runtime'
import type { WhiteboardCard } from './types'

interface WhiteboardCardContentProps {
  card: WhiteboardCard
  onOpenNested?: (whiteboardId: string) => void
}

const FILE_UPLOAD_ROUTE = '/api/uploads/'

function absoluteUploadUrl(uploadId: string) {
  const encoded = encodeURIComponent(uploadId)
  const base = getRuntimeApiBaseUrl()
  if (base) return `${base.replace(/\/$/, '')}/uploads/${encoded}`
  const path = `${FILE_UPLOAD_ROUTE}${encoded}`
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
  const url = absoluteUploadUrl(card.content.upload_id)
  const [loadState, setLoadState] = useState<'loading' | 'available' | 'missing' | 'error'>('loading')
  const [attempt, setAttempt] = useState(0)

  const checkFile = useCallback(async (signal: AbortSignal) => {
    setLoadState('loading')
    try {
      const sessionToken = getRuntimeSessionToken()
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          Range: 'bytes=0-0',
          ...(sessionToken ? { 'X-NoteMeld-Session': sessionToken } : {}),
        },
        signal,
      })
      if (response.body) void response.body.cancel()
      if (response.status === 404) setLoadState('missing')
      else if (response.ok) setLoadState('available')
      else setLoadState('error')
    } catch {
      if (!signal.aborted) setLoadState('error')
    }
  }, [url])

  useEffect(() => {
    const abortController = new AbortController()
    void checkFile(abortController.signal)
    return () => abortController.abort()
  }, [attempt, checkFile])

  if (loadState === 'loading') {
    return <div className="flex items-center gap-2 text-xs text-on-surface-variant"><Loader2 className="h-3.5 w-3.5 animate-spin" />正在检查文件…</div>
  }

  if (loadState === 'missing' || loadState === 'error') {
    return (
      <div className="rounded-lg border border-dashed border-border-subtle bg-surface-container/40 p-2.5 text-xs text-on-surface-variant">
        <div className="flex items-center gap-2 font-medium text-on-surface">
          <AlertCircle className="h-4 w-4 text-amber-600" />
          {loadState === 'missing' ? '资源不存在或已被移除' : '文件加载失败'}
        </div>
        {loadState === 'error' ? (
          <Button type="button" size="sm" variant="ghost" className="nodrag nopan mt-2 h-7" onClick={() => setAttempt(value => value + 1)}>
            重试
          </Button>
        ) : null}
      </div>
    )
  }
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
