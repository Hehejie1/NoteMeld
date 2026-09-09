import { useEffect, useRef, useState } from 'react'
import CloudClient, { type CloudModel, type CloudSession } from '../../services/cloud'
import { useCloudSession } from '../../hooks/useCloudSession'

export interface CloudSessionPanelProps {
  client: CloudClient
  sessionId?: string
  onCopy?: (sessionId: string) => void
  onArchived?: () => void
  onSessionCreated?: (session: CloudSession) => void
}

export function CloudSessionPanel({ client, sessionId, onCopy, onArchived, onSessionCreated }: CloudSessionPanelProps) {
  const { session, events, loading, error, controller } = useCloudSession(client, sessionId)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [commandState, setCommandState] = useState<string | null>(null)
  const [model, setModel] = useState(session?.model_id || 'auto')
  const [fullAccess, setFullAccess] = useState(false)
  const [permissionOpen, setPermissionOpen] = useState(false)
  const [modelOpen, setModelOpen] = useState(false)
  const [attachment, setAttachment] = useState('')
  const mounted = useRef(true)
  const pollTimers = useRef<number[]>([])
  useEffect(() => () => { mounted.current = false; pollTimers.current.forEach(timer => window.clearInterval(timer)) }, [])

  if (!sessionId) return <NewCloudSessionComposer client={client} onCreated={onSessionCreated} />
  if (loading && !session) return <section aria-busy="true" aria-label="Loading cloud session" className="space-y-3 p-4"><div className="h-5 w-48 animate-pulse rounded bg-slate-200" /><div className="h-24 animate-pulse rounded bg-slate-100" /></section>
  if (error && !session) return <section role="alert" className="p-4 text-sm text-red-700">Unable to load this session: {error.message}</section>
  if (!session) return <section role="status" className="p-4 text-sm text-slate-500">This session is unavailable.</section>

  const status = session.status || 'idle'
  const statusTone = status === 'running' ? 'bg-blue-50 text-blue-700' : status === 'failed' ? 'bg-red-50 text-red-700' : status === 'waiting_approval' ? 'bg-amber-50 text-amber-700' : status === 'paused_offline' || status === 'needs_attention' ? 'bg-orange-50 text-orange-700' : 'bg-emerald-50 text-emerald-700'

  return <section aria-labelledby="cloud-session-title" className="flex min-h-0 flex-col gap-4 p-4 pb-36 md:p-6 md:pb-36">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 id="cloud-session-title" className="text-lg font-semibold text-slate-900">{session.title || 'Cloud session'}</h2>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500"><span>{session.kind === 'cloud_native' ? 'Cloud Agent' : 'Remote device'}</span><span aria-hidden="true">·</span><span className={`rounded-full px-2 py-0.5 font-medium ${statusTone}`}>{status.replaceAll('_', ' ')}</span></div>
      </div>
      <div className="flex gap-2">
        <button type="button" className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50" onClick={() => void controller.refreshEvents()}>Refresh</button>
        <button type="button" disabled={actionBusy} className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50" onClick={async () => { setActionBusy(true); setActionError(null); try { const copy = await controller.copy(); onCopy?.(copy.id) } catch (reason) { setActionError(reason instanceof Error ? reason.message : 'Unable to copy branch') } finally { setActionBusy(false) } }}>Copy branch</button>
        <button type="button" disabled={actionBusy} className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50" onClick={async () => { setActionBusy(true); setActionError(null); try { await controller.archive(); onArchived?.() } catch (reason) { setActionError(reason instanceof Error ? reason.message : 'Unable to archive session') } finally { setActionBusy(false) } }}>Archive</button>
      </div>
    </header>
    <div role="log" aria-live="polite" className="min-h-24 flex-1 overflow-auto rounded border border-slate-200 bg-white p-3">
      {events.length === 0 ? <div className="flex h-full min-h-24 items-center justify-center text-sm text-slate-500">No events yet. Send a message to start the Agent.</div> : <ol className="space-y-3">{events.map((rawEvent, index) => { const event = rawEvent as { sequence?: number; event_type?: string; payload?: unknown }; return <li key={`${event.sequence ?? 'event'}-${index}`} className="border-b border-slate-100 pb-3 text-sm last:border-b-0"><div className="flex items-center justify-between gap-2"><span className="font-medium text-slate-800">{String(event.event_type || 'event').replaceAll('_', ' ')}</span><span className="font-mono text-[11px] text-slate-400">#{event.sequence ?? index + 1}</span></div>{event.payload !== undefined ? <pre className="mt-1 max-h-28 overflow-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2 text-xs text-slate-600">{formatPayload(event.payload)}</pre> : null}</li> })}</ol>}
    </div>
    <form onSubmit={async event => { event.preventDefault(); if (!input.trim() || sending) return; setSending(true); setSendError(null); setCommandState('queued'); try { const commandInput = `${attachment ? `[附件：${attachment}] ` : ''}${fullAccess ? '[完全授权] ' : ''}${input.trim()}`; const result = await controller.send(commandInput, crypto.randomUUID()) as { command_id?: string; status?: string }; if (!mounted.current) return; setInput(''); setAttachment(''); setCommandState(result.status ?? 'queued'); await controller.refreshEvents(); if (result.command_id && (result.status === 'queued' || result.status === 'running')) { const commandId = result.command_id; const poll = window.setInterval(() => { if (!mounted.current) { window.clearInterval(poll); return } void client.commandStatus(session.id, commandId).then(value => { if (!mounted.current) return; const status = String(value.status ?? 'queued'); setCommandState(status); if (!['queued', 'running'].includes(status)) window.clearInterval(poll) }).catch(() => window.clearInterval(poll)) }, 1500); pollTimers.current.push(poll); window.setTimeout(() => window.clearInterval(poll), 30000) } } catch (reason) { if (mounted.current) { setSendError(reason instanceof Error ? reason.message : 'Unable to send message'); setCommandState(null) } } finally { if (mounted.current) setSending(false) } }} className="fixed bottom-4 left-4 right-4 z-20 space-y-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-container-lowest)] p-3 shadow-lg md:left-[calc(17rem+1rem)]"><div className="flex gap-2"><label htmlFor="cloud-session-input" className="sr-only">Message</label><textarea id="cloud-session-input" value={input} onChange={event => setInput(event.target.value)} rows={2} placeholder="Send a message to the Agent" className="min-w-0 flex-1 resize-y rounded border border-slate-300 px-3 py-2 text-sm" /><button type="submit" disabled={sending || !input.trim()} className="self-end rounded bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-50">{sending ? 'Sending…' : 'Send'}</button></div><div className="flex flex-wrap items-center gap-2 text-xs text-slate-600"><label className="rounded border border-slate-300 px-2 py-1">添加文件<input type="file" className="sr-only" onChange={event => setAttachment(event.target.files?.[0]?.name || '')} /></label><div className="relative"><button type="button" aria-expanded={modelOpen} onClick={() => { setModelOpen(value => !value); setPermissionOpen(false) }} className="flex min-w-28 items-center justify-between gap-2 rounded border border-slate-300 px-2 py-1"><span>模型 · {model === 'auto' ? '自动' : model}</span><span aria-hidden="true">⌄</span></button>{modelOpen ? <div role="menu" className="absolute bottom-[calc(100%+0.5rem)] right-0 min-w-40 rounded-lg border border-slate-200 bg-white p-1.5 text-slate-800 shadow-[0_8px_24px_rgba(15,23,42,0.12)]"><button type="button" role="menuitem" className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left hover:bg-slate-100" onClick={() => { setModel('auto'); setModelOpen(false) }}>自动</button><button type="button" role="menuitem" className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left hover:bg-slate-100" onClick={() => { setModel('fast'); setModelOpen(false) }}>快速</button><button type="button" role="menuitem" className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left hover:bg-slate-100" onClick={() => { setModel('quality'); setModelOpen(false) }}>高质量</button></div> : null}</div><PermissionPopover open={permissionOpen} fullAccess={fullAccess} onOpenChange={open => { setPermissionOpen(open); if (open) setModelOpen(false) }} onToggle={setFullAccess} />{attachment && <span role="status">已选：{attachment}</span>}</div></form>
    {commandState ? <p role="status" className="text-xs text-slate-500">Command status: {commandState}</p> : null}
    {sendError ? <p role="alert" className="text-sm text-red-700">{sendError}</p> : null}
    {actionError ? <p role="alert" className="text-sm text-red-700">{actionError}</p> : null}
  </section>
}

function formatPayload(payload: unknown) {
  if (typeof payload === 'string') return payload
  try { return JSON.stringify(payload, null, 2) } catch { return '[unavailable payload]' }
}

function PermissionPopover({ open, fullAccess, onOpenChange, onToggle }: { open: boolean; fullAccess: boolean; onOpenChange: (open: boolean) => void; onToggle: (enabled: boolean) => void }) {
  const id = 'cloud-permission-popover'
  useEffect(() => {
    if (!open) return
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') onOpenChange(false) }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [onOpenChange, open])

  return <div className="relative">
    <button type="button" aria-controls={id} aria-expanded={open} onClick={() => onOpenChange(!open)} className="flex min-w-32 items-center justify-between gap-2 rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 transition-colors hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400/40">
      <span>{fullAccess ? '完全授权' : '默认权限'}</span><span aria-hidden="true" className="text-[10px]">⌄</span>
    </button>
    {open ? <div id={id} role="dialog" aria-label="权限设置" className="absolute bottom-[calc(100%+0.5rem)] left-0 z-30 w-64 rounded-lg border border-slate-200 bg-white p-3 text-slate-800 shadow-[0_10px_28px_rgba(15,23,42,0.14)]">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold text-slate-900">权限模式</p>
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${fullAccess ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'}`}>{fullAccess ? '完全授权' : '默认'}</span>
      </div>
      <p className="mt-2 text-[13px] leading-5 text-slate-500">默认权限会在沙箱内运行；超出范围时，Agent 会先请求你的允许。</p>
      <label className="mt-3 flex cursor-pointer items-center justify-between gap-3 border-t border-slate-100 pt-3 text-xs font-medium text-slate-700">
        <span>允许完全访问</span>
        <input type="checkbox" checked={fullAccess} onChange={event => onToggle(event.target.checked)} className="h-4 w-4 accent-[var(--primary)]" />
      </label>
    </div> : null}
  </div>
}

function NewCloudSessionComposer({ client, onCreated }: { client: CloudClient; onCreated?: (session: CloudSession) => void }) {
  const [input, setInput] = useState('')
  const [models, setModels] = useState<CloudModel[]>([])
  const [model, setModel] = useState('')
  const [modelOpen, setModelOpen] = useState(false)
  const [permissionOpen, setPermissionOpen] = useState(false)
  const [bottomOpen, setBottomOpen] = useState(false)
  const [sideOpen, setSideOpen] = useState(false)
  const [fullAccess, setFullAccess] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { void client.listModels().then(value => { const enabled = value.filter(item => item.enabled); setModels(enabled); setModel(enabled.find(item => item.is_default)?.id ?? enabled[0]?.id ?? '') }).catch(() => setModels([])) }, [client])
  async function send() {
    if (!input.trim() || !model || sending) return
    setSending(true); setError(null)
    try { const session = await client.createSession('cloud_native', input.trim().slice(0, 40), 'default', model); await client.sendCommand(session.id, crypto.randomUUID(), `${fullAccess ? '[完全授权] ' : ''}${input.trim()}`); onCreated?.(session) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to create cloud session') } finally { setSending(false) }
  }
  return <section aria-label="新建云端会话" className="relative min-h-[calc(100dvh-4.5rem)] bg-[var(--surface-container-lowest)] pb-36"><header className="flex justify-end gap-2 p-4"><button type="button" aria-label="打开底部面板" title="打开底部面板" aria-expanded={bottomOpen} onClick={() => setBottomOpen(value => !value)} className="rounded p-2 text-sm text-slate-500 hover:bg-slate-100">▱</button><button type="button" aria-label="打开侧边面板" title="打开侧边面板" aria-expanded={sideOpen} onClick={() => setSideOpen(value => !value)} className="rounded p-2 text-sm text-slate-500 hover:bg-slate-100">◫</button></header>{sideOpen ? <aside className="absolute right-4 top-16 z-10 w-64 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface)] p-4 text-sm shadow-lg"><strong>会话摘要</strong><p className="mt-3 text-[var(--on-surface-variant)]">创建会话后，这里显示命令、审批和事件。</p></aside> : null}{bottomOpen ? <aside className="absolute bottom-36 left-4 right-4 z-10 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface)] p-4 text-sm shadow-lg md:left-[calc(24rem+1rem)]"><strong>运行面板</strong><p className="mt-3 text-[var(--on-surface-variant)]">发送消息后，这里显示 Agent 运行状态。</p></aside> : null}<form onSubmit={event => { event.preventDefault(); void send() }} className="fixed bottom-4 left-4 right-4 z-20 space-y-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-container-lowest)] p-3 shadow-lg md:left-[calc(24rem+1rem)]"><textarea aria-label="输入消息" value={input} onChange={event => setInput(event.target.value)} rows={3} maxLength={4000} placeholder="继续告诉 Agent 你要完成什么…" className="block min-h-20 w-full resize-y border-0 bg-transparent px-2 py-1 text-sm outline-none" /><div className="flex flex-wrap items-center gap-2 text-xs text-slate-600"><button type="button" className="rounded border border-slate-300 px-2 py-1 text-[var(--primary)]">＋ 添加</button><PermissionPopover open={permissionOpen} fullAccess={fullAccess} onOpenChange={open => { setPermissionOpen(open); if (open) setModelOpen(false) }} onToggle={setFullAccess} /><div className="relative"><button type="button" aria-expanded={modelOpen} onClick={() => { setModelOpen(value => !value); setPermissionOpen(false) }} className="flex min-w-32 items-center justify-between gap-2 rounded border border-slate-300 px-2 py-1"><span>{model ? models.find(item => item.id === model)?.name ?? '已选择模型' : '没有模型'}</span><span aria-hidden="true">⌄</span></button>{modelOpen ? <div role="menu" className="absolute bottom-[calc(100%+0.5rem)] right-0 min-w-44 rounded-lg border border-slate-200 bg-white p-1.5 text-slate-800 shadow-[0_8px_24px_rgba(15,23,42,0.12)]">{models.length ? models.map(item => <button key={item.id} type="button" role="menuitem" className="flex w-full rounded-md px-2 py-1.5 text-left hover:bg-slate-100" onClick={() => { setModel(item.id); setModelOpen(false) }}>{item.name}</button>) : <p className="p-2 text-sm text-slate-500">没有模型，请先到设置中添加。</p>}</div> : null}</div><span className="ml-auto text-slate-400">{input.length} / 4000</span><button type="submit" aria-label="发送" disabled={sending || !input.trim() || !model} className="grid h-9 w-9 place-items-center rounded-full bg-[var(--primary)] text-white disabled:opacity-40">↑</button></div>{error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}</form></section>
}
