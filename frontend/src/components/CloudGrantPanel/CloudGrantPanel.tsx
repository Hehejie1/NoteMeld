import { useState } from 'react'
import CloudClient from '../../services/cloud'

export function CloudGrantPanel({ client, onCreated }: { client: CloudClient; onCreated?: () => void }) {
  const [controller, setController] = useState('')
  const [host, setHost] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  async function create() { setBusy(true); setError(null); setMessage(null); try { await client.createGrant(controller, host, ['message.send', 'context.select', 'model.select', 'tool.invoke']); setMessage('Remote control permission created.'); onCreated?.() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to create permission') } finally { setBusy(false) } }
  return <section aria-labelledby="grant-title" className="flex max-w-md flex-col gap-3 p-4"><div><h2 id="grant-title" className="text-lg font-semibold text-slate-900">Remote control permission</h2><p className="text-sm text-slate-500">Choose which device may control the host. Dangerous actions still require host approval.</p></div><label htmlFor="grant-controller" className="text-sm font-medium">Controller device ID</label><input id="grant-controller" required value={controller} onChange={event => setController(event.target.value)} className="rounded border border-slate-300 px-3 py-2" /><label htmlFor="grant-host" className="text-sm font-medium">Host device ID</label><input id="grant-host" required value={host} onChange={event => setHost(event.target.value)} className="rounded border border-slate-300 px-3 py-2" /><button type="button" disabled={busy || !controller || !host} onClick={() => void create()} className="rounded bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-50">{busy ? 'Creating…' : 'Allow standard control'}</button>{message ? <p role="status" className="text-sm text-slate-600">{message}</p> : null}{error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}</section>
}
