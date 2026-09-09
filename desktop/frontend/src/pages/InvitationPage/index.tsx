import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import CloudClient from '@/services/cloud'

export default function InvitationPage() {
  const { token = '' } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const client = new CloudClient(import.meta.env.VITE_CLOUD_BASE_URL || 'http://127.0.0.1:8583')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  async function submit(event: React.FormEvent) { event.preventDefault(); if (!token) return setError('邀请链接无效'); if (password !== confirm) return setError('两次密码不一致'); setBusy(true); setError(null); try { await client.acceptInvitation(token, displayName.trim(), password); setDone(true) } catch (reason) { setError(reason instanceof Error ? reason.message : '邀请接受失败') } finally { setBusy(false) } }
  if (done) return <main className="flex min-h-app items-center justify-center bg-surface px-6"><section className="w-full max-w-md rounded-2xl border border-border-subtle bg-surface-container-lowest p-8 text-center shadow-sm"><h1 className="text-xl font-semibold text-on-surface">邀请已接受</h1><p className="mt-3 text-sm text-on-surface-variant">账号已创建，现在可以登录 NoteMeld Cloud。</p><button type="button" onClick={() => navigate('/cloud')} className="mt-6 rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground">前往登录</button></section></main>
  return <main className="flex min-h-app items-center justify-center bg-surface px-6"><form onSubmit={submit} aria-labelledby="invitation-title" className="w-full max-w-md space-y-4 rounded-2xl border border-border-subtle bg-surface-container-lowest p-8 shadow-sm"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">NOTEMELD CLOUD</p><h1 id="invitation-title" className="mt-2 text-2xl font-semibold text-on-surface">接受邀请</h1><p className="mt-2 text-sm text-on-surface-variant">设置你的显示名称和登录密码，完成 Cloud 账号注册。</p></div><label className="block text-sm text-on-surface">显示名称<input required minLength={1} maxLength={128} value={displayName} onChange={event => setDisplayName(event.target.value)} className="mt-1 block w-full rounded-lg border border-border-subtle bg-surface px-3 py-2" /></label><label className="block text-sm text-on-surface">密码<input required minLength={8} type="password" autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} className="mt-1 block w-full rounded-lg border border-border-subtle bg-surface px-3 py-2" /></label><label className="block text-sm text-on-surface">确认密码<input required minLength={8} type="password" autoComplete="new-password" value={confirm} onChange={event => setConfirm(event.target.value)} className="mt-1 block w-full rounded-lg border border-border-subtle bg-surface px-3 py-2" /></label>{error && <p role="alert" className="text-sm text-error">{error}</p>}<button type="submit" disabled={busy} className="w-full rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60">{busy ? '提交中…' : '完成注册'}</button></form></main>
}
