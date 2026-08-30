import { useState } from 'react'
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

  if (!sessionId) return <section aria-label="Cloud session" className="p-4 text-sm text-slate-500">Select a session to begin.</section>
  if (loading && !session) return <section aria-busy="true" aria-label="Loading cloud session" className="space-y-3 p-4"><div className="h-5 w-48 animate-pulse rounded bg-slate-200" /><div className="h-24 animate-pulse rounded bg-slate-100" /></section>
  if (error && !session) return <section role="alert" className="p-4 text-sm text-red-700">Unable to load this session: {error.message}</section>
  if (!session) return <section role="status" className="p-4 text-sm text-slate-500">This session is unavailable.</section>

  return <section aria-labelledby="cloud-session-title" className="flex min-h-0 flex-col gap-4 p-4">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 id="cloud-session-title" className="text-lg font-semibold text-slate-900">{session.title || 'Cloud session'}</h2>
        <p className="text-xs text-slate-500">{session.kind} · {session.status || 'idle'}</p>
      </div>
      <div className="flex gap-2">
        <button type="button" className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50" onClick={() => void controller.refreshEvents()}>Refresh</button>
        <button type="button" className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50" onClick={async () => { const copy = await controller.copy(); onCopy?.(copy.id) }}>Copy branch</button>
        <button type="button" className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50" onClick={async () => { await controller.archive(); onArchived?.() }}>Archive</button>
      </div>
    </header>
    <div role="log" aria-live="polite" className="min-h-24 flex-1 overflow-auto rounded border border-slate-200 bg-white p-3">
      {events.length === 0 ? <p className="text-sm text-slate-500">No events yet.</p> : <ol className="space-y-3">{events.map((event: any, index) => <li key={`${event.sequence ?? 'event'}-${index}`} className="border-b border-slate-100 pb-2 text-sm"><span className="mr-2 font-mono text-xs text-slate-400">#{event.sequence ?? index + 1}</span>{event.event_type || 'event'}</li>)}</ol>}
    </div>
    <form onSubmit={async event => { event.preventDefault(); if (!input.trim() || sending) return; setSending(true); setSendError(null); try { await controller.send(input.trim(), crypto.randomUUID()); setInput(''); await controller.refreshEvents() } catch (reason) { setSendError(reason instanceof Error ? reason.message : 'Unable to send message') } finally { setSending(false) } }} className="flex gap-2"><label htmlFor="cloud-session-input" className="sr-only">Message</label><textarea id="cloud-session-input" value={input} onChange={event => setInput(event.target.value)} rows={2} placeholder="Send a message to the Agent" className="min-w-0 flex-1 resize-y rounded border border-slate-300 px-3 py-2 text-sm" /><button type="submit" disabled={sending || !input.trim()} className="self-end rounded bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-50">{sending ? 'Sending…' : 'Send'}</button></form>
    {sendError ? <p role="alert" className="text-sm text-red-700">{sendError}</p> : null}
  </section>
}
