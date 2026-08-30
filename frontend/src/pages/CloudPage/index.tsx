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
import { CloudWorkspaceBrowser } from '../../components/CloudWorkspaceBrowser'
import { CloudUserList } from '../../components/CloudUserList'
import { CloudUserForm } from '../../components/CloudUserForm'
import { makeDeviceId } from '../../services/deviceIdentity'

export default function CloudPage() {
  const baseUrl = import.meta.env.VITE_CLOUD_BASE_URL || 'http://127.0.0.1:8583'
  const [deviceId] = useState(() => makeDeviceId('web'))
  const [client, setClient] = useState(() => new CloudClient(baseUrl, undefined, deviceId))
  const [secureStorageReady, setSecureStorageReady] = useState(false)
  const [secureStorageError, setSecureStorageError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string>()
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>()
  const [showArchived, setShowArchived] = useState(false)
  const [listVersion, setListVersion] = useState(0)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [archiveAction, setArchiveAction] = useState(false)
  const [archiveError, setArchiveError] = useState<string | null>(null)
  const [capabilities, setCapabilities] = useState<{ protocol_version?: string; relay_persists_payload?: boolean; lan_first_candidates?: boolean } | null>(null)
  useEffect(() => { let active = true; void openIndexedDbTokenStore().then(store => { if (active) { setClient(new CloudClient(baseUrl, undefined, deviceId, store)); setSecureStorageReady(true); setSecureStorageError(null) } }).catch(() => { if (active) setSecureStorageError('Secure browser storage is unavailable. Cloud sign-in is disabled on this browser.') }); return () => { active = false } }, [baseUrl, deviceId])
  const auth = useCloudAuth(client)
  useEffect(() => {
    if (!auth.authenticated) return
    let active = true
    const announce = () => { void client.heartbeat(deviceId).catch(() => undefined) }
    void client.registerDevice(deviceId, 'web', 'Web browser').then(() => { if (active) announce() }).catch(() => undefined)
    const timer = window.setInterval(announce, 30_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [auth.authenticated, client, deviceId])
  useEffect(() => {
    if (!auth.authenticated) return
    void client.capabilities().then(setCapabilities).catch(() => setCapabilities(null))
  }, [auth.authenticated, client])
  if (secureStorageError) return <main role="alert" className="p-6 text-sm text-red-700">{secureStorageError}</main>
  if (!secureStorageReady) return <main aria-busy="true" className="p-6 text-sm text-slate-500">Preparing secure cloud storage…</main>
  async function createSession() {
    setCreating(true); setCreateError(null)
    try { const session = await client.createSession('cloud_native'); setSelectedId(session.id); setSelectedWorkspaceId(session.workspace_id); setListVersion(value => value + 1) } catch (reason) { setCreateError(reason instanceof Error ? reason.message : 'Unable to create session') } finally { setCreating(false) }
  }
  async function restoreSession(id: string) { setArchiveAction(true); setArchiveError(null); try { await client.restoreSession(id); setListVersion(value => value + 1) } catch (reason) { setArchiveError(reason instanceof Error ? reason.message : 'Unable to restore session') } finally { setArchiveAction(false) } }
  async function deleteSession(id: string) { if (!window.confirm('Delete this archived session permanently?')) return; setArchiveAction(true); setArchiveError(null); try { await client.deleteSession(id); setSelectedId(undefined); setListVersion(value => value + 1) } catch (reason) { setArchiveError(reason instanceof Error ? reason.message : 'Unable to delete session') } finally { setArchiveAction(false) } }
  if (auth.loading) return <main aria-busy="true" className="p-6 text-sm text-slate-500">Connecting to NoteMeld Cloud…</main>
  if (!auth.authenticated) return <main className="flex min-h-app items-center justify-center"><CloudLoginPanel client={client} /></main>
  return <main aria-label="Cloud workspace" className="flex min-h-app flex-col bg-[var(--surface)] text-[var(--on-surface)] md:grid md:grid-cols-[minmax(17rem,24rem)_minmax(0,1fr)]">
    <aside className="flex min-h-0 flex-col border-b border-[var(--border-subtle)] bg-[var(--sidebar-bg)] md:border-r md:border-b-0">
      <header className="border-b border-[var(--border-subtle)] px-4 py-4 md:px-5">
        <div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--primary)]">NoteMeld Cloud</p><h1 className="mt-1 text-lg font-semibold">{showArchived ? 'Archived sessions' : 'Cloud sessions'}</h1></div><button type="button" className="rounded-md px-2 py-1 text-sm text-[var(--sidebar-muted)] hover:bg-[var(--surface-container)]" onClick={() => void auth.logout()}>Sign out</button></div>
        <div className="mt-4 flex flex-wrap gap-2"><button type="button" disabled={creating || showArchived} className="rounded-md bg-[var(--primary)] px-3 py-2 text-xs font-medium text-white shadow-sm disabled:opacity-50" onClick={() => void createSession()}>{creating ? 'Creating…' : '+ New session'}</button><button type="button" disabled={archiveAction} className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-container-lowest)] px-3 py-2 text-xs font-medium disabled:opacity-50" onClick={() => { setShowArchived(value => !value); setSelectedId(undefined); setSelectedWorkspaceId(undefined) }}>{showArchived ? 'Active sessions' : 'Archived'}</button></div>
        {createError ? <p role="alert" className="mt-2 text-xs text-[var(--error)]">{createError}</p> : null}{archiveError ? <p role="alert" className="mt-2 text-xs text-[var(--error)]">{archiveError}</p> : null}
      </header>
      <div className="min-h-0 flex-1 overflow-auto"><CloudSessionList key={`${listVersion}-${showArchived}`} client={client} archived={showArchived} selectedId={selectedId} onSelect={session => { setSelectedId(session.id); setSelectedWorkspaceId(session.workspace_id) }} onRestore={session => void restoreSession(session.id)} onDelete={session => void deleteSession(session.id)} /></div>
      <div className="border-t border-[var(--border-subtle)] px-4 py-3 text-xs text-[var(--sidebar-muted)]"><div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-[var(--status-success)]" aria-hidden="true" />{capabilities ? `Protocol ${capabilities.protocol_version ?? 'v1'} · ${capabilities.lan_first_candidates ? 'LAN preferred' : 'Relay'}` : 'Checking cloud capabilities…'}</div><p className="mt-1">Relay payload persistence: {capabilities?.relay_persists_payload ? 'enabled' : 'disabled'}</p></div>
      <details className="border-t border-[var(--border-subtle)]"><summary className="cursor-pointer px-4 py-3 text-sm font-medium">Devices & remote access</summary><CloudDeviceList client={client} /><CloudPairingPanel client={client} /><CloudGrantPanel client={client} /></details><details className="border-t border-[var(--border-subtle)]"><summary className="cursor-pointer px-4 py-3 text-sm font-medium">Cloud models</summary><CloudModelList client={client} /><CloudModelForm client={client} /></details>{auth.role === 'admin' ? <details className="border-t border-[var(--border-subtle)]"><summary className="cursor-pointer px-4 py-3 text-sm font-medium">Administration</summary><CloudUserList client={client} /><CloudUserForm client={client} /></details> : null}
    </aside>
    <section className="min-h-0 min-w-0 overflow-auto bg-[var(--surface-container-lowest)]"><CloudSessionPanel client={client} sessionId={selectedId} onArchived={() => { setSelectedId(undefined); setSelectedWorkspaceId(undefined); setListVersion(value => value + 1) }} />{selectedId && !showArchived ? <><CloudWorkspaceBrowser client={client} workspaceId={selectedWorkspaceId ?? 'default'} /><CloudSharePanel client={client} sessionId={selectedId} /><details className="border-t border-[var(--border-subtle)]"><summary className="cursor-pointer px-4 py-3 text-sm font-medium">Pending approvals</summary><CloudApprovalList client={client} sessionId={selectedId} /></details></> : <div className="mx-auto max-w-xl px-6 pb-12 text-center text-sm text-[var(--on-surface-variant)]"><p>Select a session to inspect its events, workspace and approvals.</p></div>}</section>
  </main>
}
