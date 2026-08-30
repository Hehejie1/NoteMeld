import { useEffect, useState } from 'react'
import CloudClient, { CloudDevice } from '../../services/cloud'

export function CloudDeviceList({ client, onRevoke }: { client: CloudClient; onRevoke?: (device: CloudDevice) => void }) {
  const [devices, setDevices] = useState<CloudDevice[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  useEffect(() => { let active = true; void client.listDevices().then(value => { if (active) setDevices(value as CloudDevice[]) }).catch(reason => { if (active) setError(reason instanceof Error ? reason : new Error(String(reason))) }).finally(() => { if (active) setLoading(false) }); return () => { active = false } }, [client])
  if (loading) return <div aria-busy="true" className="space-y-2 p-3"><div className="h-10 animate-pulse rounded bg-slate-100" /><div className="h-10 animate-pulse rounded bg-slate-100" /></div>
  if (error) return <div role="alert" className="p-3 text-sm text-red-700">Unable to load devices: {error.message}</div>
  if (!devices.length) return <div role="status" className="p-4 text-sm text-slate-500">No devices connected.</div>
  return <ul role="list" aria-label="Connected devices" className="space-y-2 p-2">{devices.map(device => <li key={device.id} className="flex items-center justify-between gap-3 rounded border border-slate-200 p-3"><div className="min-w-0"><p className="truncate text-sm font-medium text-slate-900">{device.display_name}</p><p className="text-xs text-slate-500">{device.platform} · {device.online ? 'Online' : 'Offline'}</p>{device.connectivity?.lan_endpoints?.length ? <p className="truncate text-xs text-slate-400">LAN: {device.connectivity.lan_endpoints.join(', ')}</p> : null}</div><button type="button" className="shrink-0 rounded border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50" onClick={async () => { await client.revokeDevice(device.id); onRevoke?.(device) }}>Revoke</button></li>)}</ul>
}
