import { useEffect, useRef, useState } from 'react'
import type CloudClient from '../../services/cloud'
import { useCloudSession } from '../../hooks/useCloudSession'

export interface CloudSessionPanelProps {
  client: CloudClient
  sessionId?: string
  onCopy?: (sessionId: string) => void
  onArchived?: () => void
}

export function CloudSessionPanel({ client, sessionId, onCopy, onArchived }: CloudSessionPanelProps) {
  const { session, events, loading, error, controller } = useCloudSession(client, sessionId)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [commandState, setCommandState] = useState<string | null>(null)
  const mounted = useRef(true)
  const pollTimers = useRef<number[]>([])
  useEffect(() => () => { mounted.current = false; pollTimers.current.forEach(timer => window.clearInterval(timer)) }, [])

  if (!sessionId) return <section aria-label="Cloud session" className="p-4 text-sm text-slate-500">Select a session to begin.</section>
  if (loading && !session) return <section aria-busy="true" aria-label="Loading cloud session" className="space-y-3 p-4"><div className="h-5 w-48 animate-pulse rounded bg-slate-200" /><div className="h-24 animate-pulse rounded bg-slate-100" /></section>
  if (error && !session) return <section role="alert" className="p-4 text-sm text-red-700">Unable to load this session: {error.message}</section>
  if (!session) return <section role="status" className="p-4 text-sm text-slate-500">This session is unavailable.</section>

  const status = session.status || 'idle'
  const statusTone = status === 'running' ? 'bg-blue-50 text-blue-700' : status === 'failed' ? 'bg-red-50 text-red-700' : status === 'waiting_approval' ? 'bg-amber-50 text-amber-700' : status === 'paused_offline' || status === 'needs_attention' ? 'bg-orange-50 text-orange-700' : 'bg-emerald-50 text-emerald-700'

  return <section aria-labelledby="cloud-session-title" className="flex min-h-0 flex-col gap-4 p-4 md:p-6">
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
    <form onSubmit={async event => { event.preventDefault(); if (!input.trim() || sending) return; setSending(true); setSendError(null); setCommandState('queued'); try { const result = await controller.send(input.trim(), crypto.randomUUID()) as { command_id?: string; status?: string }; if (!mounted.current) return; setInput(''); setCommandState(result.status ?? 'queued'); await controller.refreshEvents(); if (result.command_id && (result.status === 'queued' || result.status === 'running')) { const commandId = result.command_id; const poll = window.setInterval(() => { if (!mounted.current) { window.clearInterval(poll); return } void client.commandStatus(session.id, commandId).then(value => { if (!mounted.current) return; const status = String(value.status ?? 'queued'); setCommandState(status); if (!['queued', 'running'].includes(status)) window.clearInterval(poll) }).catch(() => window.clearInterval(poll)) }, 1500); pollTimers.current.push(poll); window.setTimeout(() => window.clearInterval(poll), 30000) } } catch (reason) { if (mounted.current) { setSendError(reason instanceof Error ? reason.message : 'Unable to send message'); setCommandState(null) } } finally { if (mounted.current) setSending(false) } }} className="flex gap-2"><label htmlFor="cloud-session-input" className="sr-only">Message</label><textarea id="cloud-session-input" value={input} onChange={event => setInput(event.target.value)} rows={2} placeholder="Send a message to the Agent" className="min-w-0 flex-1 resize-y rounded border border-slate-300 px-3 py-2 text-sm" /><button type="submit" disabled={sending || !input.trim()} className="self-end rounded bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-50">{sending ? 'Sending…' : 'Send'}</button></form>
    {commandState ? <p role="status" className="text-xs text-slate-500">Command status: {commandState}</p> : null}
    {sendError ? <p role="alert" className="text-sm text-red-700">{sendError}</p> : null}
    {actionError ? <p role="alert" className="text-sm text-red-700">{actionError}</p> : null}
  </section>
}

function formatPayload(payload: unknown) {
  if (typeof payload === 'string') return payload
  try { return JSON.stringify(payload, null, 2) } catch { return '[unavailable payload]' }
}
