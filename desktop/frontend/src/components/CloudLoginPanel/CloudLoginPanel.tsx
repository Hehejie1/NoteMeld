import { FormEvent, useState } from 'react'
import CloudClient from '../../services/cloud'

export function CloudLoginPanel({ client, onLoggedIn }: { client: CloudClient; onLoggedIn?: () => void }) {
  const [mode, setMode] = useState<'login' | 'request'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [reason, setReason] = useState('')
  const [remember, setRemember] = useState(() => localStorage.getItem('notemeld-cloud-remember') === '1')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try { if (mode === 'request') { localStorage.setItem('notemeld-cloud-access-request', JSON.stringify({ username, name, reason, createdAt: Date.now() })); setError('申请已提交，管理员审核通过后即可登录'); return } await client.login(password, username); if (remember) localStorage.setItem('notemeld-cloud-remember', '1'); else localStorage.removeItem('notemeld-cloud-remember'); onLoggedIn?.() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Login failed') } finally { setBusy(false) }
  }
  return <form onSubmit={submit} aria-labelledby="cloud-login-title" className="mx-auto flex w-full max-w-sm flex-col gap-4 p-6">
    <div><h1 id="cloud-login-title" className="text-xl font-semibold text-slate-900">{mode === 'login' ? 'Sign in to NoteMeld Cloud' : '申请访问 NoteMeld Cloud'}</h1><p className="mt-1 text-sm text-slate-500">{mode === 'login' ? 'Use the account created by your cloud administrator.' : '提交后由管理员审核，申请记录仅保存在当前浏览器。'}</p></div>
    <div className="flex flex-col gap-1"><label htmlFor="cloud-username" className="text-sm font-medium text-slate-700">邮箱或用户名</label><input id="cloud-username" autoComplete="username" required value={username} onChange={event => setUsername(event.target.value)} className="rounded border border-slate-300 px-3 py-2" /></div>
    {mode === 'request' ? <><div className="flex flex-col gap-1"><label htmlFor="cloud-name" className="text-sm font-medium text-slate-700">姓名</label><input id="cloud-name" required value={name} onChange={event => setName(event.target.value)} className="rounded border border-slate-300 px-3 py-2" /></div><div className="flex flex-col gap-1"><label htmlFor="cloud-reason" className="text-sm font-medium text-slate-700">申请说明</label><textarea id="cloud-reason" required value={reason} onChange={event => setReason(event.target.value)} className="rounded border border-slate-300 px-3 py-2" /></div></> : <div className="flex flex-col gap-1"><label htmlFor="cloud-password" className="text-sm font-medium text-slate-700">Password</label><input id="cloud-password" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} className="rounded border border-slate-300 px-3 py-2" /><label className="mt-1 flex items-center gap-2 text-xs text-slate-500"><input type="checkbox" checked={remember} onChange={event => setRemember(event.target.checked)} /> 记住登录</label></div>}
    {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
    <button type="submit" disabled={busy} className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">{busy ? '处理中…' : mode === 'login' ? '登录' : '提交申请'}</button>
    <div className="flex justify-between text-xs text-slate-500"><button type="button" onClick={() => setMode(mode === 'login' ? 'request' : 'login')}>{mode === 'login' ? '申请访问' : '返回登录'}</button>{mode === 'login' ? <button type="button" onClick={() => setError('请联系管理员重置密码')}>忘记密码？</button> : null}</div>
  </form>
}
