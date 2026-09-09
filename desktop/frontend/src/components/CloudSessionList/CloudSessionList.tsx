import { useEffect, useState } from 'react'
import CloudClient from '../../services/cloud'
import type { CloudSession } from '../../services/cloud'

export function CloudSessionList({ client, archived = false, selectedId, onSelect, onRestore, onDelete }: { client: CloudClient; archived?: boolean; selectedId?: string; onSelect: (session: CloudSession) => void; onRestore?: (session: CloudSession) => void; onDelete?: (session: CloudSession) => void }) {
  const [sessions, setSessions] = useState<CloudSession[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  useEffect(() => {
    let active = true
    setLoading(true); setError(null)
    void client.listSessions(archived).then(value => { if (active) setSessions(value) }).catch(reason => { if (active) setError(reason instanceof Error ? reason : new Error(String(reason))) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [client, archived])
  if (loading) return <div aria-busy="true" className="space-y-2 p-3"><div className="h-9 animate-pulse rounded bg-slate-100" /><div className="h-9 animate-pulse rounded bg-slate-100" /></div>
  if (error) return <div role="alert" className="p-3 text-sm text-red-700">Unable to load sessions: {error.message}</div>
  if (!sessions.length) return <div role="status" className="p-4 text-sm text-slate-500">{archived ? 'No archived sessions.' : 'No active sessions.'}</div>
  return <nav aria-label={archived ? 'Archived sessions' : 'Active sessions'}><ul role="list" className="space-y-1 p-2">{sessions.map(session => <li key={session.id} className="rounded border border-transparent hover:border-slate-200"><button type="button" aria-current={selectedId === session.id ? 'page' : undefined} className="w-full rounded px-3 py-2 text-left hover:bg-slate-100 aria-[current=page]:bg-slate-100" onClick={() => onSelect(session)}><span className="block truncate text-sm font-medium text-slate-900">{session.title || 'Untitled session'}</span><span className="block text-xs text-slate-500">{session.status || 'idle'}</span></button>{archived ? <div className="flex gap-2 px-3 pb-2"><button type="button" className="text-xs text-slate-700 underline" onClick={() => onRestore?.(session)}>Restore</button><button type="button" className="text-xs text-red-700 underline" onClick={() => onDelete?.(session)}>Delete permanently</button></div> : null}</li>)}</ul></nav>
}
