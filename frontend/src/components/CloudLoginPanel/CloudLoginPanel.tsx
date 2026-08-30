import { FormEvent, useState } from 'react'
import CloudClient from '../../services/cloud'

export function CloudLoginPanel({ client, onLoggedIn }: { client: CloudClient; onLoggedIn?: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try { await client.login(password, username); onLoggedIn?.() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Login failed') } finally { setBusy(false) }
  }
  return <form onSubmit={submit} aria-labelledby="cloud-login-title" className="mx-auto flex w-full max-w-sm flex-col gap-4 p-6">
    <div><h1 id="cloud-login-title" className="text-xl font-semibold text-slate-900">Sign in to NoteMeld Cloud</h1><p className="mt-1 text-sm text-slate-500">Use the account created by your cloud administrator.</p></div>
    <div className="flex flex-col gap-1"><label htmlFor="cloud-username" className="text-sm font-medium text-slate-700">Username</label><input id="cloud-username" autoComplete="username" required value={username} onChange={event => setUsername(event.target.value)} className="rounded border border-slate-300 px-3 py-2" /></div>
    <div className="flex flex-col gap-1"><label htmlFor="cloud-password" className="text-sm font-medium text-slate-700">Password</label><input id="cloud-password" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} className="rounded border border-slate-300 px-3 py-2" /></div>
    {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
    <button type="submit" disabled={busy} className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">{busy ? 'Signing in…' : 'Sign in'}</button>
  </form>
}
