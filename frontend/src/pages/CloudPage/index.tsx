import { useMemo, useState } from 'react'
import CloudClient from '../../services/cloud'
import { useCloudAuth } from '../../hooks/useCloudAuth'
import { CloudLoginPanel } from '../../components/CloudLoginPanel'
import { CloudSessionList } from '../../components/CloudSessionList'
import { CloudSessionPanel } from '../../components/CloudSessionPanel'

export default function CloudPage() {
  const client = useMemo(() => new CloudClient(import.meta.env.VITE_CLOUD_BASE_URL || 'http://127.0.0.1:8583'), [])
  const auth = useCloudAuth(client)
  const [selectedId, setSelectedId] = useState<string>()
  if (auth.loading) return <main aria-busy="true" className="p-6 text-sm text-slate-500">Connecting to NoteMeld Cloud…</main>
  if (!auth.authenticated) return <main className="flex min-h-app items-center justify-center"><CloudLoginPanel client={client} /></main>
  return <main aria-label="Cloud workspace" className="grid min-h-app grid-cols-[minmax(15rem,22rem)_minmax(0,1fr)] bg-white max-md:grid-cols-1"><aside className="border-r border-slate-200 max-md:border-r-0 max-md:border-b"><header className="flex items-center justify-between px-4 py-3"><h1 className="font-semibold text-slate-900">Cloud sessions</h1><button type="button" className="text-sm text-slate-600 underline" onClick={() => void auth.logout()}>Sign out</button></header><CloudSessionList client={client} selectedId={selectedId} onSelect={session => setSelectedId(session.id)} /></aside><section className="min-w-0"><CloudSessionPanel client={client} sessionId={selectedId} /></section></main>
}
