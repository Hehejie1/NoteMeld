import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertCircle, ChevronRight, Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useBackendInitContext } from '@/contexts/BackendInitContext'
import LearningCanvasCard from '@/pages/HomePage/components/LearningCanvasCard'
import MarkdownViewer from '@/pages/HomePage/components/MarkdownViewer'
import { cn } from '@/lib/utils'
import { getWhiteboard, publishWhiteboard } from '@/services/whiteboard'
import type { WhiteboardPublishResult, WhiteboardSnapshot } from './types'
import WhiteboardCanvas, { type WhiteboardCanvasStatus } from './WhiteboardCanvas'
import {
  createPublishedNoteOverride,
  createWhiteboardSnapshotLoader,
  deliverPublishedNoteRefresh,
  getWhiteboardPublishPresentation,
  loadWhiteboardSnapshotForTarget,
  isPublishedNoteOverrideConfirmed,
  isWhiteboardTargetCurrent,
  resolveWhiteboardNoteDocument,
  resolvePublishedWhiteboardSnapshot,
  reloadWhiteboardForPanelView,
  runDurableWhiteboardPublish,
  runPublishedWhiteboardReload,
  selectWhiteboardPanelSnapshot,
  type PublishedNoteOverride,
  type WhiteboardNoteDocumentLike,
} from './whiteboardPanelState'

export type WhiteboardPanelView = 'whiteboard' | 'note'

interface BreadcrumbItem {
  id: string
  title: string
}

interface WhiteboardPanelProps {
  conversationId: string
  whiteboardId: string
  legacyCanvasId?: string
  documents: readonly WhiteboardNoteDocumentLike[]
  activeView?: WhiteboardPanelView
  onViewChange?: (view: WhiteboardPanelView) => void
  showTabs?: boolean
  onDeleteDocument?: (taskId: string) => void | Promise<void>
  onWikiRetrySuccess?: () => void
  onPublished?: (result: WhiteboardPublishResult) => void | Promise<void>
}

export default function WhiteboardPanel({
  conversationId,
  whiteboardId,
  legacyCanvasId,
  documents,
  activeView,
  onViewChange,
  showTabs = true,
  onDeleteDocument,
  onWikiRetrySuccess,
  onPublished,
}: WhiteboardPanelProps) {
  const { backendReady, failureKind, checkNow } = useBackendInitContext()
  const [localView, setLocalView] = useState<WhiteboardPanelView>('whiteboard')
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbItem[]>([
    { id: whiteboardId, title: '研究白板' },
  ])
  const [canvasStatus, setCanvasStatus] = useState<WhiteboardCanvasStatus | null>(null)
  const [noteSnapshot, setNoteSnapshot] = useState<{
    targetKey: string
    value: WhiteboardSnapshot
  } | null>(null)
  const [snapshotLoadState, setSnapshotLoadState] = useState<{
    targetKey: string
    status: 'idle' | 'loading' | 'loaded' | 'error'
    message: string
  }>({ targetKey: '', status: 'idle', message: '' })
  const [publishing, setPublishing] = useState(false)
  const [publishError, setPublishError] = useState('')
  const [publishedNoteDelivery, setPublishedNoteDelivery] = useState<{
    targetKey: string
    result: WhiteboardPublishResult
    message: string
  } | null>(null)
  const [publishedNoteOverride, setPublishedNoteOverride] = useState<PublishedNoteOverride | null>(null)
  const [publishedReloadFailure, setPublishedReloadFailure] = useState<{
    targetKey: string
    message: string
  } | null>(null)
  const [retryingPublishedNote, setRetryingPublishedNote] = useState(false)
  const [retryingPublishedReload, setRetryingPublishedReload] = useState(false)
  const [showLegacyFallback, setShowLegacyFallback] = useState(false)
  const snapshotLoaderRef = useRef(createWhiteboardSnapshotLoader<WhiteboardSnapshot>())
  const currentSnapshotTargetKeyRef = useRef('')
  const currentViewRef = useRef<WhiteboardPanelView>('whiteboard')
  const currentCanvasStatusRef = useRef<{
    targetKey: string
    status: WhiteboardCanvasStatus | null
  } | null>(null)
  const view = activeView ?? localView
  const currentBoard = breadcrumbs[0]?.id === whiteboardId
    ? breadcrumbs[breadcrumbs.length - 1]
    : { id: whiteboardId, title: '研究白板' }
  const snapshotTargetKey = JSON.stringify([conversationId, currentBoard.id])
  currentSnapshotTargetKeyRef.current = snapshotTargetKey
  currentViewRef.current = view
  currentCanvasStatusRef.current = { targetKey: snapshotTargetKey, status: canvasStatus }
  const currentNoteSnapshot = noteSnapshot?.targetKey === snapshotTargetKey
    ? noteSnapshot.value
    : null
  const canvasSnapshot = canvasStatus?.snapshot?.id === currentBoard.id
    ? canvasStatus.snapshot
    : null
  const noteSnapshotForBoard = currentNoteSnapshot?.id === currentBoard.id
    ? currentNoteSnapshot
    : null
  const rawSnapshot = selectWhiteboardPanelSnapshot(
    view,
    noteSnapshotForBoard,
    canvasSnapshot,
  )
  const currentPublishedNoteOverride = publishedNoteOverride?.targetKey === snapshotTargetKey
    ? publishedNoteOverride
    : null
  const snapshot = useMemo(() => resolvePublishedWhiteboardSnapshot(
    rawSnapshot,
    snapshotTargetKey,
    currentPublishedNoteOverride,
  ), [currentPublishedNoteOverride, rawSnapshot, snapshotTargetKey])
  const snapshotLoadError = snapshotLoadState.targetKey === snapshotTargetKey
    && snapshotLoadState.status === 'error'
    ? snapshotLoadState.message
    : ''
  const snapshotLoading = view === 'note'
    && !snapshot
    && !snapshotLoadError
  const currentPublishedNoteDelivery = publishedNoteDelivery?.targetKey === snapshotTargetKey
    ? publishedNoteDelivery
    : null
  const currentPublishedReloadFailure = publishedReloadFailure?.targetKey === snapshotTargetKey
    ? publishedReloadFailure
    : null
  const publishBlocked = Boolean(
    !snapshot
    || publishing
    || retryingPublishedNote
    || retryingPublishedReload
    || currentPublishedNoteDelivery
    || currentPublishedNoteOverride
    || currentPublishedReloadFailure
    || canvasStatus?.pending
    || canvasStatus?.conflict
    || canvasStatus?.unsavedError,
  )

  useEffect(() => {
    setBreadcrumbs([{ id: whiteboardId, title: '研究白板' }])
    setCanvasStatus(null)
    setNoteSnapshot(null)
    setSnapshotLoadState({ targetKey: '', status: 'idle', message: '' })
    setPublishError('')
    setPublishedNoteDelivery(null)
    setPublishedNoteOverride(null)
    setPublishedReloadFailure(null)
    setRetryingPublishedNote(false)
    setRetryingPublishedReload(false)
    setShowLegacyFallback(false)
  }, [conversationId, whiteboardId])

  const loadNoteSnapshot = useCallback(async () => {
    if (!backendReady) return
    const targetKey = JSON.stringify([conversationId, currentBoard.id])
    setSnapshotLoadState({ targetKey, status: 'loading', message: '' })
    const outcome = await loadWhiteboardSnapshotForTarget({
      targetKey,
      getCurrentTargetKey: () => currentSnapshotTargetKeyRef.current,
      load: () => snapshotLoaderRef.current.load(
        targetKey,
        () => getWhiteboard(conversationId, currentBoard.id),
      ),
      accept: board => {
        setNoteSnapshot({ targetKey, value: board })
        setSnapshotLoadState({ targetKey, status: 'loaded', message: '' })
      },
    })
    if (outcome.status === 'error' && currentSnapshotTargetKeyRef.current === targetKey) {
      setSnapshotLoadState({
        targetKey,
        status: 'error',
        message: `白板发布状态加载失败：${outcome.message}`,
      })
    }
  }, [backendReady, conversationId, currentBoard.id])

  useEffect(() => {
    if (
      !backendReady
      || view !== 'note'
      || snapshot?.id === currentBoard.id
      || (snapshotLoadState.targetKey === snapshotTargetKey && snapshotLoadState.status !== 'idle')
    ) return
    void loadNoteSnapshot()
  }, [backendReady, currentBoard.id, loadNoteSnapshot, snapshot?.id, snapshotLoadState.status, snapshotLoadState.targetKey, snapshotTargetKey, view])

  useEffect(() => {
    if (!snapshot || snapshot.id !== currentBoard.id) return
    setBreadcrumbs(items => items.map(item => (
      item.id === snapshot.id ? { ...item, title: snapshot.title || item.title } : item
    )))
  }, [currentBoard.id, snapshot])

  useEffect(() => {
    if (isPublishedNoteOverrideConfirmed(rawSnapshot, currentPublishedNoteOverride)) {
      setPublishedNoteOverride(null)
    }
  }, [currentPublishedNoteOverride, rawSnapshot])

  const publishPresentation = useMemo(() => snapshot
    ? getWhiteboardPublishPresentation({ revision: snapshot.revision, noteLink: snapshot.note_link })
    : null, [snapshot])
  const boardNote = useMemo(
    () => resolveWhiteboardNoteDocument(snapshot?.note_link || null, documents),
    [documents, snapshot?.note_link],
  )

  const selectView = (next: WhiteboardPanelView) => {
    if (activeView === undefined) setLocalView(next)
    onViewChange?.(next)
  }

  const openNestedWhiteboard = (childWhiteboardId: string) => {
    setBreadcrumbs(items => {
      const existingIndex = items.findIndex(item => item.id === childWhiteboardId)
      if (existingIndex >= 0) return items.slice(0, existingIndex + 1)
      return [...items, { id: childWhiteboardId, title: '子白板' }]
    })
    setCanvasStatus(null)
    setNoteSnapshot(null)
    setSnapshotLoadState({ targetKey: '', status: 'idle', message: '' })
    setPublishError('')
    setPublishedNoteDelivery(null)
    setPublishedNoteOverride(null)
    setPublishedReloadFailure(null)
    setRetryingPublishedNote(false)
    setRetryingPublishedReload(false)
  }

  const retryNoteSnapshotLoad = async () => {
    await checkNow().catch(() => undefined)
    await loadNoteSnapshot()
  }

  const retryLegacyFallback = () => {
    setShowLegacyFallback(false)
    if (view === 'whiteboard' && canvasStatus) {
      void canvasStatus.reload().catch(() => undefined)
      return
    }
    void retryNoteSnapshotLoad()
  }

  const retryPublishedNoteRefresh = async () => {
    if (!currentPublishedNoteDelivery || retryingPublishedNote) return
    const retryTargetKey = currentPublishedNoteDelivery.targetKey
    setRetryingPublishedNote(true)
    const delivery = await deliverPublishedNoteRefresh(
      currentPublishedNoteDelivery.result,
      onPublished,
    )
    if (currentSnapshotTargetKeyRef.current !== retryTargetKey) {
      setRetryingPublishedNote(false)
      return
    }
    if (delivery.status === 'failed') {
      setPublishedNoteDelivery({
        targetKey: retryTargetKey,
        result: currentPublishedNoteDelivery.result,
        message: delivery.message,
      })
    } else {
      setPublishedNoteDelivery(null)
    }
    setRetryingPublishedNote(false)
  }

  const reloadPublishedWhiteboard = async (targetKey: string) => {
    if (currentSnapshotTargetKeyRef.current !== targetKey) return
    setRetryingPublishedReload(true)
    const reloadView = currentViewRef.current
    const activeCanvasStatus = currentCanvasStatusRef.current?.targetKey === targetKey
      ? currentCanvasStatusRef.current.status
      : null
    const outcome = await runPublishedWhiteboardReload(() => reloadWhiteboardForPanelView({
      view: reloadView,
      canvasReload: reloadView === 'whiteboard' && activeCanvasStatus
        ? activeCanvasStatus.reload
        : undefined,
      directLoad: () => getWhiteboard(conversationId, currentBoard.id),
      targetKey,
      getCurrentTargetKey: () => currentSnapshotTargetKeyRef.current,
      accept: board => setNoteSnapshot({ targetKey, value: board }),
    }))
    if (currentSnapshotTargetKeyRef.current !== targetKey) {
      setRetryingPublishedReload(false)
      return
    }
    if (outcome.status === 'failed') {
      setPublishedReloadFailure({ targetKey, message: outcome.message })
    } else {
      setPublishedReloadFailure(null)
    }
    setRetryingPublishedReload(false)
  }

  const publish = async () => {
    if (!snapshot || publishing) return
    const publishTargetKey = snapshotTargetKey
    setPublishing(true)
    setPublishError('')
    setPublishedNoteDelivery(null)
    setPublishedReloadFailure(null)
    try {
      const outcome = await runDurableWhiteboardPublish({
        publish: () => publishWhiteboard(conversationId, snapshot.id, {
          base_revision: snapshot.revision,
          scope: 'all',
          card_ids: [],
          relation_ids: [],
        }),
        deliver: onPublished,
      })
      if (outcome.noteRefresh.status === 'failed') {
        if (currentSnapshotTargetKeyRef.current === publishTargetKey) {
          setPublishedNoteDelivery({
            targetKey: publishTargetKey,
            result: outcome.result,
            message: outcome.noteRefresh.message,
          })
        }
      }
      if (currentSnapshotTargetKeyRef.current === publishTargetKey) {
        setPublishedNoteOverride(createPublishedNoteOverride(publishTargetKey, outcome.result))
        await reloadPublishedWhiteboard(publishTargetKey)
      }
    } catch (error) {
      if (!isWhiteboardTargetCurrent(
        publishTargetKey,
        () => currentSnapshotTargetKeyRef.current,
      )) return
      const candidate = error as { msg?: string } | undefined
      setPublishError(candidate?.msg || '发布失败，白板和上一次笔记均已保留')
    } finally {
      setPublishing(false)
    }
  }

  if (!backendReady) {
    if (failureKind) {
      return (
        <div className="flex h-full min-h-0 flex-col items-center justify-center gap-3 px-6 text-center text-sm text-on-surface-variant" role="alert">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <span>{failureKind === 'runtime' ? '本地运行时启动失败，白板尚未连接。' : '本地知识库连接失败，白板尚未加载。'}</span>
          <Button type="button" size="sm" variant="outline" onClick={() => void checkNow().catch(() => undefined)}><RefreshCw className="h-4 w-4" />重试连接</Button>
        </div>
      )
    }
    return (
      <div className="flex h-full min-h-0 items-center justify-center gap-2 text-sm text-on-surface-variant">
        <Loader2 className="h-4 w-4 animate-spin" />正在连接本地知识库…
      </div>
    )
  }

  return (
    <section className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-white" aria-label="白板与笔记工作区">
      <header className="shrink-0 border-b border-border-subtle/60 bg-white">
        <div className="flex min-h-12 items-center justify-between gap-3 px-4 py-2">
          <div className="flex min-w-0 items-center gap-3">
            {showTabs ? (
              <div className="flex items-center gap-1">
                <button type="button" onClick={() => selectView('whiteboard')} className={cn('rounded-md px-3 py-1.5 text-[13px] font-medium', view === 'whiteboard' ? 'bg-primary-light text-primary' : 'text-on-surface-variant hover:bg-surface-container-low')}>白板</button>
                <button type="button" onClick={() => selectView('note')} className={cn('rounded-md px-3 py-1.5 text-[13px] font-medium', view === 'note' ? 'bg-primary-light text-primary' : 'text-on-surface-variant hover:bg-surface-container-low')}>笔记</button>
              </div>
            ) : null}
            <nav className="flex min-w-0 items-center text-[11px] text-on-surface-variant" aria-label="白板面包屑" data-testid="whiteboard-breadcrumb">
              {breadcrumbs.map((item, index) => (
                <span key={item.id} className="flex min-w-0 items-center">
                  {index > 0 ? <ChevronRight className="mx-1 h-3 w-3 shrink-0" /> : null}
                  <button type="button" className="max-w-[150px] truncate hover:text-primary" onClick={() => { setBreadcrumbs(items => items.slice(0, index + 1)); setCanvasStatus(null) }}>{item.title}</button>
                </span>
              ))}
            </nav>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {publishPresentation ? (
              <span className={cn('rounded-full px-2 py-1 text-[11px]', publishPresentation.state === 'stale' ? 'bg-amber-50 text-amber-700' : publishPresentation.state === 'synced' ? 'bg-emerald-50 text-emerald-700' : 'bg-surface-container text-on-surface-variant')}>{publishPresentation.label}</span>
            ) : null}
            <Button type="button" size="sm" variant="outline" disabled={publishBlocked} onClick={() => void publish()}>
              {publishing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              {publishPresentation?.actionLabel || '发布为笔记'}
            </Button>
          </div>
        </div>
        {publishError ? <div className="border-t border-destructive/10 bg-destructive/5 px-4 py-2 text-xs text-destructive" role="alert">{publishError}</div> : null}
        {currentPublishedNoteDelivery ? (
          <div className="flex flex-wrap items-center gap-2 border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800" role="alert">
            <span>发布成功，笔记内容刷新失败：{currentPublishedNoteDelivery.message.replace(/^发布成功，笔记内容刷新失败：/, '')}</span>
            <Button type="button" size="sm" variant="outline" className="h-7" disabled={retryingPublishedNote} onClick={() => void retryPublishedNoteRefresh()}>
              {retryingPublishedNote ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              重试刷新
            </Button>
          </div>
        ) : null}
        {currentPublishedReloadFailure ? (
          <div className="flex flex-wrap items-center gap-2 border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800" role="alert">
            <span>笔记已发布，白板状态刷新失败：{currentPublishedReloadFailure.message.replace(/^笔记已发布，白板状态刷新失败：/, '')}</span>
            <Button type="button" size="sm" variant="outline" className="h-7" disabled={retryingPublishedReload} onClick={() => void reloadPublishedWhiteboard(currentPublishedReloadFailure.targetKey)}>
              {retryingPublishedReload ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              重试白板刷新
            </Button>
          </div>
        ) : null}
        {canvasStatus?.conflict ? (
          <div className="flex flex-wrap items-center gap-2 border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800" role="alert">
            <span>白板已在其他窗口更新，本地操作仍可重新应用。</span>
            <Button type="button" size="sm" variant="outline" className="h-7" onClick={() => { canvasStatus.discardRetry(); void canvasStatus.reload().catch(() => undefined) }}>重新加载</Button>
            <Button type="button" size="sm" className="h-7" onClick={() => void canvasStatus.retry().catch(() => undefined)}>重新应用</Button>
          </div>
        ) : null}
      </header>

      <div className="relative min-h-0 flex-1 overflow-hidden">
        {showLegacyFallback && legacyCanvasId ? (
          <LearningCanvasCard conversationId={conversationId} canvasId={legacyCanvasId} conversionError="可编辑白板加载失败，当前显示原研究图。" onRetryConversion={retryLegacyFallback} />
        ) : view === 'note' ? (
          snapshotLoadError ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center text-sm text-on-surface-variant" role="alert">
              <AlertCircle className="h-5 w-5 text-destructive" />
              <span>{snapshotLoadError}</span>
              <div className="flex gap-2">
                <Button type="button" size="sm" variant="outline" onClick={() => void retryNoteSnapshotLoad()}><RefreshCw className="h-4 w-4" />重试加载</Button>
                {legacyCanvasId ? <Button type="button" size="sm" variant="ghost" onClick={() => { setShowLegacyFallback(true); selectView('whiteboard') }}>查看原研究图</Button> : null}
              </div>
            </div>
          ) : snapshotLoading ? (
            <div className="flex h-full items-center justify-center gap-2 text-sm text-on-surface-variant">
              <Loader2 className="h-4 w-4 animate-spin" />正在加载白板发布状态…
            </div>
          ) : boardNote.taskId ? (
            <MarkdownViewer
              status={boardNote.status}
              content={boardNote.content}
              documentTaskId={boardNote.taskId}
              onDeleteDocument={onDeleteDocument ? async () => {
                await onDeleteDocument(boardNote.taskId)
                const refreshed = await getWhiteboard(conversationId, currentBoard.id).catch(() => null)
                if (refreshed) setNoteSnapshot({ targetKey: snapshotTargetKey, value: refreshed })
              } : undefined}
              onWikiRetrySuccess={onWikiRetrySuccess}
            />
          ) : (
            <div className="flex h-full items-center justify-center px-6 text-center">
              <div>
                <div className="text-sm font-semibold text-on-surface">尚未发布</div>
                <p className="mt-2 max-w-sm text-xs leading-5 text-on-surface-variant">白板仍是研究草稿。确认结构后，点击“发布为笔记”进入标准 Note 与 Wiki 管线。</p>
                <Button type="button" size="sm" className="mt-4" disabled={publishBlocked} onClick={() => void publish()}>发布为笔记</Button>
              </div>
            </div>
          )
        ) : (
          <div className="relative h-full min-h-0">
            <WhiteboardCanvas conversationId={conversationId} whiteboardId={currentBoard.id} onOpenNestedWhiteboard={openNestedWhiteboard} onStatusChange={setCanvasStatus} />
            {canvasStatus?.loadError ? (
              <div className="absolute inset-0 z-40 flex flex-col items-center justify-center gap-3 bg-white px-6 text-center text-sm text-on-surface-variant">
                <AlertCircle className="h-5 w-5 text-destructive" />
                <span>{canvasStatus.loadError}</span>
                <div className="flex gap-2">
                  <Button type="button" size="sm" variant="outline" onClick={() => void canvasStatus.reload().catch(() => undefined)}><RefreshCw className="h-4 w-4" />重试</Button>
                  {legacyCanvasId ? <Button type="button" size="sm" variant="ghost" onClick={() => setShowLegacyFallback(true)}>查看原研究图</Button> : null}
                </div>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </section>
  )
}
