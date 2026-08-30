import { useEffect, useState } from 'react'
import CloudClient, { CloudModel } from '../../services/cloud'

export function CloudModelList({ client }: { client: CloudClient }) {
  const [models, setModels] = useState<CloudModel[]>([])
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { let active = true; void client.listModels().then(value => { if (active) setModels(value) }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Unable to load models') }); return () => { active = false } }, [client])
  if (error) return <section role="alert" className="p-3 text-sm text-red-700">{error}</section>
  if (!models.length) return <section role="status" className="p-4 text-sm text-slate-500">No cloud models configured.</section>
  return <section aria-labelledby="model-list-title" className="p-3"><h2 id="model-list-title" className="mb-2 text-base font-semibold text-slate-900">Cloud models</h2><ul role="list" className="space-y-2">{models.map(model => <li key={model.id} className="flex items-center justify-between rounded border border-slate-200 p-3"><div><p className="text-sm font-medium">{model.name}{model.is_default ? ' · Default' : ''}</p><p className="text-xs text-slate-500">{model.provider} / {model.model}</p></div><span className="text-xs text-slate-500">{model.has_api_key ? 'Credential saved' : 'No credential'}</span></li>)}</ul></section>
}
