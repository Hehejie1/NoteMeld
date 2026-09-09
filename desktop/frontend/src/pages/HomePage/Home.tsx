import { FC, useMemo, useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowUpRight, FileCode2, FileText, Files, MoreHorizontal, PanelBottomOpen, PanelRightClose, PanelRightOpen, Plus, Share2, Sparkles, Terminal, X } from 'lucide-react'
import toast from 'react-hot-toast'
import ChatComposer from '@/pages/HomePage/components/ChatComposer'
import LearningCanvasCard from '@/pages/HomePage/components/LearningCanvasCard'
import MarkdownViewer from '@/pages/HomePage/components/MarkdownViewer'
import WhiteboardPanel, { type WhiteboardPanelView } from '@/pages/HomePage/whiteboard/WhiteboardPanel'
import {
  createLearningSeedKey,
  createSeedAttemptRegistry,
  resolveLatestLearningWorkspace,
  resolveSeedError,
  resolveWhiteboardId,
  runLegacyWhiteboardSeed,
  completePublishedConversationRefresh,
} from '@/pages/HomePage/whiteboard/whiteboardPanelState'
import { useTaskStore, type ConversationMessage, type Task } from '@/store/taskStore'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { buildConversationTimeline } from '@/pages/HomePage/conversationHelpers'
import {
  findScrollViewport,
  isNearScrollBottom,
  scrollElementToBottom,
} from '@/pages/HomePage/chatScrollHelpers'
import { ConversationMessageRenderer } from '@/pages/HomePage/messageRenderers'
import { get_task_status } from '@/services/note'
import { cancelWorkspaceTask } from '@/services/workspace'
import { seedLearningCanvasWhiteboard } from '@/services/learning'
import type { WhiteboardPublishResult } from '@/pages/HomePage/whiteboard/types'
import { useBackendInitContext } from '@/contexts/BackendInitContext'

type ViewStatus = 'idle' | 'loading' | 'success' | 'failed'

const SEMANTIC_WHITEBOARD_ENABLED = import.meta.env.VITE_SEMANTIC_WHITEBOARD_ENABLED !== 'false'

export const HomePage: FC = () => {
  const { taskId } = useParams<{ taskId?: string }>()
  const navigate = useNavigate()
  const { backendReady, failureKind, checkNow } = useBackendInitContext()
  const tasks = useTaskStore(state => state.tasks)
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const hasLoadedConversations = useTaskStore(state => state.hasLoadedConversations)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const retryTask = useTaskStore(state => state.retryTask)
  const retryChat = useTaskStore(state => state.retryChat)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)
  const selectNoteDocument = useTaskStore(state => state.selectNoteDocument)
  const deleteNoteDocument = useTaskStore(state => state.deleteNoteDocument)
  const loadConversation = useTaskStore(state => state.loadConversation)
  const refreshConversation = useTaskStore(state => state.refreshConversation)

  // /new 视为“新建笔记”，强制空态、不展示任何选中笔记
  const isNewNote = !taskId

  // 同步 URL → currentTaskId
  useEffect(() => {
    if (isNewNote) {
      if (currentTaskId !== null) setCurrentTask(null)
      return
    }
    if (taskId && taskId !== currentTaskId) {
      setCurrentTask(taskId)
    }
    if (taskId) {
      loadConversation(taskId).catch(err => {
        console.error('加载会话详情失败', err)
      })
    }
  }, [taskId, isNewNote, currentTaskId, loadConversation, setCurrentTask])

  // URL 中 taskId 不存在时（被删除等），回到 /new
  useEffect(() => {
    if (taskId && hasLoadedConversations && !tasks.find(t => t.id === taskId)) {
      navigate('/new', { replace: true })
    }
  }, [taskId, tasks, hasLoadedConversations, navigate])

  const currentTask = !isNewNote ? tasks.find(t => t.id === taskId) : null

  const [viewerCollapsed, setViewerCollapsed] = useState(false)
  const [idlePanel, setIdlePanel] = useState<'side' | 'bottom' | null>(null)
  const [contextOpen, setContextOpen] = useState(false)
  const handleShareSession = async () => {
    const url = window.location.href
    if (!navigator.clipboard) {
      toast.error('当前环境不支持复制会话链接')
      return
    }
    try {
      await navigator.clipboard.writeText(url)
      toast.success('会话链接已复制')
    } catch {
      toast.error('复制会话链接失败')
    }
  }
  /** 对话栏宽度比例（0-1），默认 0.5 即各占一半 */
  const [chatRatio, setChatRatio] = useState(0.5)
  const [mobileView, setMobileView] = useState<'chat' | 'learning' | 'note' | 'wiki'>('chat')
  const [rightContentView, setRightContentView] = useState<'learning' | 'note'>('learning')
  const [seededWhiteboard, setSeededWhiteboard] = useState({ key: '', id: '' })
  const [whiteboardSeedError, setWhiteboardSeedError] = useState({ key: '', message: '' })
  const seedAttemptsRef = useRef(createSeedAttemptRegistry())
  const activeSeedKeyRef = useRef('')
  const [isMobile, setIsMobile] = useState(false)
  const splitContainerRef = useRef<HTMLDivElement>(null)
  const draggingRef = useRef(false)
  const scrollAreaRootRef = useRef<HTMLDivElement>(null)
  const previousAutoScrollTaskIdRef = useRef<string | null>(null)
  const autoScrollMessageKey = useMemo(() => {
    const lastMessage = currentTask?.messages?.[currentTask.messages.length - 1]
    if (!lastMessage) return ''
    return [
      lastMessage.id,
      lastMessage.content,
      String(Boolean((lastMessage as ConversationMessage & { isStreaming?: boolean }).isStreaming)),
    ].join('|')
  }, [currentTask?.messages])
  const latestLearningCanvas = useMemo(
    () => resolveLatestLearningWorkspace(currentTask?.messages || []),
    [currentTask?.messages],
  )
  const conversationId = currentTask?.id || ''
  const latestLearningMessageId = latestLearningCanvas?.messageId || ''
  const latestLearningCanvasId = latestLearningCanvas?.canvasId || ''
  const compactWhiteboardId = latestLearningCanvas?.whiteboardId || ''
  const seedRequestKey = createLearningSeedKey(
    conversationId,
    latestLearningMessageId,
    latestLearningCanvasId,
  )
  activeSeedKeyRef.current = seedRequestKey
  const latestWhiteboardId = resolveWhiteboardId(
    compactWhiteboardId,
    seedRequestKey,
    seededWhiteboard,
  )
  const activeWhiteboardSeedError = resolveSeedError(seedRequestKey, whiteboardSeedError)
  const hasLearningCanvas = Boolean(
    latestLearningCanvas && (latestLearningCanvas.canvasId || latestWhiteboardId),
  )
  const useLegacyLearningCanvas = Boolean(
    latestLearningCanvasId
    && (!SEMANTIC_WHITEBOARD_ENABLED || activeWhiteboardSeedError),
  )
  const whiteboardSeedPending = Boolean(
    SEMANTIC_WHITEBOARD_ENABLED
    && latestLearningCanvasId
    && !compactWhiteboardId
    && !latestWhiteboardId
    && !activeWhiteboardSeedError,
  )

  useEffect(() => {
    if (!latestLearningMessageId || !SEMANTIC_WHITEBOARD_ENABLED) {
      return
    }
    if (compactWhiteboardId) {
      return
    }
    if (!latestLearningCanvasId || !conversationId) {
      return
    }
    runLegacyWhiteboardSeed({
      backendReady,
      conversationId,
      messageId: latestLearningMessageId,
      canvasId: latestLearningCanvasId,
      registry: seedAttemptsRef.current,
      request: () => seedLearningCanvasWhiteboard(conversationId, latestLearningCanvasId),
    })
      .then(result => {
        if (activeSeedKeyRef.current !== seedRequestKey || result.status !== 'seeded') return
        setSeededWhiteboard({ key: seedRequestKey, id: result.value.id })
        setWhiteboardSeedError({ key: '', message: '' })
      })
      .catch(error => {
        if (activeSeedKeyRef.current !== seedRequestKey) return
        const candidate = error as { msg?: string } | undefined
        setWhiteboardSeedError({
          key: seedRequestKey,
          message: candidate?.msg || '转换可编辑白板失败，仍可查看原图',
        })
      })
  }, [backendReady, compactWhiteboardId, conversationId, latestLearningCanvasId, latestLearningMessageId, seedRequestKey])

  const retryWhiteboardSeed = () => {
    if (!conversationId || !latestLearningMessageId) return
    const retryKey = seedRequestKey
    seedAttemptsRef.current.release(conversationId, latestLearningMessageId)
    setWhiteboardSeedError({ key: '', message: '' })
    setSeededWhiteboard({ key: '', id: '' })
    if (!latestLearningCanvasId) return
    runLegacyWhiteboardSeed({
      backendReady,
      conversationId,
      messageId: latestLearningMessageId,
      canvasId: latestLearningCanvasId,
      registry: seedAttemptsRef.current,
      request: () => seedLearningCanvasWhiteboard(conversationId, latestLearningCanvasId),
    })
      .then(result => {
        if (activeSeedKeyRef.current !== retryKey || result.status !== 'seeded') return
        setSeededWhiteboard({ key: retryKey, id: result.value.id })
      })
      .catch(error => {
        if (activeSeedKeyRef.current !== retryKey) return
        const candidate = error as { msg?: string } | undefined
        setWhiteboardSeedError({
          key: retryKey,
          message: candidate?.msg || '转换可编辑白板失败，仍可查看原图',
        })
      })
  }

  useEffect(() => {
    const media = window.matchMedia('(max-width: 767px)')
    const sync = () => setIsMobile(media.matches)
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])

  // 拖拽对话栏 / 笔记看板分隔条
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current || !splitContainerRef.current) return
      const rect = splitContainerRef.current.getBoundingClientRect()
      const offset = e.clientX - rect.left
      const total = rect.width
      // 最小宽度：对话栏 320px，笔记看板 360px
      const minLeft = 320
      const minRight = 360
      const minRatio = minLeft / total
      const maxRatio = (total - minRight) / total
      const next = Math.min(maxRatio, Math.max(minRatio, offset / total))
      setChatRatio(next)
    }
    const onUp = () => {
      if (draggingRef.current) {
        draggingRef.current = false
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  const startSplitDrag = (e: React.MouseEvent) => {
    e.preventDefault()
    draggingRef.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  const status: ViewStatus = useMemo(() => {
    if (!currentTask) return 'idle'
    if (
      currentTask.status === 'FAILED'
      || currentTask.status === 'CANCELED'
      || currentTask.status === 'NOT_FOUND'
      || currentTask.noteState === 'failed'
    ) return 'failed'
    if (currentTask.noteState === 'generating') return 'loading'
    if (currentTask.noteState === 'none' && currentTask.mode === 'chat') return 'success'
    if (currentTask.status === 'SUCCESS') return 'success'
    return 'loading'
  }, [currentTask])

  const hasSelectedDocument = Boolean(currentTask?.activeDocumentTaskId)
    && (currentTask?.documents || []).some(document => document.taskId === currentTask?.activeDocumentTaskId && document.content)
  const viewerStatus: ViewStatus = hasSelectedDocument ? 'success' : 'idle'
  const shouldShowSplitLayout = status === 'success' || hasSelectedDocument || hasLearningCanvas

  useEffect(() => {
    if (hasLearningCanvas) {
      setRightContentView('learning')
      setViewerCollapsed(false)
      return
    }
    setRightContentView('note')
  }, [currentTask?.id, latestLearningCanvas?.messageId, hasLearningCanvas])

  useEffect(() => {
    if (hasLearningCanvas && !hasSelectedDocument) {
      setRightContentView('learning')
    }
  }, [hasLearningCanvas, hasSelectedDocument])

  useEffect(() => {
    const focusWhiteboard = () => {
      if (!hasLearningCanvas) return
      setViewerCollapsed(false)
      setRightContentView('learning')
      if (isMobile) setMobileView('learning')
    }
    window.addEventListener('notemeld:focus-research-node', focusWhiteboard)
    return () => window.removeEventListener('notemeld:focus-research-node', focusWhiteboard)
  }, [hasLearningCanvas, isMobile])

  useEffect(() => {
    if (!isMobile) return
    if (hasLearningCanvas) {
      setMobileView('learning')
      return
    }
    if (status === 'success' || hasSelectedDocument) {
      setMobileView('note')
      return
    }
    setMobileView('chat')
  }, [isMobile, status, hasSelectedDocument, hasLearningCanvas, currentTask?.id])

  const handleRetry = (noteTaskId?: string) => {
    if (currentTask?.id) {
      retryTask(currentTask.id, undefined, noteTaskId)
    }
  }

  const handleRetryChat = () => {
    if (currentTask?.id) {
      retryChat(currentTask.id)
    }
  }

  const handleSelectNoteResult = async (noteTaskId: string) => {
    if (!currentTask?.id || !noteTaskId) return
    const existing = (currentTask.documents || []).find(document => document.taskId === noteTaskId)
    if (existing?.content) {
      selectNoteDocument(currentTask.id, noteTaskId)
      return
    }

    const res = await get_task_status(noteTaskId)
    const markdown = res.result?.markdown
    if (res.status === 'SUCCESS' && typeof markdown === 'string') {
      updateTaskContent(currentTask.id, {
        status: 'SUCCESS',
        message: res.message,
        markdown,
        transcript: res.result?.transcript,
        audioMeta: res.result?.audio_meta,
        documentTaskId: res.task_id || noteTaskId,
      })
      selectNoteDocument(currentTask.id, noteTaskId)
    }
  }

  const handleCancelTask = async (cardId: string) => {
    if (!currentTask?.id || !cardId) return
    try {
      await cancelWorkspaceTask(currentTask.id, cardId)
    } catch {
      /* 错误已由 request 拦截器 toast */
    }
  }

  const handleDeleteCurrentDocument = async () => {
    if (!currentTask?.id || !currentTask.activeDocumentTaskId) return
    const confirmed = window.confirm('删除这篇笔记？此操作会移除对应 Wiki 贡献。')
    if (!confirmed) return
    await deleteNoteDocument(currentTask.id, currentTask.activeDocumentTaskId)
  }

  const handleDeleteWhiteboardDocument = async (noteTaskId: string) => {
    if (!currentTask?.id || !noteTaskId) return
    const confirmed = window.confirm('删除这篇笔记？此操作会移除对应 Wiki 贡献。')
    if (!confirmed) return
    await deleteNoteDocument(currentTask.id, noteTaskId)
  }

  const handleWikiRetrySuccess = () => {
    if (!currentTask?.id) return
    refreshConversation(currentTask.id).catch(err => {
      console.error('刷新 Wiki 状态失败', err)
    })
  }

  const handleWhiteboardPublished = async (result: WhiteboardPublishResult) => {
    if (!currentTask?.id) return
    const publishedConversationId = currentTask.id
    await completePublishedConversationRefresh({
      conversationId: publishedConversationId,
      getCurrentConversationId: () => useTaskStore.getState().currentTaskId,
      refresh: () => refreshConversation(publishedConversationId),
      apply: () => {
        selectNoteDocument(publishedConversationId, result.note_task_id)
        setRightContentView('note')
        if (isMobile) setMobileView('note')
      },
    })
  }

  const panelView: WhiteboardPanelView = rightContentView === 'learning' ? 'whiteboard' : 'note'

  const renderWhiteboardSeedPending = () => (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center text-sm text-on-surface-variant">
      <span>{failureKind ? '本地知识库尚未连接，暂时无法转换可编辑白板。' : '正在转换可编辑白板…'}</span>
      {failureKind ? (
        <button type="button" className="rounded-md border border-border-subtle bg-white px-3 py-1.5 text-xs text-primary hover:bg-primary-light" onClick={() => void checkNow().catch(() => undefined)}>重试连接</button>
      ) : null}
    </div>
  )

  // 只在切换会话或用户本来就在底部附近时自动跟随，避免轮询刷新把阅读位置拉走。
  useEffect(() => {
    const viewport = findScrollViewport(scrollAreaRootRef.current)
    if (!viewport) return

    const taskChanged = previousAutoScrollTaskIdRef.current !== currentTask?.id
    if (taskChanged || isNearScrollBottom(viewport)) {
      scrollElementToBottom(viewport)
    }

    previousAutoScrollTaskIdRef.current = currentTask?.id || null
  }, [currentTask?.id, currentTask?.messages?.length, autoScrollMessageKey])

  useEffect(() => {
    if (!taskId || currentTask?.mode !== 'note') return
    if (currentTask.status !== 'SUCCESS' && currentTask.status !== 'FAILED') return

    loadConversation(taskId).catch(err => {
      console.error('同步会话终态消息失败', err)
    })
  }, [taskId, currentTask?.mode, currentTask?.status, loadConversation])

  useEffect(() => {
    if (!taskId || currentTask?.mode !== 'note') return
    if (currentTask.status === 'SUCCESS' || currentTask.status === 'FAILED') return

    const timer = window.setInterval(() => {
      loadConversation(taskId).catch(err => {
        console.error('轮询会话消息失败', err)
      })
    }, 3000)

    return () => window.clearInterval(timer)
  }, [taskId, currentTask?.mode, currentTask?.status, loadConversation])

  useEffect(() => {
    if (!currentTask?.id || currentTask.mode !== 'note' || currentTask.activeDocumentTaskId) return
    const firstDocument = (currentTask.documents || []).find(document => document.content)
    if (!firstDocument) return
    selectNoteDocument(currentTask.id, firstDocument.taskId)
  }, [
    currentTask?.id,
    currentTask?.mode,
    currentTask?.activeDocumentTaskId,
    currentTask?.documents,
    selectNoteDocument,
  ])

  /** 空态：Hero 居中 */
  if (status === 'idle') {
    return (
      <div className="relative flex h-full w-full flex-col overflow-hidden bg-surface">
        <header className="flex h-12 shrink-0 items-center justify-end gap-1 border-b border-border-subtle/60 px-4">
          <button type="button" onClick={() => setIdlePanel('bottom')} className="rounded-lg p-2 text-on-surface-variant transition hover:bg-surface-container hover:text-primary" aria-label="打开底部面板" title="命令行与运行日志"><PanelBottomOpen className="h-4 w-4" /></button>
          <button type="button" onClick={() => setIdlePanel('side')} className="rounded-lg p-2 text-on-surface-variant transition hover:bg-surface-container hover:text-primary" aria-label="打开侧边文件面板" title="选择文件并查看内容"><PanelRightOpen className="h-4 w-4" /></button>
        </header>
        <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto px-4 py-10 md:px-6">
          <div className="w-full max-w-3xl">
            <div className="mb-8 text-center">
              <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-primary-light text-primary"><Sparkles className="h-5 w-5" aria-hidden="true" /></div>
              <h1 className="font-display text-[36px] font-extrabold leading-tight tracking-[-0.04em] text-on-surface md:text-[42px]">开始新对话</h1>
              <p className="mx-auto mt-3 max-w-xl text-[15px] leading-relaxed text-on-surface-variant">选择工作空间，告诉 Agent 你想完成什么。</p>
            </div>
            <div className="mx-auto mb-6 grid max-w-2xl grid-cols-2 gap-2 md:grid-cols-4">
              {[
                ['探索并理解代码', '分析当前工作区的结构与关键模块。'],
                ['构建新功能或应用', '从需求开始拆解并实现一个可验证的功能。'],
                ['审查代码并提出修改建议', '检查风险、测试缺口和可维护性问题。'],
                ['修复问题和失败', '定位根因，给出修复方案并验证结果。'],
              ].map(([title, prompt]) => (
                <button key={title} type="button" onClick={() => window.dispatchEvent(new CustomEvent('notemeld:prefill-research', { detail: { prompt, mode: 'chat' } }))} className="min-h-16 rounded-xl border border-border-subtle bg-surface-container-lowest px-3 py-2.5 text-left text-xs font-medium text-on-surface transition hover:border-primary/40 hover:bg-primary/[0.03] focus:outline-none focus:ring-2 focus:ring-primary/30">{title}</button>
              ))}
            </div>
            <ChatComposer layout="hero" />
            <p className="mt-3 text-center text-[12px] text-on-surface-variant/70">支持使用 / 调用能力，使用 @ 添加智能体和上下文。</p>
          </div>
        </div>
        {idlePanel === 'side' && <aside className="absolute inset-y-12 right-0 z-20 flex w-[min(360px,90vw)] flex-col border-l border-border-subtle bg-surface-container-lowest shadow-2xl"><div className="flex h-12 items-center justify-between border-b border-border-subtle px-4"><span className="flex items-center gap-2 text-sm font-semibold"><Files className="h-4 w-4 text-primary" />选择文件</span><button type="button" onClick={() => setIdlePanel(null)} aria-label="关闭侧边文件面板" className="rounded-lg p-1.5 text-on-surface-variant hover:bg-surface-container"><X className="h-4 w-4" /></button></div><div className="flex min-h-0 flex-1 flex-col gap-4 p-4"><div className="space-y-1"><button type="button" className="w-full rounded-lg bg-primary-light px-3 py-2 text-left text-xs font-medium text-primary">▧ event_bus_config.yaml</button><button type="button" className="w-full rounded-lg px-3 py-2 text-left text-xs text-on-surface-variant hover:bg-surface-container">▤ 系统架构研究报告.md</button><button type="button" className="w-full rounded-lg px-3 py-2 text-left text-xs text-on-surface-variant hover:bg-surface-container">▤ 架构风险清单.html</button></div><div className="rounded-xl bg-surface-container-low p-4 text-xs leading-5 text-on-surface-variant"><strong className="mb-1 block text-on-surface">event_bus_config.yaml</strong>选择工作空间后可查看文件摘要、类型、大小和最近修改信息。</div></div></aside>}
        {idlePanel === 'bottom' && <section className="absolute inset-x-0 bottom-0 z-20 border-t border-border-subtle bg-[#17191e] text-[#d9dde7] shadow-2xl"><div className="flex h-11 items-center justify-between border-b border-white/10 px-4"><span className="flex items-center gap-2 text-xs font-semibold"><Terminal className="h-4 w-4 text-[#9b9afc]" />底部面板</span><button type="button" onClick={() => setIdlePanel(null)} aria-label="关闭底部面板" className="rounded-lg p-1.5 text-[#aeb4c2] hover:bg-white/10"><X className="h-4 w-4" /></button></div><div className="space-y-1 p-4 font-mono text-[11px] leading-5"><div><span className="text-[#9b9afc]">➜ notemeld-project</span> <span className="text-[#e8eaf0]">等待新的 Agent 指令</span></div><div className="text-[#9299a8]">Agent session ready · local runtime</div><div><span className="text-[#9b9afc]">➜</span> <span className="inline-block h-3 w-1.5 animate-pulse bg-[#9b9afc] align-middle" /></div></div></section>}
      </div>
    )
  }

  if (currentTask?.mode === 'chat' && currentTask.noteState !== 'ready' && !hasLearningCanvas && !hasSelectedDocument) {
    return (
      <div className="flex h-full min-h-0 w-full flex-col">
        <div ref={scrollAreaRootRef} className="min-h-0 flex-1">
          <ScrollArea className="h-full">
            <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-6 md:py-8">
              <ConversationMessages task={currentTask} compact={isMobile} />
            </div>
          </ScrollArea>
        </div>
        <div className="shrink-0 border-t border-border-subtle/60 bg-surface px-4 py-3 md:px-6 md:py-4">
          <div className="mx-auto w-full max-w-2xl md:max-w-3xl">
            <ChatComposer layout="bottom" />
            <p className="mt-2 text-center text-[11px] leading-5 text-on-surface-variant/65">
              支持网页文章、视频内容、AI 对话和随手记录。
            </p>
          </div>
        </div>
      </div>
    )
  }

  /** 生成中 / 失败：左侧聊天流 */
  if (!shouldShowSplitLayout && (status === 'loading' || status === 'failed')) {
    return (
      <div className="flex h-full min-h-0 w-full flex-col">
        <div ref={scrollAreaRootRef} className="min-h-0 flex-1">
          <ScrollArea className="h-full">
            <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-6 md:py-8">
              <ConversationMessages task={currentTask!} compact={isMobile} onRetry={handleRetry} onRetryChat={handleRetryChat} onSelectNoteResult={handleSelectNoteResult} onCancelTask={handleCancelTask} />
            </div>
          </ScrollArea>
        </div>
        <div className="shrink-0 border-t border-border-subtle/60 bg-surface px-4 py-3 md:px-6 md:py-4">
          <div className="mx-auto w-full max-w-2xl md:max-w-3xl">
            <ChatComposer layout="bottom" />
            <p className="mt-2 text-center text-[11px] leading-5 text-on-surface-variant/65">
              支持网页文章、视频内容、AI 对话和随手记录。
            </p>
          </div>
        </div>
      </div>
    )
  }

  /** 成功态：左聊天历史 + 右笔记看板（默认各占 50%，支持拖拽） */
  if (isMobile && shouldShowSplitLayout) {
    const mobileTabs: Array<{
      key: 'chat' | 'learning' | 'note' | 'wiki'
      label: string
    }> = [
      { key: 'chat', label: '对话' },
      ...(hasLearningCanvas ? [{ key: 'learning' as const, label: '白板' }] : []),
      ...(hasLearningCanvas || hasSelectedDocument
        ? [
            { key: 'note' as const, label: '笔记' },
          ]
        : []),
      ...(hasSelectedDocument ? [{ key: 'wiki' as const, label: 'Wiki' }] : []),
    ]

    return (
      <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-surface">
        <div
          className="grid h-11 shrink-0 border-b border-border-subtle/70 bg-white px-2 py-1"
          style={{ gridTemplateColumns: `repeat(${mobileTabs.length}, minmax(0, 1fr))` }}
        >
          {mobileTabs.map(item => (
            <button
              key={item.key}
              type="button"
              onClick={() => setMobileView(item.key)}
              className={cn(
                'rounded-lg text-[13px] font-medium transition-colors',
                mobileView === item.key
                  ? 'bg-primary text-white'
                  : 'text-on-surface-variant active:bg-surface-container',
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        {mobileView === 'chat' ? (
          <div className="flex min-h-0 flex-1 flex-col">
            <div ref={scrollAreaRootRef} className="min-h-0 flex-1">
              <ScrollArea className="h-full">
                <div className="mx-auto w-full max-w-2xl px-4 py-4">
                  <ConversationMessages
                    task={currentTask!}
                    compact
                    onRetry={handleRetry}
                    onRetryChat={handleRetryChat}
                    onSelectNoteResult={handleSelectNoteResult}
                    onCancelTask={handleCancelTask}
                  />
                </div>
              </ScrollArea>
            </div>
            <div className="shrink-0 border-t border-border-subtle/60 bg-surface px-4 py-3">
              <div className="mx-auto w-full max-w-2xl">
                <ChatComposer layout="bottom" />
              </div>
            </div>
          </div>
        ) : mobileView === 'learning' && hasLearningCanvas ? (
          <div className="min-h-0 flex-1 overflow-hidden bg-surface-container-low">
            {latestWhiteboardId && !useLegacyLearningCanvas ? (
              <WhiteboardPanel
                conversationId={currentTask!.id}
                whiteboardId={latestWhiteboardId}
                legacyCanvasId={latestLearningCanvasId || undefined}
                documents={currentTask?.documents || []}
                activeView="whiteboard"
                showTabs={false}
                onDeleteDocument={handleDeleteWhiteboardDocument}
                onWikiRetrySuccess={handleWikiRetrySuccess}
                onPublished={handleWhiteboardPublished}
              />
            ) : whiteboardSeedPending ? (
              renderWhiteboardSeedPending()
            ) : latestLearningCanvasId ? (
              <LearningCanvasCard
                conversationId={currentTask!.id}
                canvasId={latestLearningCanvasId}
                conversionError={activeWhiteboardSeedError || (!SEMANTIC_WHITEBOARD_ENABLED ? '语义白板已关闭，当前显示兼容研究图。' : undefined)}
                onRetryConversion={SEMANTIC_WHITEBOARD_ENABLED ? retryWhiteboardSeed : undefined}
              />
            ) : null}
          </div>
        ) : mobileView === 'note' && latestWhiteboardId && !useLegacyLearningCanvas ? (
          <div className="min-h-0 flex-1 overflow-hidden bg-white">
            <WhiteboardPanel
              conversationId={currentTask!.id}
              whiteboardId={latestWhiteboardId}
              legacyCanvasId={latestLearningCanvasId || undefined}
              documents={currentTask?.documents || []}
              activeView="note"
              showTabs={false}
              onDeleteDocument={handleDeleteWhiteboardDocument}
              onWikiRetrySuccess={handleWikiRetrySuccess}
              onPublished={handleWhiteboardPublished}
            />
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-hidden bg-white">
            <MarkdownViewer
              status={viewerStatus}
              content={currentTask?.markdown || ''}
              onDeleteDocument={handleDeleteCurrentDocument}
              onWikiRetrySuccess={handleWikiRetrySuccess}
              initialViewMode={mobileView === 'wiki' ? 'wiki' : 'preview'}
            />
          </div>
        )}
      </div>
    )
  }

  return (
    <div ref={splitContainerRef} className="nm-d03-workspace flex h-full min-h-0 w-full overflow-hidden">
      {/* 左侧：对话历史 + 输入 */}
      <div
        style={
          viewerCollapsed
            ? undefined
            : { width: `${chatRatio * 100}%` }
        }
        className={cn(
          'flex min-h-0 flex-col border-r border-border-subtle/60',
          viewerCollapsed ? 'flex-1' : 'shrink-0',
        )}
      >
        <div className="nm-d03-header flex h-12 shrink-0 items-center justify-between border-b border-border-subtle/60 px-4">
          <div className="min-w-0"><span className="block text-[10px] font-semibold tracking-[0.14em] text-primary">D03 · LOCAL AGENT</span><span className="mt-0.5 block truncate text-[13px] font-semibold text-on-surface">当前会话</span></div>
          <div className="flex items-center gap-1"><button type="button" onClick={() => void handleShareSession()} className="nm-d03-action" aria-label="分享当前会话" title="复制会话链接"><Share2 /></button><button type="button" className={cn('nm-d03-action', contextOpen && 'is-active')} onClick={() => setContextOpen(value => !value)} aria-label="切换置顶摘要" title="显示或隐藏置顶摘要"><Files /></button><button type="button" onClick={() => setIdlePanel('side')} className="nm-d03-action" aria-label="打开侧边文件面板" title="选择文件并查看内容"><PanelRightOpen /></button><button type="button" onClick={() => setIdlePanel('bottom')} className="nm-d03-action" aria-label="打开底部面板" title="命令行与运行日志"><PanelBottomOpen /></button><button
            onClick={() => setViewerCollapsed(v => !v)}
            className="nm-d03-action"
            title={viewerCollapsed ? '展开右侧面板' : '隐藏右侧面板'}
            aria-label={viewerCollapsed ? '展开右侧面板' : '隐藏右侧面板'}
          >
            {viewerCollapsed ? (
              <PanelRightOpen className="h-4 w-4" />
            ) : (
              <PanelRightClose className="h-4 w-4" />
            )}
          </button><button type="button" onClick={() => setContextOpen(value => !value)} className="nm-d03-action" aria-label="更多会话操作" title="显示或隐藏会话上下文"><MoreHorizontal /></button></div>
        </div>
        <div ref={scrollAreaRootRef} className="min-h-0 flex-1">
          <ScrollArea className="h-full">
            <div className="px-4 py-4">
              <ConversationMessages
                task={currentTask!}
                compact
                onRetry={handleRetry}
                onRetryChat={handleRetryChat}
                onSelectNoteResult={handleSelectNoteResult}
                onCancelTask={handleCancelTask}
              />
            </div>
          </ScrollArea>
        </div>
        <div className="shrink-0 border-t border-border-subtle/60 px-3 py-3">
          <ChatComposer layout="bottom" />
          <p className="mt-2 text-center text-[11px] leading-5 text-on-surface-variant/65">
            支持网页文章、视频内容、AI 对话和随手记录。
          </p>
        </div>
      </div>

      {/* 拖拽手柄 */}
      {!viewerCollapsed && (
        <div
          onMouseDown={startSplitDrag}
          className="group/resizer relative w-1 shrink-0 cursor-col-resize"
          aria-label="拖拽调整对话/右侧面板宽度"
        >
          <div className="absolute inset-y-0 left-0 w-1 transition-colors group-hover/resizer:bg-primary/40" />
        </div>
      )}

      {/* 右侧：学习面板 / 笔记看板 */}
      {!viewerCollapsed && (
        <div className="flex min-w-0 flex-1 flex-col bg-white">
          {latestWhiteboardId && !useLegacyLearningCanvas ? (
            <WhiteboardPanel
              conversationId={currentTask!.id}
              whiteboardId={latestWhiteboardId}
              legacyCanvasId={latestLearningCanvasId || undefined}
              documents={currentTask?.documents || []}
              activeView={panelView}
              onViewChange={view => setRightContentView(view === 'whiteboard' ? 'learning' : 'note')}
              onDeleteDocument={handleDeleteWhiteboardDocument}
              onWikiRetrySuccess={handleWikiRetrySuccess}
              onPublished={handleWhiteboardPublished}
            />
          ) : hasLearningCanvas ? (
            <div className="flex h-full min-h-0 flex-col">
              <div className="flex h-12 shrink-0 items-center gap-1 border-b border-border-subtle/60 px-4">
                <button
                  type="button"
                  onClick={() => setRightContentView('learning')}
                  className={cn(
                    'rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors',
                    rightContentView === 'learning'
                      ? 'bg-primary-light text-primary'
                      : 'text-on-surface-variant hover:bg-surface-container-low',
                  )}
                >
                  白板
                </button>
                <button
                  type="button"
                  onClick={() => setRightContentView('note')}
                  className={cn(
                    'rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors',
                    rightContentView === 'note'
                      ? 'bg-primary-light text-primary'
                      : 'text-on-surface-variant hover:bg-surface-container-low',
                  )}
                >
                  笔记
                </button>
              </div>
              {rightContentView === 'learning' && whiteboardSeedPending ? (
                <div className="min-h-0 flex-1">{renderWhiteboardSeedPending()}</div>
              ) : rightContentView === 'learning' && latestLearningCanvasId ? (
                <div className="min-h-0 flex-1 overflow-hidden bg-surface-container-low">
                  <LearningCanvasCard
                    conversationId={currentTask!.id}
                    canvasId={latestLearningCanvasId}
                    conversionError={activeWhiteboardSeedError || (!SEMANTIC_WHITEBOARD_ENABLED ? '语义白板已关闭，当前显示兼容研究图。' : undefined)}
                    onRetryConversion={SEMANTIC_WHITEBOARD_ENABLED ? retryWhiteboardSeed : undefined}
                  />
                </div>
              ) : hasSelectedDocument ? (
                <div className="min-h-0 flex-1">
                  <MarkdownViewer
                    status={viewerStatus}
                    content={currentTask?.markdown || ''}
                    onDeleteDocument={handleDeleteCurrentDocument}
                    onWikiRetrySuccess={handleWikiRetrySuccess}
                  />
                </div>
              ) : (
                <div className="flex min-h-0 flex-1 items-center justify-center px-6 text-center text-sm text-on-surface-variant">可编辑白板转换成功后即可发布标准笔记。</div>
              )}
            </div>
          ) : (
            <div className="min-h-0 flex-1">
              <MarkdownViewer
                status={viewerStatus}
                content={currentTask?.markdown || ''}
                onDeleteDocument={handleDeleteCurrentDocument}
                onWikiRetrySuccess={handleWikiRetrySuccess}
              />
            </div>
          )}
        </div>
      )}
      {contextOpen && <aside className="nm-d03-context-panel"><div className="nm-d03-context-header"><div><span className="nm-kicker">PINNED CONTEXT</span><strong>置顶摘要</strong></div><button type="button" onClick={() => setContextOpen(false)} aria-label="关闭置顶摘要"><PanelRightClose /></button></div><section><div className="nm-d03-context-title">输出内容 <button type="button" aria-label="添加产物"><Plus /></button></div><button type="button"><FileText />系统架构研究报告.md <small><ArrowUpRight /></small></button><button type="button"><FileCode2 />架构风险清单.html <small><ArrowUpRight /></small></button></section><section><div className="nm-d03-context-title">子智能体 <b>2</b></div><p><i className="is-running" />架构分析 Agent <small>运行中</small></p><p><i />资料检索 Agent <small>已完成</small></p></section><section><div className="nm-d03-context-title">后台进程 <b>1</b></div><div className="nm-d03-process"><strong>生成 Markdown 报告</strong><small>正在处理 · 42%</small><span><i /></span></div></section><section><div className="nm-d03-context-title">来源 <button type="button" aria-label="添加来源"><Plus /></button></div><button type="button"><FileText />2026-08-29-stitch-multiplatform-prompts.md</button><button type="button"><FileCode2 />event_bus_config.yaml</button></section></aside>}
      {idlePanel === 'side' && <aside className="nm-d03-file-panel"><div><strong><Files />选择文件</strong><button type="button" onClick={() => setIdlePanel(null)} aria-label="关闭侧边文件面板"><X /></button></div><button type="button" className="is-selected"><FileCode2 />event_bus_config.yaml</button><button type="button"><FileText />系统架构研究报告.md</button><button type="button"><FileText />架构风险清单.html</button><p><strong>event_bus_config.yaml</strong>选择工作空间后可查看文件摘要、类型、大小和最近修改信息。</p></aside>}
      {idlePanel === 'bottom' && <section className="nm-d03-bottom-panel"><div><strong><Terminal />底部面板</strong><button type="button" onClick={() => setIdlePanel(null)} aria-label="关闭底部面板"><X /></button></div><p><span>➜ notemeld-project</span> 等待新的 Agent 指令</p><p>Agent session ready · local runtime</p><p><span>➜</span> <i /></p></section>}
    </div>
  )
}

const ConversationMessages: FC<{
  task: Task
  compact?: boolean
  onRetry?: (taskId?: string) => void
  onRetryChat?: () => void
  onSelectNoteResult?: (taskId: string) => void
  onCancelTask?: (cardId: string) => void
}> = ({
  task,
  compact,
  onRetry,
  onRetryChat,
  onSelectNoteResult,
  onCancelTask,
}) => {
  const items = buildConversationTimeline(task)
  if (!items.length) return null

  return (
    <div className="mb-6 space-y-5">
      {items.map(item => {
        const message = item.message as ConversationMessage

        return (
          <ConversationMessageRenderer
            key={item.id}
            message={message}
            conversationId={task.id}
            compact={compact}
            taskPlatform={task.platform || task.formData?.platform}
            onRetry={onRetry}
            onRetryChat={onRetryChat}
            onSelectNoteResult={onSelectNoteResult}
            onCancelTask={onCancelTask}
          />
        )
      })}
    </div>
  )
}

export default HomePage
