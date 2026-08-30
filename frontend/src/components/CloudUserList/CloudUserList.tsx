import { useEffect, useState } from 'react'
import CloudClient, { CloudUser } from '../../services/cloud'

export function CloudUserList({ client, onChanged }: { client: CloudClient; onChanged?: () => void }) {
  const [users, setUsers] = useState<CloudUser[]>([]); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState<string | null>(null)
  async function refresh() { try { setUsers(await client.listUsers()); setError(null) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to load users') } }
  useEffect(() => { void refresh() }, [client])
  async function remove(user: CloudUser) { if (user.role === 'admin') return; setBusy(user.id); try { await client.deleteUser(user.id); await refresh(); onChanged?.() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to delete user') } finally { setBusy(null) } }
  if (error && !users.length) return <section role="alert" className="p-3 text-sm text-red-700">{error}</section>
  if (!users.length) return <section role="status" className="p-4 text-sm text-slate-500">No cloud users.</section>
  return <section aria-labelledby="user-list-title" className="p-3"><h2 id="user-list-title" className="mb-2 text-base font-semibold">Cloud users</h2><ul role="list" className="space-y-2">{users.map(user => <li key={user.id} className="flex items-center justify-between rounded border border-slate-200 p-3"><div><p className="text-sm font-medium">{user.username}</p><p className="text-xs text-slate-500">{user.role} · {user.disabled ? 'Disabled' : 'Active'}</p></div>{user.role === 'user' ? <button type="button" disabled={busy === user.id} onClick={() => void remove(user)} className="rounded border border-red-200 px-2 py-1 text-xs text-red-700 disabled:opacity-50">Delete</button> : <span className="text-xs text-slate-400">Protected</span>}</li>)}</ul>{error ? <p role="alert" className="mt-2 text-sm text-red-700">{error}</p> : null}</section>
}
