import { useEffect, useState } from 'react'
import CloudClient from '../../services/cloud'
import { useCloudAuth } from '../../hooks/useCloudAuth'
import { openIndexedDbTokenStore } from '../../services/tokenStore'
import { CloudLoginPanel } from '../../components/CloudLoginPanel'
import { CloudSessionList } from '../../components/CloudSessionList'
import { CloudSessionPanel } from '../../components/CloudSessionPanel'
import { CloudSharePanel } from '../../components/CloudSharePanel'
import { CloudDeviceList } from '../../components/CloudDeviceList'
import { CloudPairingPanel } from '../../components/CloudPairingPanel'
import { CloudGrantPanel } from '../../components/CloudGrantPanel'
import { CloudModelList } from '../../components/CloudModelList'
import { CloudModelForm } from '../../components/CloudModelForm'
import { CloudApprovalList } from '../../components/CloudApprovalList'

export default function CloudPage() {
  const baseUrl = import.meta.env.VITE_CLOUD_BASE_URL || 'http://127.0.0.1:8583'
  const [client, setClient] = useState(() => new CloudClient(baseUrl))
  const [secureStorageReady, setSecureStorageReady] = useState(false)
  useEffect(() => { let active = true; void openIndexedDbTokenStore().then(store => { if (active) { setClient(new CloudClient(baseUrl, undefined, undefined, store)); setSecureStorageReady(true) } }).catch(() => { if (active) setSecureStorageReady(true) }); return () => { active = false } }, [baseUrl])
  const auth = useCloudAuth(client)
  if (!secureStorageReady) return <main aria-busy="true" className="p-6 text-sm text-slate-500">Preparing secure cloud storage…</main>
  const [selectedId, setSelectedId] = useState<string>()
  const [showArchived, setShowArchived] = useState(false)
  const [listVersion, setListVersion] = useState(0)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [archiveAction, setArchiveAction] = useState(false)
  const [archiveError, setArchiveError] = useState<string | null>(null)
  async function createSession() {
    setCreating(true); setCreateError(null)
    try { const session = await client.createSession('cloud_native'); setSelectedId(session.id); setListVersion(value => value + 1) } catch (reason) { setCreateError(reason instanceof Error ? reason.message : 'Unable to create session') } finally { setCreating(false) }
  }
  async function restoreSession(id: string) { setArchiveAction(true); setArchiveError(null); try { await client.restoreSession(id); setListVersion(value => value + 1) } catch (reason) { setArchiveError(reason instanceof Error ? reason.message : 'Unable to restore session') } finally { setArchiveAction(false) } }
  async function deleteSession(id: string) { if (!window.confirm('Delete this archived session permanently?')) return; setArchiveAction(true); setArchiveError(null); try { await client.deleteSession(id); setSelectedId(undefined); setListVersion(value => value + 1) } catch (reason) { setArchiveError(reason instanceof Error ? reason.message : 'Unable to delete session') } finally { setArchiveAction(false) } }
  if (auth.loading) return <main aria-busy="true" className="p-6 text-sm text-slate-500">Connecting to NoteMeld Cloud…</main>
  if (!auth.authenticated) return <main className="flex min-h-app items-center justify-center"><CloudLoginPanel client={client} /></main>
  return <main aria-label="Cloud workspace" className="grid min-h-app grid-cols-[minmax(15rem,22rem)_minmax(0,1fr)] bg-white max-md:grid-cols-1"><aside className="border-r border-slate-200 max-md:border-r-0 max-md:border-b"><header className="flex items-center justify-between px-4 py-3"><div><h1 className="font-semibold text-slate-900">Cloud sessions</h1><div className="mt-2 flex gap-2"><button type="button" disabled={creating || showArchived} className="rounded bg-slate-900 px-2 py-1 text-xs text-white disabled:opacity-50" onClick={() => void createSession()}>{creating ? 'Creating…' : 'New cloud session'}</button><button type="button" disabled={archiveAction} className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-50" onClick={() => { setShowArchived(value => !value); setSelectedId(undefined) }}>{showArchived ? 'Active sessions' : 'Archived sessions'}</button></div>{createError ? <p role="alert" className="mt-2 max-w-48 text-xs text-red-700">{createError}</p> : null}{archiveError ? <p role="alert" className="mt-2 max-w-48 text-xs text-red-700">{archiveError}</p> : null}</div><button type="button" className="text-sm text-slate-600 underline" onClick={() => void auth.logout()}>Sign out</button></header><CloudSessionList key={`${listVersion}-${showArchived}`} client={client} archived={showArchived} selectedId={selectedId} onSelect={session => setSelectedId(session.id)} onRestore={session => void restoreSession(session.id)} onDelete={session => void deleteSession(session.id)} /><details className="border-t border-slate-200"><summary className="cursor-pointer px-4 py-3 text-sm font-medium">Connected devices</summary><CloudDeviceList client={client} /><CloudPairingPanel client={client} /><CloudGrantPanel client={client} /></details><details className="border-t border-slate-200"><summary className="cursor-pointer px-4 py-3 text-sm font-medium">Cloud models</summary><CloudModelList client={client} /><CloudModelForm client={client} /></details></aside><section className="min-w-0"><CloudSessionPanel client={client} sessionId={selectedId} onArchived={() => { setSelectedId(undefined); setListVersion(value => value + 1) }} />{selectedId && !showArchived ? <><CloudSharePanel client={client} sessionId={selectedId} /><details className="border-t border-slate-200"><summary className="cursor-pointer px-4 py-3 text-sm font-medium">Pending approvals</summary><CloudApprovalList client={client} sessionId={selectedId} /></details></> : null}</section></main>
}
