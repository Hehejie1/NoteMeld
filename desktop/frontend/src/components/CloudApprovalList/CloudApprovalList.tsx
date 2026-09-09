import { useEffect, useState } from 'react'
import CloudClient from '../../services/cloud'

type Approval = { id: string; tool_name?: string; status: string; created_at?: number; arguments?: Record<string, unknown> }

export function CloudApprovalList({ client, sessionId }: { client: CloudClient; sessionId: string }) {
  const [items, setItems] = useState<Approval[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  async function refresh() { try { setItems(await client.listApprovals(sessionId) as Approval[]); setError(null) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load approvals') } }
  useEffect(() => { void refresh() }, [sessionId])
  async function resolve(item: Approval, status: 'approved' | 'rejected') { setBusy(item.id); setError(null); try { await client.resolveApproval(sessionId, item.id, status); await refresh() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to resolve approval') } finally { setBusy(null) } }
  if (error && !items.length) return <section role="alert" className="p-3 text-sm text-red-700">{error}</section>
  const pending = items.filter(item => item.status === 'pending')
  if (!pending.length) return <section role="status" aria-label="Approvals" className="p-4 text-sm text-slate-500">No pending approvals.</section>
  return <section aria-labelledby="approval-title" className="space-y-2 p-3"><h2 id="approval-title" className="text-base font-semibold text-slate-900">Approval required</h2><ul role="list" className="space-y-2">{pending.map(item => <li key={item.id} className="rounded border border-amber-200 bg-amber-50 p-3"><p className="text-sm font-medium text-slate-900">{item.tool_name || 'Sensitive action'}</p><p className="mt-1 truncate text-xs text-slate-600">Review on the host before allowing this action.</p><div className="mt-3 flex gap-2"><button type="button" disabled={busy === item.id} onClick={() => void resolve(item, 'approved')} className="rounded bg-slate-900 px-3 py-1.5 text-xs text-white disabled:opacity-50">Approve</button><button type="button" disabled={busy === item.id} onClick={() => void resolve(item, 'rejected')} className="rounded border border-slate-300 px-3 py-1.5 text-xs">Reject</button></div></li>)}</ul>{error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}</section>
}
