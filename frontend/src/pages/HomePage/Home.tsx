import { FC, useMemo, useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { PanelRightClose, PanelRightOpen } from 'lucide-react'
import ChatComposer from '@/pages/HomePage/components/ChatComposer'
import MarkdownViewer from '@/pages/HomePage/components/MarkdownViewer'
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

type ViewStatus = 'idle' | 'loading' | 'success' | 'failed'

export const HomePage: FC = () => {
  const { taskId } = useParams<{ taskId?: string }>()
  const navigate = useNavigate()
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
  /** 对话栏宽度比例（0-1），默认 0.5 即各占一半 */
  const [chatRatio, setChatRatio] = useState(0.5)
  const [mobileView, setMobileView] = useState<'chat' | 'note' | 'wiki'>('chat')
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
  }, [currentTask?.status, currentTask?.id, currentTask?.noteState, currentTask?.mode])

  const hasSelectedDocument = Boolean(currentTask?.activeDocumentTaskId)
    && (currentTask?.documents || []).some(document => document.taskId === currentTask?.activeDocumentTaskId && document.content)
  const viewerStatus: ViewStatus = hasSelectedDocument ? 'success' : 'idle'
  const shouldShowSplitLayout = status === 'success' || hasSelectedDocument

  useEffect(() => {
    if (!isMobile) return
    if (status === 'success' || hasSelectedDocument) {
      setMobileView('note')
      return
    }
    setMobileView('chat')
  }, [isMobile, status, hasSelectedDocument, currentTask?.id])

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

  const handleDeleteCurrentDocument = async () => {
    if (!currentTask?.id || !currentTask.activeDocumentTaskId) return
    const confirmed = window.confirm('删除这篇笔记？此操作会移除对应 Wiki 贡献。')
    if (!confirmed) return
    await deleteNoteDocument(currentTask.id, currentTask.activeDocumentTaskId)
  }

  const handleWikiRetrySuccess = () => {
    if (!currentTask?.id) return
    loadConversation(currentTask.id).catch(err => {
      console.error('刷新 Wiki 状态失败', err)
    })
  }

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
      <div className="flex h-full w-full flex-col items-center justify-center px-4 md:px-6">
        <div className="w-full max-w-2xl">
          <div className="mb-9 text-center">
            <h1 className="font-display mb-4 text-[42px] font-extrabold leading-tight tracking-[-0.04em] text-on-surface">
              More Than <span className="text-primary">Notes</span>
            </h1>
            <p className="mx-auto max-w-xl text-[15px] leading-relaxed text-on-surface-variant">
              让每一次阅读、观看、对话，沉淀为你的专属知识库
            </p>
          </div>
          <ChatComposer layout="hero" />
          <p className="mt-4 text-center text-[12px] text-on-surface-variant/70">
            支持网页文章、视频内容、AI 对话和随手记录。
          </p>
        </div>
      </div>
    )
  }

  if (currentTask?.mode === 'chat' && currentTask.noteState !== 'ready') {
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
              <ConversationMessages task={currentTask!} compact={isMobile} onRetry={handleRetry} onRetryChat={handleRetryChat} onSelectNoteResult={handleSelectNoteResult} />
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
    const mobileTabs: Array<{ key: 'chat' | 'note' | 'wiki'; label: string }> = [
      { key: 'chat', label: '对话' },
      { key: 'note', label: '笔记' },
      { key: 'wiki', label: 'Wiki' },
    ]

    return (
      <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-surface">
        <div className="grid h-11 shrink-0 grid-cols-3 border-b border-border-subtle/70 bg-white px-2 py-1">
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
    <div ref={splitContainerRef} className="flex h-full min-h-0 w-full overflow-hidden">
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
        <div className="flex h-12 shrink-0 items-center justify-between border-b border-border-subtle/60 px-4">
          <span className="text-[13px] font-medium text-on-surface-variant">对话</span>
          <button
            onClick={() => setViewerCollapsed(v => !v)}
            className="rounded p-1.5 text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary"
            title={viewerCollapsed ? '展开笔记' : '隐藏笔记'}
          >
            {viewerCollapsed ? (
              <PanelRightOpen className="h-4 w-4" />
            ) : (
              <PanelRightClose className="h-4 w-4" />
            )}
          </button>
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
          aria-label="拖拽调整对话/笔记宽度"
        >
          <div className="absolute inset-y-0 left-0 w-1 transition-colors group-hover/resizer:bg-primary/40" />
        </div>
      )}

      {/* 右侧：笔记看板 */}
      {!viewerCollapsed && (
        <div className="min-w-0 flex-1 bg-white">
          <MarkdownViewer
            status={viewerStatus}
            content={currentTask?.markdown || ''}
            onDeleteDocument={handleDeleteCurrentDocument}
            onWikiRetrySuccess={handleWikiRetrySuccess}
          />
        </div>
      )}
    </div>
  )
}

const ConversationMessages: FC<{
  task: Task
  compact?: boolean
  onRetry?: (taskId?: string) => void
  onRetryChat?: () => void
  onSelectNoteResult?: (taskId: string) => void
}> = ({
  task,
  compact,
  onRetry,
  onRetryChat,
  onSelectNoteResult,
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
            compact={compact}
            taskPlatform={task.platform || task.formData?.platform}
            onRetry={onRetry}
            onRetryChat={onRetryChat}
            onSelectNoteResult={onSelectNoteResult}
          />
        )
      })}
    </div>
  )
}

export default HomePage
