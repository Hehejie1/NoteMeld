import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import {
  ArrowUp,
  Brain,
  ChevronDown,
  ChevronRight,
  File as FileIcon,
  FileCode,
  FileCode2,
  FileImage,
  FilePlus,
  FileText,
  Folder,
  FolderOpen,
  FolderPlus,
  MoreHorizontal,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  CornerUpLeft,
  Trash2,
  Terminal,
  X,
} from 'lucide-react'
import CloudClient, { type CloudAttachment, type CloudModel } from '../../services/cloud'
import { useCloudSession } from '../../hooks/useCloudSession'
import { localizeCloudError, useCloudLocale } from '../../pages/CloudPage/cloudLocale'
import { CloudApprovalList } from '../CloudApprovalList'
import ChatMarkdown from '../../pages/HomePage/components/ChatMarkdown'

export interface CloudSessionPanelProps {
  client: CloudClient
  sessionId?: string
  onSessionCreated?: (session: CloudSessionLike) => void
}

type CloudSessionLike = { id: string; workspace_id: string }

type HistoryCommand = {
  id: string
  sequence: number
  input_text?: string
  status: string
  created_at: number
}

type ThreadEvent = {
  sequence: number
  event_type: string
  payload?: {
    command_sequence?: number
    command_id?: string
    output?: string
    status?: string
    error?: { message?: string }
    reasoning?: string[]
  }
  created_at: number
}

type Turn = {
  key: string
  user?: string
  assistant?: string
  // 思考过程：默认折叠，展开显示本轮思考（可多段）。
  reasoning?: string[]
  error?: string
  time?: number
  // 命令已入库但尚无终态事件：渲染“思考中”而不是留白。
  pending?: boolean
  // 是否仍在流式接收。
  streaming?: boolean
}

export function CloudSessionPanel({
  client,
  sessionId,
  onSessionCreated,
}: CloudSessionPanelProps) {
  const { t } = useCloudLocale()
  const { session, events } = useCloudSession(client, sessionId)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [model, setModel] = useState(session?.model_id || '')
  const [auto, setAuto] = useState(!session?.model_id)
  const [fullAccess, setFullAccess] = useState(false)
  const [bottomOpen, setBottomOpen] = useState(false)
  const [sideOpen, setSideOpen] = useState(false)
  const [sideWidth, setSideWidth] = useState(290)
  const [bottomHeight, setBottomHeight] = useState(220)
  const [attachmentName, setAttachmentName] = useState('')
  const [attachmentPayload, setAttachmentPayload] = useState<CloudAttachment | null>(null)
  const [refs, setRefs] = useState<Array<{ id: string; path: string }>>([])
  const [historyCommands, setHistoryCommands] = useState<HistoryCommand[]>([])
  // 当前正在流式接收的回合：点击发送立即出现（用户气泡 + 思考/正文增量）。
  const [streamingTurn, setStreamingTurn] = useState<Turn | null>(null)
  const threadRef = useRef<HTMLDivElement>(null)
  const pollTimers = useRef<number[]>([])

  // 读取该会话的用户命令（消息）。
  const reloadCommands = useCallback(() => {
    if (!sessionId) return Promise.resolve()
    return client
      .listCommands(sessionId, 0, 500)
      .then(value => setHistoryCommands(value as HistoryCommand[]))
      .catch(() => undefined)
  }, [client, sessionId])

  useEffect(() => {
    void reloadCommands()
  }, [reloadCommands, events.length])

  // model 始终保存一个可发送的具体模型；auto 决定标签显示与选择态。
  useEffect(() => {
    let active = true
    void client
      .listModels()
      .then(value => {
        if (!active || session?.model_id) return
        setModel(previous =>
          previous || value.find(item => item.is_default && item.enabled)?.id || ''
        )
      })
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [client, session?.model_id])

  useEffect(
    () => () => pollTimers.current.forEach(timer => window.clearInterval(timer)),
    []
  )

  // 新消息到达时滚动到底部。
  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight })
  }, [events.length, historyCommands.length, streamingTurn])

  // 命令 + turn 事件按 command_sequence 配对，避免仅靠位置索引错位。
  const commandById = new Map(historyCommands.map(command => [command.id, command]))
  const outputByCommand = new Map<string, {
    text?: string
    error?: string
    reasoning?: string[]
  }>()
  ;(events as ThreadEvent[]).forEach(event => {
    if (!event.event_type.startsWith('turn.')) return
    const seq = event.payload?.command_sequence
    const command =
      historyCommands.find(item => item.sequence === seq) ??
      (event.payload?.command_id ? commandById.get(event.payload.command_id) : undefined)
    if (!command) return
    if (event.event_type === 'turn.failed' || event.event_type === 'turn.needs_attention') {
      outputByCommand.set(command.id, {
        error: event.payload?.error?.message ?? t('session.failed', '执行失败'),
      })
    } else if (event.event_type === 'turn.completed') {
      const reasoning = Array.isArray(event.payload?.reasoning)
        ? event.payload?.reasoning.filter((part: unknown) => typeof part === 'string')
        : undefined
      outputByCommand.set(command.id, {
        text: event.payload?.output,
        ...(reasoning?.length ? { reasoning } : {}),
      })
    }
  })

  const turns: Turn[] = historyCommands.map(command => {
    const result = outputByCommand.get(command.id)
    const pending =
      result === undefined && command.status !== 'completed' && command.status !== 'failed'
    // 兜底：命令已标记 failed 但事件暂未配对时，也显示失败而不是留白。
    const fallbackError =
      result === undefined && command.status === 'failed'
        ? t('session.failed', '执行失败')
        : undefined
    return {
      key: command.id,
      user: command.input_text,
      assistant: result?.text,
      reasoning: result?.reasoning,
      error: result?.error ?? fallbackError,
      time: command.created_at,
      pending,
    }
  })

  if (!sessionId)
    return (
      <NewCloudSessionView
        client={client}
        onCreated={onSessionCreated}
        model={model}
      />
    )

  async function loadAttachment(file: File) {
    if (file.size > 10 * 1024 * 1024) {
      setSendError(t('session.attachment-size', '单个附件不能超过 10 MiB'))
      return
    }
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onerror = () => reject(new Error(t('session.attachment-read-failed', '无法读取附件')))
      reader.onload = () => resolve(String(reader.result))
      reader.readAsDataURL(file)
    })
    const comma = dataUrl.indexOf(',')
    setAttachmentName(file.name || t('session.attachment-name', '剪贴板截图'))
    setAttachmentPayload({
      name: file.name || 'attachment',
      size: file.size,
      type: file.type || 'application/octet-stream',
      content_base64: comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl,
    })
    setSendError(null)
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const text = input.trim()
    if (!text || sending || !model || !sessionId) return
    setSending(true)
    setSendError(null)
    // 附件暂存于此（当前流式接口未透传，先随发送清空）。
    void attachmentPayload
    setAttachmentPayload(null)
    setAttachmentName('')
    // 立刻清空输入并出现流式回合（用户气泡 + 思考/正文逐块更新）。
    setInput('')
    const turnId = `streaming-${Date.now()}`
    const live: Turn = {
      key: turnId,
      user: text,
      time: Math.floor(Date.now() / 1000),
      reasoning: [],
      pending: true,
      streaming: true,
    }
    setStreamingTurn(live)
    const patch = (mutator: (turn: Turn) => Turn) =>
      setStreamingTurn(current => (current ? mutator(current) : current))
    try {
      await client.streamTurn(
        sessionId,
        {
          input: text,
          requestId: crypto.randomUUID(),
          ...(auto ? {} : { model_id: model }),
          authorization_mode: fullAccess ? 'full' : 'default',
        },
        chunk => {
          const type = String(chunk.type)
          if (type === 'reasoning') {
            patch(current => {
              const reasoning = [...(current.reasoning ?? [''])]
              reasoning[reasoning.length - 1] += String(chunk.text ?? '')
              return { ...current, reasoning, pending: false }
            })
          } else if (type === 'delta') {
            patch(current => ({
              ...current,
              pending: false,
              assistant: (current.assistant ?? '') + String(chunk.text ?? ''),
            }))
          } else if (type === 'error') {
            patch(current => ({
              ...current,
              streaming: false,
              error: String(chunk.message ?? t('session.failed', '执行失败')),
            }))
          } else if (type === 'done') {
            patch(current => ({ ...current, streaming: false, pending: false }))
          }
        }
      )
    } catch (reason) {
      patch(current => ({
        ...current,
        streaming: false,
        error: localizeCloudError(reason instanceof Error ? reason.message : 'send failed', t),
      }))
    } finally {
      setSending(false)
      // 重新拉取真实历史后，用持久化回合替换流式占位。
      await reloadCommands()
      window.setTimeout(() => setStreamingTurn(null), 400)
    }
  }

  return (
    <section className="relative flex h-full min-h-0 flex-col overflow-hidden">
      <header className="flex flex-none items-center gap-3 border-b border-[var(--border-subtle)] bg-[var(--surface)] px-5 py-3">
        <h1 className="min-w-0 flex-1 truncate text-[15px] font-semibold text-[var(--on-surface)]">
          {session?.title || t('session.title', '云端会话')}
        </h1>
        <div className="flex items-center gap-1">
          <IconToggle
            active={bottomOpen}
            label={t('session.bottom-panel', '底部命令行')}
            onClick={() => setBottomOpen(value => !value)}
          >
            <BottomPanelIcon />
          </IconToggle>
          <IconToggle
            active={sideOpen}
            label={t('session.side-panel', '侧边菜单')}
            onClick={() => setSideOpen(value => !value)}
          >
            <SidePanelIcon />
          </IconToggle>
        </div>
      </header>

      {/* 中部：对话 + 可选侧边资源管理器（flex 行，内部独立滚动） */}
      <div className="flex min-h-0 flex-1">
        <div ref={threadRef} className="min-h-0 flex-1 overflow-auto px-5 py-5">
          {!turns.length ? (
            <p className="grid h-full place-items-center text-sm text-[var(--on-surface-variant)]">
              {t('session.start-hint', '发送一条消息开始对话。')}
            </p>
          ) : (
            <div className="mx-auto max-w-3xl space-y-6">
              {turns.map(turn => (
                <TurnBlock key={turn.key} turn={turn} />
              ))}
              {streamingTurn ? <TurnBlock key={streamingTurn.key} turn={streamingTurn} /> : null}
            </div>
          )}
        </div>

        {sideOpen ? (
          <>
            <VerticalResizeHandle onResize={delta => setSideWidth(w => Math.min(520, Math.max(220, w - delta)))} />
            <div style={{ width: sideWidth }} className="flex-none overflow-hidden">
              <SideExplorer
                client={client}
                workspaceId={session?.workspace_id || 'default'}
                refs={refs}
                onAddRef={path =>
                  setRefs(current =>
                    current.some(item => item.path === path)
                      ? current
                      : [...current, { id: crypto.randomUUID(), path }]
                  )
                }
                onRemoveRef={id => setRefs(current => current.filter(item => item.id !== id))}
              />
            </div>
          </>
        ) : null}
      </div>

      {/* 输入区：浮动卡片 */}
      <form onSubmit={submit} className="flex-none px-5 pb-4">
        <div className="mx-auto max-w-3xl">
          <CloudApprovalBar client={client} sessionId={sessionId} />
          <div className="cloud-session-composer rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface)] p-3 shadow-[0_4px_16px_rgba(0,0,0,0.06)]">
            {refs.length ? (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {refs.map(ref => (
                  <span
                    key={ref.id}
                    className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-container-low)] px-2 py-1 text-[11px]"
                  >
                    <FileText className="h-3 w-3 text-[var(--primary)]" />
                    <span className="max-w-[150px] truncate">{ref.path.split('/').pop()}</span>
                    <button
                      type="button"
                      aria-label={t('session.remove-ref', '移除引用')}
                      onClick={() => setRefs(current => current.filter(item => item.id !== ref.id))}
                      className="text-[var(--on-surface-variant)] hover:text-[var(--on-surface)]"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            ) : null}
            {sendError ? (
              <p role="alert" className="mb-2 text-xs text-[var(--error)]">{sendError}</p>
            ) : null}
            {attachmentName ? (
              <p className="mb-2 text-xs text-[var(--on-surface-variant)]">
                <span className="mr-1">📎</span>{attachmentName}
              </p>
            ) : null}
            <textarea
              value={input}
              onChange={event => setInput(event.target.value)}
              onPaste={event => {
                const file = Array.from(event.clipboardData.files).find(item =>
                  item.type.startsWith('image/')
                )
                if (!file) return
                event.preventDefault()
                void loadAttachment(file)
              }}
              rows={1}
              maxLength={4000}
              placeholder={t('session.placeholder', '继续告诉 Agent 你要完成什么…')}
              className="max-h-40 min-h-[1.75rem] w-full resize-none border-0 bg-transparent px-1 py-1 text-[13px] outline-none placeholder:text-[var(--on-surface-variant)]"
            />
            <div className="mt-1 flex items-center gap-2">
              <label className="flex cursor-pointer items-center gap-1.5 px-1 py-1 text-xs font-semibold text-[var(--primary)]">
                <Plus className="h-4 w-4" />
                {t('session.add', '添加')}
                <input
                  type="file"
                  className="sr-only"
                  onChange={event => {
                    const file = event.target.files?.[0]
                    if (file) void loadAttachment(file)
                  }}
                />
              </label>
              <PermissionSelect fullAccess={fullAccess} onChange={setFullAccess} />
              <span className="flex-1" />
              <ModelSelect
                model={model}
                auto={auto}
                onChange={(next, nextAuto) => {
                  setModel(next)
                  setAuto(nextAuto)
                }}
                client={client}
              />
              <button
                type="submit"
                aria-label={t('session.send', '发送')}
                disabled={sending || !input.trim() || !model}
                title={!model ? t('session.model-hint', '请先在设置中配置模型') : ''}
                className="grid h-9 w-9 place-items-center rounded-full bg-[var(--primary)] text-white disabled:opacity-40"
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </form>

      {bottomOpen ? (
        <>
          <HorizontalResizeHandle onResize={delta => setBottomHeight(h => Math.min(Math.max(120, window.innerHeight * 0.6), Math.max(120, h + delta)))} />
          <div style={{ height: bottomHeight }} className="flex-none overflow-hidden">
            <BottomTerminal client={client} sessionId={sessionId} />
          </div>
        </>
      ) : null}
    </section>
  )
}

// 单个对话回合：时间默认隐藏、hover 才显示；AI 卡片含可折叠思考 + Markdown。
function TurnBlock({ turn }: { turn: Turn }) {
  const { t } = useCloudLocale()
  const [reasoningOpen, setReasoningOpen] = useState(false)
  const reasoning = turn.reasoning?.filter(part => part && part.trim()) ?? []
  const hasAnswer = turn.assistant !== undefined && turn.assistant.length > 0
  return (
    <div className="cloud-turn group space-y-2">
      <div className="flex justify-end">
        <time className="cloud-turn-time block text-[11px] font-normal text-[var(--on-surface-variant)]">
          {turn.time ? new Date(turn.time * 1000).toLocaleString() : ''}
        </time>
      </div>
      <div className="flex justify-end">
        <div className="max-w-[82%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-[var(--primary)] px-4 py-3 text-[13px] leading-relaxed text-white">
          {turn.user}
        </div>
      </div>
      {turn.error ? (
        <div className="flex justify-start">
          <div className="max-w-[82%] rounded-2xl rounded-bl-sm border border-[var(--border-subtle)] bg-[var(--surface)] px-4 py-3 text-[13px] leading-relaxed shadow-sm">
            <span className="text-[var(--error)]">{turn.error}</span>
          </div>
        </div>
      ) : null}
      {reasoning.length ? (
        <div className="flex justify-start">
          <div className="max-w-[92%] overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-container-low,transparent)]">
            <button
              type="button"
              onClick={() => setReasoningOpen(value => !value)}
              className="flex w-full items-center gap-1.5 px-3 py-1.5 text-[12px] text-[var(--on-surface-variant)] hover:bg-[var(--surface-container)]"
              aria-expanded={reasoningOpen}
            >
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${reasoningOpen ? '' : '-rotate-90'}`}
              />
              <Brain className="h-3.5 w-3.5" />
              <span>{t('session.thought', '思考过程')}</span>
              {turn.streaming && !hasAnswer ? <ThinkingDots /> : null}
            </button>
            {reasoningOpen ? (
              <div className="space-y-2 border-t border-[var(--border-subtle)] px-3 py-2">
                {reasoning.map((part, index) => (
                  <div
                    key={index}
                    className="whitespace-pre-wrap text-[12px] leading-5 text-[var(--on-surface-variant)]"
                  >
                    {part}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
      {hasAnswer ? (
        <div className="flex justify-start">
          <div className="max-w-[92%] rounded-2xl rounded-bl-sm border border-[var(--border-subtle)] bg-[var(--surface)] px-4 py-3 shadow-sm">
            <ChatMarkdown content={turn.assistant ?? ''} />
          </div>
        </div>
      ) : turn.pending ? (
        <div className="flex justify-start">
          <div className="flex items-center gap-2 rounded-2xl rounded-bl-sm border border-[var(--border-subtle)] bg-[var(--surface)] px-4 py-3 text-[13px] text-[var(--on-surface-variant)] shadow-sm">
            <ThinkingDots />
            <span>{t('session.thinking', '思考中')}</span>
          </div>
        </div>
      ) : null}
    </div>
  )
}

// “思考中”的三点动画，让等待过程有即时反馈而不是空白。
function ThinkingDots() {
  return (
    <span className="flex items-center gap-1" aria-hidden="true">
      <span className="cloud-thinking-dot" />
      <span className="cloud-thinking-dot" style={{ animationDelay: '0.15s' }} />
      <span className="cloud-thinking-dot" style={{ animationDelay: '0.3s' }} />
    </span>
  )
}

/* ---------------- Header toggles ---------------- */

function IconToggle({
  active,
  label,
  onClick,
  children,
}: {
  active: boolean
  label: string
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      onClick={onClick}
      className={`grid h-8 w-8 place-items-center rounded text-[var(--on-surface-variant)] hover:bg-[var(--surface-container)] ${active ? 'bg-[var(--primary-light)] text-[var(--primary)]' : ''}`}
    >
      {children}
    </button>
  )
}

// 与原型一致使用 panel-bottom / panel-right 图标语义。
function BottomPanelIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="3" y1="15" x2="21" y2="15" />
    </svg>
  )
}
function SidePanelIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="15" y1="4" x2="15" y2="20" />
    </svg>
  )
}

/* ---------------- Popover (antd Select Dropdown 风格) ---------------- */

function usePopoverPosition(
  triggerRef: React.RefObject<HTMLButtonElement | null>,
  panelRef: React.RefObject<HTMLDivElement | null>
) {
  const [rect, setRect] = useState<{ top: number; left: number; width: number; up: boolean } | null>(null)

  const measure = useCallback(() => {
    const trigger = triggerRef.current
    const panel = panelRef.current
    if (!trigger || !panel) return
    const r = trigger.getBoundingClientRect()
    const h = panel.offsetHeight
    const spaceBelow = window.innerHeight - r.bottom
    const spaceAbove = r.top
    const up = spaceBelow < h && spaceAbove > spaceBelow
    const width = Math.max(r.width, 200)
    let left = r.left
    if (left + width > window.innerWidth - 8) left = Math.max(8, window.innerWidth - width - 8)
    const top = up ? r.top - Math.min(h, spaceAbove - 10) - 6 : r.bottom + 6
    setRect({ top, left, width, up })
  }, [triggerRef, panelRef])

  return { rect, measure }
}

// antd Trigger 风格：单一稳定的 document mousedown 监听器，根据是否点中
// trigger / panel 决定开合；trigger 本身不再绑 onClick，避免同一次点击与
// 外部关闭、选项点击竞态。
function useSelectOpen() {
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const openRef = useRef(false)
  const [open, setOpenState] = useState(false)

  const setOpen = useCallback((value: boolean) => {
    openRef.current = value
    setOpenState(value)
  }, [])

  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node
      const inTrigger = triggerRef.current?.contains(target)
      const inPanel = panelRef.current?.contains(target)
      if (inTrigger) {
        setOpen(!openRef.current)
        return
      }
      if (!inPanel) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    const onResize = () => setOpen(false)
    // 仅在可滚动祖先发生滚动时关闭；fixed 弹层与 trigger 自身不在滚动容器内，
    // 打开瞬间因布局触发的 scroll 事件不会误关。
    const onScroll = (event: Event) => {
      const node = event.target
      if (!(node instanceof HTMLElement)) return
      if (node.contains(triggerRef.current)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', onResize)
    window.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('scroll', onScroll, true)
    }
  }, [setOpen])

  return { triggerRef, panelRef, open, setOpen }
}

function PermissionSelect({
  fullAccess,
  onChange,
}: {
  fullAccess: boolean
  onChange: (full: boolean) => void
}) {
  const { t } = useCloudLocale()
  const { triggerRef, panelRef, open } = useSelectOpen()
  const { rect, measure } = usePopoverPosition(triggerRef, panelRef)

  useLayoutEffect(() => {
    if (open) measure()
  }, [open, measure])

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-[var(--on-surface-variant)] hover:bg-[var(--surface-container)]"
      >
        <ShieldIcon />
        {fullAccess ? t('session.full-access', '完全授权') : t('session.permission-default', '默认权限')}
        <ChevronDown className="h-3 w-3" />
      </button>
      {open
        ? createPortal(
            <div
              ref={panelRef}
              className="fixed z-[1000] max-h-80 w-max max-w-[320px] overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface)] p-2 text-[var(--on-surface)] shadow-[0_6px_16px_rgba(0,0,0,0.08),0_9px_28px_rgba(0,0,0,0.05)]"
              style={
                rect
                  ? { top: rect.top, left: rect.left, minWidth: rect.width }
                  : { visibility: 'hidden' }
              }
            >
              <p className="m-0 text-[13px] leading-relaxed text-[var(--on-surface-variant)]">
                {fullAccess
                  ? t('session.perm-full-hint', '当前为完全授权，所有操作都会在安全沙箱约束内执行。')
                  : t('session.perm-default-hint', '当前为默认权限，常规操作直接执行，高风险操作会请求你的允许。')}
              </p>
              <hr className="my-3 border-0 border-t border-[var(--border-subtle)]" />
              <label className="flex cursor-pointer items-center justify-between gap-6 text-sm">
                <span>{t('session.allow-full', '允许完全访问')}</span>
                <input
                  type="checkbox"
                  checked={fullAccess}
                  onChange={event => {
                    onChange(event.target.checked)
                  }}
                  className="h-5 w-9 accent-[var(--primary)]"
                />
              </label>
            </div>,
            document.body
          )
        : null}
    </>
  )
}

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  )
}

function ModelSelect({
  model,
  auto,
  onChange,
  client,
}: {
  model: string
  auto: boolean
  onChange: (id: string, nextAuto: boolean) => void
  client: CloudClient
}) {
  const { t } = useCloudLocale()
  const { triggerRef, panelRef, open, setOpen } = useSelectOpen()
  const [models, setModels] = useState<CloudModel[]>([])
  const { rect, measure } = usePopoverPosition(triggerRef, panelRef)

  useEffect(() => {
    if (!open) return
    let active = true
    void client
      .listModels()
      .then(value => active && setModels(value))
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [open, client])

  useLayoutEffect(() => {
    if (open) measure()
  }, [open, models, measure])

  const enabled = models.filter(item => item.enabled)
  const currentName = enabled.find(item => item.id === model)?.name

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        title={model ? '' : t('session.model-hint', '请先在设置中配置模型')}
        className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-[var(--on-surface-variant)] hover:bg-[var(--surface-container)]"
      >
        <SparklesIcon />
        {auto ? t('session.model-auto', 'Auto') : currentName || t('session.no-model', '暂无模型')}
        <ChevronDown className="h-3 w-3" />
      </button>
      {open
        ? createPortal(
            <div
              ref={panelRef}
              className="fixed z-[1000] max-h-80 w-max max-w-[320px] overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface)] p-2 text-[var(--on-surface)] shadow-[0_6px_16px_rgba(0,0,0,0.08),0_9px_28px_rgba(0,0,0,0.05)]"
              style={
                rect
                  ? { top: rect.top, left: rect.left, minWidth: rect.width }
                  : { visibility: 'hidden' }
              }
            >
              {!enabled.length ? (
                <p className="m-0 text-[13px] text-[var(--on-surface-variant)]">
                  {t('session.no-model-available', '没有可用模型，请先到设置中添加模型。')}
                </p>
              ) : (
                <>
                  <ModelChoice
                    selected={auto}
                    title="Auto"
                    subtitle={t('session.auto-sub', '按发送的文件自动匹配，报错自动切换')}
                    trailing={t('session.auto-tag', '自动')}
                    onClick={() => {
                      onChange(model, true)
                      setOpen(false)
                    }}
                  />
                  {enabled.map(item => (
                    <ModelChoice
                      key={item.id}
                      selected={!auto && item.id === model}
                      title={item.name}
                      subtitle={item.model}
                      onClick={() => {
                        onChange(item.id, false)
                        setOpen(false)
                      }}
                    />
                  ))}
                </>
              )}
            </div>,
            document.body
          )
        : null}
    </>
  )
}

function ModelChoice({
  selected,
  title,
  subtitle,
  trailing,
  onClick,
}: {
  selected: boolean
  title: string
  subtitle: string
  trailing?: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-selected={selected}
      onClick={onClick}
      className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-2 text-left text-xs hover:bg-[var(--primary-light)]"
    >
      <span className="flex flex-col gap-0.5">
        <strong className={`text-[12px] font-semibold ${selected ? 'text-[var(--primary)]' : 'text-[var(--on-surface)]'}`}>
          {title}
        </strong>
        <small className="text-[11px] font-normal text-[var(--on-surface-variant)]">{subtitle}</small>
      </span>
      {trailing ? <span className="flex-none text-[11px] text-[var(--on-surface-variant)]">{trailing}</span> : null}
    </button>
  )
}

function SparklesIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4">
      <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z" />
    </svg>
  )
}

/* ---------------- Resize handles ---------------- */

function VerticalResizeHandle({ onResize }: { onResize: (delta: number) => void }) {
  const startX = useRef(0)
  const [dragging, setDragging] = useState(false)
  return (
    <div
      onPointerDown={event => {
        event.preventDefault()
        startX.current = event.clientX
        setDragging(true)
        const move = (e: PointerEvent) => onResize(startX.current - e.clientX)
        const up = () => {
          setDragging(false)
          window.removeEventListener('pointermove', move)
          window.removeEventListener('pointerup', up)
        }
        window.addEventListener('pointermove', move)
        window.addEventListener('pointerup', up)
      }}
      className={`relative w-0 flex-none cursor-col-resize after:absolute after:inset-y-0 after:-inset-x-[3px] after:transition-colors ${dragging ? 'after:bg-[var(--primary)]' : 'hover:after:bg-[var(--primary)]'}`}
      title="拖拽调整侧边区域宽度"
    />
  )
}

function HorizontalResizeHandle({ onResize }: { onResize: (delta: number) => void }) {
  const startY = useRef(0)
  const [dragging, setDragging] = useState(false)
  return (
    <div
      onPointerDown={event => {
        event.preventDefault()
        startY.current = event.clientY
        setDragging(true)
        const move = (e: PointerEvent) => onResize(startY.current - e.clientY)
        const up = () => {
          setDragging(false)
          window.removeEventListener('pointermove', move)
          window.removeEventListener('pointerup', up)
        }
        window.addEventListener('pointermove', move)
        window.addEventListener('pointerup', up)
      }}
      className={`relative h-0 flex-none cursor-row-resize after:absolute after:-inset-y-[3px] after:inset-x-0 after:transition-colors ${dragging ? 'after:bg-[var(--primary)]' : 'hover:after:bg-[var(--primary)]'}`}
      title="拖拽调整底部区域高度"
    />
  )
}

/* ---------------- Side Explorer ---------------- */

type TreeNode = {
  name: string
  path: string
  type: 'folder' | 'file'
  bytes?: number
  expanded: boolean
  children: TreeNode[]
}

function buildTree(files: Array<{ path: string; bytes?: number }>): TreeNode {
  const root: TreeNode = { name: 'NoteMeld', path: '', type: 'folder', expanded: true, children: [] }
  for (const file of files) {
    const parts = file.path.split('/').filter(Boolean)
    let current = root
    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1
      const childPath = parts.slice(0, index + 1).join('/')
      let child = current.children.find(node => node.name === part)
      if (!child) {
        child = {
          name: part,
          path: childPath,
          type: isFile ? 'file' : 'folder',
          expanded: false,
          children: [],
          ...(isFile ? { bytes: file.bytes } : {}),
        }
        current.children.push(child)
      }
      current = child
    })
  }
  return root
}

function iconForNode(name: string, type: 'folder' | 'file', expanded: boolean) {
  if (type === 'folder')
    return expanded ? <FolderOpen className="h-[15px] w-[15px] text-[#dcb67a]" /> : <Folder className="h-[15px] w-[15px] text-[#dcb67a]" />
  const ext = (name.split('.').pop() || '').toLowerCase()
  if (['js', 'mjs', 'ts', 'tsx'].includes(ext)) return <FileCode className="h-[15px] w-[15px] text-[var(--explorer-muted,#7c7c7c)]" />
  if (['css', 'scss'].includes(ext)) return <FileCode2 className="h-[15px] w-[15px] text-[var(--explorer-muted,#7c7c7c)]" />
  if (['png', 'jpg', 'jpeg', 'svg', 'gif', 'webp'].includes(ext)) return <FileImage className="h-[15px] w-[15px] text-[var(--explorer-muted,#7c7c7c)]" />
  if (ext === 'md') return <FileText className="h-[15px] w-[15px] text-[var(--explorer-muted,#7c7c7c)]" />
  return <FileIcon className="h-[15px] w-[15px] text-[var(--explorer-muted,#7c7c7c)]" />
}

function findNode(root: TreeNode, path: string): TreeNode | null {
  if (root.path === path && path !== '') return root
  for (const child of root.children) {
    const found = findNode(child, path)
    if (found) return found
  }
  return null
}

function uniqueName(folder: TreeNode, name: string) {
  const names = folder.children.map(c => c.name)
  if (!names.includes(name)) return name
  const dot = name.lastIndexOf('.')
  const base = dot > 0 ? name.slice(0, dot) : name
  const ext = dot > 0 ? name.slice(dot) : ''
  let i = 2
  while (names.includes(`${base} ${i}${ext}`)) i += 1
  return `${base} ${i}${ext}`
}

function SideExplorer({
  client,
  workspaceId,
  refs,
  onAddRef,
  onRemoveRef: _onRemoveRef,
}: {
  client: CloudClient
  workspaceId: string
  refs: Array<{ id: string; path: string }>
  onAddRef: (path: string) => void
  onRemoveRef: (id: string) => void
}) {
  const { t } = useCloudLocale()
  const [tree, setTree] = useState<TreeNode>(() => buildTree([]))
  const [query, setQuery] = useState('')
  const [activeFile, setActiveFile] = useState('')
  const [menu, setMenu] = useState<{ x: number; y: number; items: MenuItemDef[] } | null>(null)

  const load = useCallback(async () => {
    try {
      const value = (await client.listWorkspaceFiles(workspaceId, '', 500)) as {
        files?: Array<{ path: string; bytes?: number }>
      }
      setTree(buildTree(value.files ?? []))
    } catch {
      setTree(buildTree([]))
    }
  }, [client, workspaceId])

  useEffect(() => {
    void load()
  }, [load])

  // 单一外部 mousedown 监听：点在菜单/触发按钮之外才关闭；点菜单内部不关，
  // 交给菜单项自己的 click 处理，避免“一点就关、动作没触发”。
  useEffect(() => {
    if (!menu) return
    const onDown = (event: MouseEvent) => {
      const target = event.target as HTMLElement
      // 点菜单本身或其触发按钮都不在此关闭（触发按钮的 click 负责切换）。
      if (target.closest('.ctx-menu') || target.closest('[data-menu-trigger]')) return
      setMenu(null)
    }
    const onResize = () => setMenu(null)
    const onEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenu(null)
    }
    document.addEventListener('mousedown', onDown)
    window.addEventListener('resize', onResize)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onDown)
      window.removeEventListener('resize', onResize)
      document.removeEventListener('keydown', onEsc)
    }
  }, [menu])

  // 文件操作：写/删后重新拉取并重建树。
  async function createFile(folder: TreeNode) {
    const name = window.prompt(t('explorer.new-file', '新建文件'), '新建文件.txt')
    const trimmed = name?.trim()
    if (!trimmed) return
    const finalName = uniqueName(folder, trimmed)
    const path = folder.path ? `${folder.path}/${finalName}` : finalName
    await client.writeWorkspaceFile(workspaceId, path, '')
    await load()
  }

  function createFolder(folder: TreeNode) {
    // 文件夹本身不落盘（空目录无法存储），只在本地树结构中体现，直到放入文件。
    const name = window.prompt(t('explorer.new-folder', '新建文件夹'), '新建文件夹')
    const trimmed = name?.trim()
    if (!trimmed) return
    const finalName = uniqueName(folder, trimmed)
    folder.children.push({
      name: finalName,
      path: folder.path ? `${folder.path}/${finalName}` : finalName,
      type: 'folder',
      expanded: true,
      children: [],
    })
    folder.expanded = true
    setTree(current => structuredClone(current))
  }

  async function rename(node: TreeNode) {
    const name = window.prompt(t('explorer.rename', '重命名'), node.name)
    const trimmed = name?.trim()
    if (!trimmed || trimmed === node.name) return
    const parentPath = node.path.split('/').slice(0, -1).join('/')
    const targetPath = parentPath ? `${parentPath}/${trimmed}` : trimmed
    if (node.type === 'file') {
      try {
        const value = (await client.readWorkspaceFile(workspaceId, node.path)) as {
          content?: string
        }
        await client.writeWorkspaceFile(workspaceId, targetPath, value.content ?? '')
        await client.deleteWorkspaceFile(workspaceId, node.path)
      } catch {
        return
      }
      await load()
    } else {
      node.name = trimmed
      node.path = targetPath
      setTree(current => structuredClone(current))
    }
  }

  async function remove(node: TreeNode) {
    if (!window.confirm(t('explorer.delete-confirm', `确定删除 “${node.name}” 吗？`))) return
    if (node.type === 'file') {
      await client.deleteWorkspaceFile(workspaceId, node.path)
      await load()
    } else {
      setTree(current => {
        const clone = structuredClone(current)
        const target = findNode(clone, node.path)
        const parent = findNodeParent(clone, node.path)
        if (target && parent) parent.children = parent.children.filter(c => c.path !== node.path)
        return clone
      })
    }
  }

  function openNodeMenu(event: React.MouseEvent, node: TreeNode) {
    event.preventDefault()
    const common: MenuItemDef[] = [
      { icon: Pencil, label: t('explorer.ctx-rename', '重命名'), action: () => void rename(node) },
      { icon: CornerUpLeft, label: t('explorer.ctx-add-chat', '添加到聊天'), action: () => onAddRef(node.path) },
      { divider: true },
      { icon: Trash2, label: t('explorer.ctx-delete', '删除'), action: () => void remove(node) },
    ]
    const folderExtra: MenuItemDef[] = node.path
      ? [
          { icon: FilePlus, label: t('explorer.ctx-new-file', '新建文件'), action: () => void createFile(node) },
          { icon: FolderPlus, label: t('explorer.ctx-new-folder', '新建文件夹'), action: () => createFolder(node) },
          { divider: true },
        ]
      : []
    setMenu({
      x: event.clientX,
      y: event.clientY,
      items: node.type === 'folder' ? [...folderExtra, ...common] : common,
    })
  }

  const searchResults = query.trim()
    ? collectFiles(tree).filter(file => file.name.toLowerCase().includes(query.trim().toLowerCase()))
    : null

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--explorer-bg,#f3f3f3)] text-[var(--explorer-text,#333)]">
      <header className="flex flex-none items-center justify-between px-2.5 pb-1.5 pt-2.5">
        <strong className="text-[11px] font-bold tracking-wide">
          {t('explorer.title', '资源管理器')}
        </strong>
        <button
          type="button"
          data-menu-trigger
          title={t('explorer.more', '更多操作')}
          aria-label={t('explorer.more', '更多操作')}
          onClick={event => {
            const r = event.currentTarget.getBoundingClientRect()
            setMenu({
              x: r.left,
              y: r.bottom + 6,
              items: [
                { icon: FilePlus, label: t('explorer.ctx-new-file', '新建文件'), action: () => void createFile(tree) },
                { icon: FolderPlus, label: t('explorer.ctx-new-folder', '新建文件夹'), action: () => createFolder(tree) },
                { divider: true },
                { icon: RefreshCw, label: t('explorer.refresh', '刷新'), action: () => void load() },
                {
                  icon: MoreHorizontal,
                  label: t('explorer.collapse', '折叠'),
                  action: () => {
                    tree.children.forEach(c => {
                      if (c.type === 'folder') c.expanded = false
                    })
                    setTree(current => structuredClone(current))
                  },
                },
              ],
            })
          }}
          className="grid h-[22px] w-6 place-items-center rounded text-[var(--explorer-muted,#7c7c7c)] hover:bg-[var(--explorer-hover,#e8e8e8)] hover:text-[var(--explorer-text,#333)]"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </header>
      <div className="mx-2 mb-2 flex flex-none items-center gap-1.5 rounded border border-[var(--explorer-border,#e2e2e2)] bg-white px-2 py-1">
        <Search className="h-3.5 w-3.5 flex-none text-[var(--explorer-muted,#7c7c7c)]" />
        <input
          type="search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder={t('explorer.search', '搜索文件')}
          aria-label={t('explorer.search', '搜索文件')}
          className="min-w-0 flex-1 border-0 bg-transparent text-[12px] outline-none"
        />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {searchResults ? (
          searchResults.length ? (
            searchResults.map(file => (
              <button
                key={file.path}
                type="button"
                onClick={() => setActiveFile(file.path)}
                onContextMenu={event => openNodeMenu(event, file)}
                className={`flex h-6 w-full items-center gap-1.5 px-2 text-left text-[13px] hover:bg-[var(--explorer-hover,#e8e8e8)] ${activeFile === file.path ? 'bg-[var(--explorer-active,#e4e4f4)]' : ''}`}
              >
                {iconForNode(file.name, 'file', false)}
                <span className="truncate">{file.name}</span>
              </button>
            ))
          ) : (
            <p className="p-3 text-[12px] text-[var(--explorer-muted,#7c7c7c)]">
              {t('explorer.no-match', '未找到匹配文件')}
            </p>
          )
        ) : (
          <ExplorerNode
            node={tree}
            depth={0}
            activeFile={activeFile}
            onToggleFolder={node => {
              node.expanded = !node.expanded
              setTree(current => structuredClone(current))
            }}
            onSelectFile={node => setActiveFile(node.path)}
            onContextMenu={openNodeMenu}
          />
        )}
      </div>
      {refs.length ? (
        <div className="flex-none border-t border-[var(--explorer-border,#e2e2e2)] p-2 text-[11px] text-[var(--explorer-muted,#7c7c7c)]">
          {refs.length} {t('explorer.refs', '个引用已加入聊天')}
        </div>
      ) : null}
      {menu
        ? createPortal(
            <CtxMenu menu={menu} onClose={() => setMenu(null)} />,
            document.body
          )
        : null}
    </div>
  )
}

type MenuItemDef =
  | { icon?: typeof Pencil; label: string; action: () => void; divider?: undefined }
  | { divider: true; icon?: undefined; label?: undefined; action?: undefined }

function CtxMenu({ menu, onClose }: { menu: { x: number; y: number; items: MenuItemDef[] }; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ left: menu.x, top: menu.y })
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const w = el.offsetWidth
    const h = el.offsetHeight
    setPos({
      left: Math.min(menu.x, window.innerWidth - w - 8),
      top: Math.min(menu.y, window.innerHeight - h - 8),
    })
  }, [menu.x, menu.y])
  return (
    <div
      ref={ref}
      className="ctx-menu fixed z-[1100] min-w-[170px] rounded-lg border border-[var(--border-subtle)] bg-[var(--surface)] p-1.5 text-[var(--on-surface)] shadow-[0_8px_24px_rgba(0,0,0,0.12)]"
      style={pos}
    >
      {menu.items.map((item, index) =>
        item.divider ? (
          <hr key={index} className="mx-1.5 my-1 border-0 border-t border-[var(--border-subtle)]" />
        ) : (
          <button
            key={index}
            type="button"
            onClick={() => {
              onClose()
              item.action()
            }}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] hover:bg-[var(--primary-light)] hover:text-[var(--primary)]"
          >
            {item.icon ? <item.icon className="h-[15px] w-[15px] flex-none" /> : null}
            {item.label}
          </button>
        )
      )}
    </div>
  )
}

function ExplorerNode({
  node,
  depth,
  activeFile,
  onToggleFolder,
  onSelectFile,
  onContextMenu,
}: {
  node: TreeNode
  depth: number
  activeFile: string
  onToggleFolder: (node: TreeNode) => void
  onSelectFile: (node: TreeNode) => void
  onContextMenu: (event: React.MouseEvent, node: TreeNode) => void
}) {
  if (node.path === '') {
    return (
      <>
        {node.children.map(child => (
          <ExplorerNode
            key={child.path}
            node={child}
            depth={0}
            activeFile={activeFile}
            onToggleFolder={onToggleFolder}
            onSelectFile={onSelectFile}
            onContextMenu={onContextMenu}
          />
        ))}
      </>
    )
  }
  return (
    <div>
      <button
        type="button"
        onClick={() => (node.type === 'folder' ? onToggleFolder(node) : onSelectFile(node))}
        onContextMenu={event => onContextMenu(event, node)}
        style={{ paddingLeft: depth * 12 + 8 }}
        className={`flex h-6 w-full items-center gap-1.5 text-left text-[13px] hover:bg-[var(--explorer-hover,#e8e8e8)] ${activeFile === node.path ? 'bg-[var(--explorer-active,#e4e4f4)]' : ''}`}
      >
        {node.type === 'folder' ? (
          node.expanded ? (
            <ChevronDown className="h-[13px] w-[13px] flex-none text-[var(--explorer-text,#333)]" />
          ) : (
            <ChevronRight className="h-[13px] w-[13px] flex-none text-[var(--explorer-text,#333)]" />
          )
        ) : (
          <span className="w-[13px] flex-none" />
        )}
        {iconForNode(node.name, node.type, node.expanded)}
        <span className="truncate font-normal">{node.name}</span>
      </button>
      {node.type === 'folder' && node.expanded
        ? node.children.map(child => (
            <ExplorerNode
              key={child.path}
              node={child}
              depth={depth + 1}
              activeFile={activeFile}
              onToggleFolder={onToggleFolder}
              onSelectFile={onSelectFile}
              onContextMenu={onContextMenu}
            />
          ))
        : null}
    </div>
  )
}

function collectFiles(node: TreeNode, out: TreeNode[] = []): TreeNode[] {
  if (node.path !== '' && node.type === 'file') out.push(node)
  node.children.forEach(child => collectFiles(child, out))
  return out
}

function findNodeParent(node: TreeNode, path: string): TreeNode | null {
  for (const child of node.children) {
    if (child.path === path) return node
    const found = findNodeParent(child, path)
    if (found) return found
  }
  return null
}

/* ---------------- Bottom Terminal ---------------- */

function BottomTerminal({ client, sessionId }: { client: CloudClient; sessionId: string }) {
  const { t } = useCloudLocale()
  const [tabs, setTabs] = useState<number[]>([1])
  const [active, setActive] = useState(1)
  const [nextId, setNextId] = useState(2)
  const session = sessionId

  function addTab() {
    const id = nextId
    setNextId(value => value + 1)
    setTabs(current => [...current, id])
    setActive(id)
  }
  function closeTab(id: number) {
    if (tabs.length <= 1) return
    const index = tabs.findIndex(value => value === id)
    const remaining = tabs.filter(value => value !== id)
    setTabs(remaining)
    if (active === id) setActive(remaining[Math.max(0, index - 1)])
  }

  return (
    <div className="flex h-full flex-col border-t border-[var(--term-border,#e2e2e2)] bg-[var(--term-bg,#ffffff)]">
      <header className="flex h-[35px] flex-none items-stretch border-b border-[var(--term-border,#e2e2e2)] bg-[var(--term-tab-bg,#ececec)] text-[var(--term-muted,#8c8c8c)]">
        {tabs.map(id => (
          <div
            key={id}
            onClick={() => setActive(id)}
            className={`flex cursor-pointer items-center gap-1.5 border-r border-[var(--term-border,#e2e2e2)] px-2.5 text-[12px] font-semibold ${active === id ? 'bg-[var(--term-tab-active,#fff)] text-[var(--term-text,#333)]' : ''}`}
          >
            <Terminal className="h-3.5 w-3.5 text-[#d7ba7d]" />
            <span>{id === 1 ? 'ssh' : `ssh ${id}`}</span>
            <button
              type="button"
              title={t('terminal.close', '关闭终端标签')}
              aria-label={t('terminal.close', '关闭终端标签')}
              onClick={event => {
                event.stopPropagation()
                closeTab(id)
              }}
              className="grid h-[18px] w-[18px] place-items-center rounded hover:bg-[#d5d5d5] hover:text-[var(--term-text,#333)]"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
        <button
          type="button"
          title={t('terminal.new', '新建终端')}
          aria-label={t('terminal.new', '新建终端')}
          onClick={addTab}
          className="grid w-[34px] place-items-center hover:text-[var(--term-text,#333)]"
        >
          <Plus className="h-[15px] w-[15px]" />
        </button>
      </header>
      <TerminalBody key={active} client={client} sessionId={session} />
    </div>
  )
}

type TerminalLine = {
  command: string
  output?: string
  error?: string
  cwd?: string
}

function TerminalBody({
  client,
  sessionId,
}: {
  client: CloudClient
  sessionId: string
}) {
  const { t } = useCloudLocale()
  const [lines, setLines] = useState<TerminalLine[]>([])
  const [value, setValue] = useState('')
  const [cwd, setCwd] = useState('.')
  const [busy, setBusy] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight })
  }, [lines.length, busy])

  async function run(event: React.FormEvent) {
    event.preventDefault()
    const command = value.trim()
    if (!command || busy) return
    setValue('')
    setBusy(true)
    setLines(current => [...current, { command }])
    try {
      const result = await client.runTerminal(sessionId, command, cwd === '.' ? null : cwd)
      setLines(current =>
        current.map((line, index) =>
          index === current.length - 1
            ? {
                ...line,
                output: result.stdout,
                error: result.stderr,
                cwd: result.cwd,
              }
            : line
        )
      )
      setCwd(result.cwd)
    } catch (reason) {
      setLines(current =>
        current.map((line, index) =>
          index === current.length - 1
            ? {
                ...line,
                error:
                  reason instanceof Error
                    ? reason.message
                    : t('terminal.failed', '命令执行失败'),
              }
            : line
        )
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      ref={bodyRef}
      className="min-h-0 flex-1 overflow-auto bg-[var(--term-bg,#fff)] px-4 py-2.5 text-left font-mono text-[13px] leading-[1.55]"
    >
      <div className="mb-2 text-[11px] text-[var(--term-muted,#8c8c8c)]">
        {t('terminal.root', '工作根目录（仅可访问此目录）')}: {cwd}
      </div>
      {lines.map((line, index) => (
        <div key={index} className="mb-1.5">
          <div className="whitespace-pre-wrap break-all">
            <span className="font-semibold text-[var(--term-green,#388a34)]">hehejie@cloud</span>
            <span className="text-[var(--term-text,#333)]">:</span>
            <span className="text-[var(--term-blue,#098658)]">{line.cwd ?? cwd}</span>
            <span className="text-[var(--term-text,#333)]">$ </span>
            {line.command}
          </div>
          {line.output ? (
            <pre className="whitespace-pre-wrap break-all text-[var(--term-text,#333)]">{line.output}</pre>
          ) : null}
          {line.error ? (
            <pre className="whitespace-pre-wrap break-all text-[var(--error)]">{line.error}</pre>
          ) : null}
        </div>
      ))}
      {busy ? (
        <div className="flex items-center gap-2 text-[var(--term-muted,#8c8c8c)]">
          <ThinkingDots />
          <span>{t('terminal.running', '执行中')}</span>
        </div>
      ) : null}
      <form onSubmit={run} className="flex items-center">
        <span className="font-semibold text-[var(--term-green,#388a34)]">hehejie@cloud</span>
        <span className="text-[var(--term-text,#333)]">:</span>
        <span className="text-[var(--term-blue,#098658)]">{cwd}</span>
        <span className="text-[var(--term-text,#333)]">$&nbsp;</span>
        <input
          value={value}
          onChange={event => setValue(event.target.value)}
          aria-label="terminal input"
          autoFocus
          className="min-w-0 flex-1 border-0 bg-transparent font-mono text-[13px] text-[var(--term-text,#333)] outline-none"
        />
      </form>
    </div>
  )
}

function CloudApprovalBar({ client, sessionId }: { client: CloudClient; sessionId: string }) {
  const [pendingCount, setPendingCount] = useState<number | null>(null)
  const [open, setOpen] = useState(false)
  const { t } = useCloudLocale()
  async function check() {
    try {
      const items = (await client.listApprovals(sessionId)) as Array<{ status: string }>
      setPendingCount(items.filter(item => item.status === 'pending').length)
    } catch {
      setPendingCount(0)
    }
  }
  useEffect(() => {
    void check()
    const timer = window.setInterval(check, 5000)
    return () => window.clearInterval(timer)
  }, [sessionId])
  if (!pendingCount) return null
  return (
    <div className="mb-2 overflow-hidden rounded-lg border border-amber-300 bg-amber-500/10">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-amber-700"
        onClick={() => setOpen(value => !value)}
      >
        <span aria-hidden="true">{open ? '▼' : '▶'}</span>
        {t('sessions.pending-approvals', '待处理审批')}（{pendingCount}）
      </button>
      {open ? <CloudApprovalList client={client} sessionId={sessionId} /> : null}
    </div>
  )
}

// 新建会话视图：无历史，仅保留输入框。
function NewCloudSessionView({
  client,
  onCreated,
  model,
}: {
  client: CloudClient
  onCreated?: (session: CloudSessionLike) => void
  model: string
}) {
  const { t } = useCloudLocale()
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function send(event: React.FormEvent) {
    event.preventDefault()
    const text = input.trim()
    if (!text || !model || sending) return
    setSending(true)
    setError(null)
    try {
      const session = await client.createSession('cloud_native', text.slice(0, 40), 'default', model)
      await client.sendCommand(session.id, crypto.randomUUID(), text, { model_id: model })
      onCreated?.(session)
    } catch (reason) {
      setError(localizeCloudError(reason instanceof Error ? reason.message : 'create failed', t))
    } finally {
      setSending(false)
    }
  }
  return (
    <section className="flex h-full min-h-0 flex-col">
      <header className="h-11 border-b border-[var(--border-subtle)]" />
      <div className="min-h-0 flex-1" />
      <form onSubmit={send} className="border-t border-[var(--border-subtle)] px-4 py-3">
        {error ? <p role="alert" className="mb-2 text-xs text-[var(--error)]">{error}</p> : null}
        <div className="flex items-end gap-2">
          <textarea
            autoFocus
            value={input}
            onChange={event => setInput(event.target.value)}
            rows={2}
            maxLength={4000}
            placeholder={t('session.placeholder', '继续告诉 Agent 你要完成什么…')}
            className="max-h-40 min-h-[3rem] flex-1 resize-none rounded-xl border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
          />
          <button
            type="submit"
            disabled={sending || !input.trim() || !model}
            className="grid h-10 w-10 place-items-center rounded-full bg-[var(--primary)] text-white disabled:opacity-40"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-2 text-right text-xs text-[var(--on-surface-variant)]">{input.length} / 4000</p>
      </form>
    </section>
  )
}
