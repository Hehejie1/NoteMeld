import { useState } from 'react'
import CloudClient from '../../services/cloud'

export function CloudGrantPanel({ client, onCreated }: { client: CloudClient; onCreated?: () => void }) {
  const [controller, setController] = useState('')
  const [host, setHost] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [scopes, setScopes] = useState(['message.send', 'context.select', 'model.select', 'tool.invoke'])
  const availableScopes = [['workspace.read', '访问 Workspace 文件'], ['message.send', '查看并发送云端会话'], ['artifact.download', '下载产物'], ['tool.invoke', '远程执行（仍需审批）']] as const
  async function create() { setBusy(true); setError(null); setMessage(null); try { await client.createGrant(controller, host, scopes); setMessage('设备授权已保存。'); onCreated?.() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to create permission') } finally { setBusy(false) } }
  return <section aria-labelledby="grant-title" className="flex max-w-md flex-col gap-3 p-4"><div><h2 id="grant-title" className="text-lg font-semibold text-slate-900">设备权限</h2><p className="text-sm text-slate-500">选择控制设备可使用的能力，高风险操作仍需宿主审批。</p></div><label htmlFor="grant-controller" className="text-sm font-medium">控制端设备 ID</label><input id="grant-controller" required value={controller} onChange={event => setController(event.target.value)} className="rounded border border-slate-300 px-3 py-2" /><label htmlFor="grant-host" className="text-sm font-medium">被控端设备 ID</label><input id="grant-host" required value={host} onChange={event => setHost(event.target.value)} className="rounded border border-slate-300 px-3 py-2" /><fieldset className="space-y-2"><legend className="text-sm font-medium">授权范围</legend>{availableScopes.map(([scope, label]) => <label key={scope} className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={scopes.includes(scope)} onChange={event => setScopes(current => event.target.checked ? [...new Set([...current, scope])] : current.filter(item => item !== scope))} />{label}</label>)}</fieldset><button type="button" disabled={busy || !controller || !host || !scopes.length} onClick={() => void create()} className="rounded bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-50">{busy ? '保存中…' : '保存设备权限'}</button>{message ? <p role="status" className="text-sm text-slate-600">{message}</p> : null}{error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}</section>
}
