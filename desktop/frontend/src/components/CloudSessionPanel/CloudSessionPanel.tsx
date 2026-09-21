import { useEffect, useRef, useState } from 'react'
import {
  ArrowUp,
  FileText,
  Globe,
  MessagesSquare,
  PanelBottom,
  PanelRight,
  Paperclip,
  TerminalSquare,
} from 'lucide-react'
import CloudClient, {
  type CloudAttachment,
} from '../../services/cloud'
import { useCloudSession } from '../../hooks/useCloudSession'
import { localizeCloudError, useCloudLocale } from '../../pages/CloudPage/cloudLocale'
import { CloudApprovalList } from '../CloudApprovalList'

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
    output?: string
    status?: string
    error?: { message?: string }
  }
  created_at: number
}

export function CloudSessionPanel({
  client,
  sessionId,
  onSessionCreated,
}: CloudSessionPanelProps) {
  const { t } = useCloudLocale()
  const { session, events, controller } = useCloudSession(client, sessionId)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [model, setModel] = useState(session?.model_id || '')
  const [bottomOpen, setBottomOpen] = useState(false)
  const [sideOpen, setSideOpen] = useState(false)
  const [attachment, setAttachment] = useState('')
  const [attachmentPayload, setAttachmentPayload] = useState<CloudAttachment | null>(null)
  const [historyCommands, setHistoryCommands] = useState<HistoryCommand[]>([])
  const threadRef = useRef<HTMLDivElement>(null)
  const pollTimers = useRef<number[]>([])

  // 读取该会话的用户命令（消息），与 turn 事件按顺序配对。
  useEffect(() => {
    if (!sessionId) return
    let active = true
    void client
      .listCommands(sessionId, 0, 500)
      .then(value => {
        if (active) setHistoryCommands(value as HistoryCommand[])
      })
      .catch(() => undefined)
    return () => {
      active = false
    }
  }, [client, sessionId, events.length])

  useEffect(() => {
    let active = true
    void client
      .listModels()
      .then(value => {
        if (!active || session?.model_id) return
        setModel(value.find(item => item.is_default && item.enabled)?.id ?? '')
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
  }, [events.length])

  // 从事件流中提取对话对：用户消息取自 commands，AI 回复取自 turn 事件，按顺序一一对应。
  const turns: Array<{ user?: string; assistant?: string; error?: string }> = []
  const turnEvents = (events as ThreadEvent[]).filter(event =>
    event.event_type.startsWith('turn.')
  )
  turnEvents.forEach((event, index) => {
    const entry: typeof turns[number] = { user: historyCommands[index]?.input_text }
    if (event.event_type === 'turn.failed') {
      entry.error = event.payload?.error?.message ?? t('session.failed', '执行失败')
    } else {
      entry.assistant = event.payload?.output
    }
    turns.push(entry)
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
    setAttachment(file.name || t('session.attachment-name', '剪贴板截图'))
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
    try {
      const result = (await controller.send(text, crypto.randomUUID(), {
        attachments: attachmentPayload ? [attachmentPayload] : [],
        model_id: model,
      })) as { command_id?: string; status?: string }
      setInput('')
      setAttachment('')
      setAttachmentPayload(null)
      await controller.refreshEvents()
      if (result.command_id) {
        const commandId = result.command_id
        const poll = window.setInterval(() => {
          void client
            .commandStatus(sessionId, commandId)
            .then(async value => {
              const status = String(value.status ?? 'queued')
              if (!['queued', 'running'].includes(status)) {
                window.clearInterval(poll)
                await controller.refreshEvents()
              }
            })
            .catch(() => window.clearInterval(poll))
        }, 1500)
        pollTimers.current.push(poll)
        window.setTimeout(() => window.clearInterval(poll), 60000)
      }
    } catch (reason) {
      setSendError(localizeCloudError(reason instanceof Error ? reason.message : 'send failed', t))
    } finally {
      setSending(false)
    }
  }

  return (
    <section className="flex h-full min-h-0 flex-col">
      {/* 顶部：左侧为空，右侧展示底部面板与侧边面板两个图标按钮 */}
      <header className="flex items-center justify-end gap-1 border-b border-[var(--border-subtle)] px-3 py-2">
        <button
          type="button"
          title={t('session.bottom-panel', '底部命令行')}
          aria-label={t('session.bottom-panel', '底部命令行')}
          onClick={() => setBottomOpen(value => !value)}
          className="grid h-8 w-8 place-items-center rounded text-[var(--on-surface-variant)] hover:bg-[var(--surface-container)]"
        >
          <PanelBottom className="h-4 w-4" />
        </button>
        <button
          type="button"
          title={t('session.side-panel', '侧边菜单')}
          aria-label={t('session.side-panel', '侧边菜单')}
          onClick={() => setSideOpen(value => !value)}
          className="grid h-8 w-8 place-items-center rounded text-[var(--on-surface-variant)] hover:bg-[var(--surface-container)]"
        >
          <PanelRight className="h-4 w-4" />
        </button>
      </header>

      {/* 对话内容区：用户消息靠右，AI 回复靠左 */}
      <div ref={threadRef} className="min-h-0 flex-1 overflow-auto px-4 py-4">
        {!turns.length ? (
          <p className="grid h-full place-items-center text-sm text-[var(--on-surface-variant)]">
            {t('session.start-hint', '发送一条消息开始对话。')}
          </p>
        ) : (
          <div className="mx-auto max-w-3xl space-y-5">
            {turns.map((turn, index) => (
              <div key={index} className="space-y-3">
                <div className="flex justify-end">
                  <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-[var(--primary)] px-4 py-2.5 text-sm text-white">
                    {turn.user}
                  </div>
                </div>
                <div className="flex justify-start">
                  <div className="max-w-[80%] rounded-2xl rounded-bl-sm border border-[var(--border-subtle)] bg-[var(--surface-container)] px-4 py-2.5 text-sm">
                    {turn.error ? (
                      <span className="text-[var(--error)]">{turn.error}</span>
                    ) : (
                      turn.assistant
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 输入框：顶部展示待处理审批，无审批时不占位 */}
      <form onSubmit={submit} className="border-t border-[var(--border-subtle)] px-4 pt-2 pb-3">
        <CloudApprovalBar client={client} sessionId={sessionId} />
        {sendError ? (
          <p role="alert" className="mb-2 text-xs text-[var(--error)]">{sendError}</p>
        ) : null}
        {attachment ? (
          <p className="mb-2 text-xs text-[var(--on-surface-variant)]">
            <Paperclip className="mr-1 inline h-3 w-3" />{attachment}
          </p>
        ) : null}
        <div className="flex items-end gap-2">
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
            className="max-h-40 min-h-[2.5rem] flex-1 resize-none rounded-xl border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
          />
          <button
            type="submit"
            aria-label={t('session.send', '发送')}
            disabled={sending || !input.trim() || !model}
            className="grid h-10 w-10 place-items-center rounded-full bg-[var(--primary)] text-white disabled:opacity-40"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs text-[var(--on-surface-variant)]">
          <label className="flex cursor-pointer items-center gap-1 rounded border border-[var(--border-subtle)] px-2 py-1 hover:bg-[var(--surface-container)]">
            <Paperclip className="h-3 w-3" />
            {t('session.add-file', '添加文件')}
            <input
              type="file"
              className="sr-only"
              onChange={event => {
                const file = event.target.files?.[0]
                if (file) void loadAttachment(file)
              }}
            />
          </label>
          <span className="ml-auto">{input.length} / 4000</span>
        </div>
      </form>

      {bottomOpen ? <BottomConsole onClose={() => setBottomOpen(false)} /> : null}
      {sideOpen ? (
        <SideDrawer onClose={() => setSideOpen(false)} client={client} sessionId={sessionId} />
      ) : null}
    </section>
  )
}

// 审批条：嵌入输入框顶部；无待审批时返回 null，不展示空区块。
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

// 底部命令行面板。
function BottomConsole({ onClose }: { onClose: () => void }) {
  const { t } = useCloudLocale()
  return (
    <div className="absolute right-0 bottom-0 left-0 z-30 h-56 border-t border-[var(--border-subtle)] bg-[var(--surface-container-lowest)] shadow-[0_-8px_24px_rgba(0,0,0,0.08)]">
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-2 text-xs font-medium">
        {t('session.console', '命令行')}
        <button type="button" onClick={onClose} aria-label={t('cancel', '关闭')}>×</button>
      </div>
      <div className="h-[calc(100%-2.25rem)] p-3 font-mono text-xs text-[var(--on-surface-variant)]">
        {t('session.console-empty', '命令执行日志将显示在这里。')}
      </div>
    </div>
  )
}

// 侧边菜单抽屉：文件、浏览器、侧边对话、终端。
function SideDrawer({
  onClose,
  client: _client,
  sessionId: _sessionId,
}: {
  onClose: () => void
  client: CloudClient
  sessionId: string
}) {
  const { t } = useCloudLocale()
  const [active, setActive] = useState<'files' | 'browser' | 'chat' | 'terminal'>('files')
  const items = [
    { id: 'files' as const, icon: FileText, label: t('side.files', '文件') },
    { id: 'browser' as const, icon: Globe, label: t('side.browser', '浏览器') },
    { id: 'chat' as const, icon: MessagesSquare, label: t('side.chat', '侧边对话') },
    { id: 'terminal' as const, icon: TerminalSquare, label: t('side.terminal', '终端') },
  ]
  return (
    <div className="absolute top-0 right-0 bottom-0 z-30 flex w-80 border-l border-[var(--border-subtle)] bg-[var(--surface-container-lowest)] shadow-lg">
      <nav className="flex w-16 flex-col items-center gap-1 border-r border-[var(--border-subtle)] py-3">
        {items.map(item => {
          const Icon = item.icon
          return (
            <button
              key={item.id}
              type="button"
              title={item.label}
              onClick={() => setActive(item.id)}
              className={`grid h-11 w-11 place-items-center rounded-lg ${active === item.id ? 'bg-[var(--primary-light)] text-[var(--primary)]' : 'text-[var(--on-surface-variant)] hover:bg-[var(--surface-container)]'}`}
            >
              <Icon className="h-4 w-4" />
            </button>
          )
        })}
      </nav>
      <div className="min-w-0 flex-1 overflow-auto p-3 text-xs text-[var(--on-surface-variant)]">
        <div className="mb-2 flex items-center justify-between">
          <strong className="text-[var(--on-surface)]">{items.find(i => i.id === active)?.label}</strong>
          <button type="button" onClick={onClose} aria-label={t('cancel', '关闭')}>×</button>
        </div>
        {t('side.coming-soon', '该面板内容接入后显示。')}
      </div>
    </div>
  )
}

// 新建会话视图：顶部为空，下方无对话内容，仅保留输入框。
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
