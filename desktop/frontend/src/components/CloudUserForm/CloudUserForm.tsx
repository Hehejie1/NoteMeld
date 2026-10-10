import { useState } from 'react'
import CloudClient, { CloudUser } from '../../services/cloud'
import { useCloudLocale } from '../../pages/CloudPage/cloudLocale'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Checkbox } from '../ui/checkbox'

export function CloudUserForm({ client, user, onSaved }: { client: CloudClient; user?: CloudUser; onSaved?: () => void }) {
  const { t } = useCloudLocale()
  const [username, setUsername] = useState(user?.username ?? '')
  const [password, setPassword] = useState('')
  const [disabled, setDisabled] = useState(user?.disabled ?? false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [inviteLink, setInviteLink] = useState('')
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try {
      if (user) await client.updateUser(user.id, { username, ...(password ? { password } : {}), disabled })
      else { const created = await client.createUser(username, password); setInviteLink(`${window.location.origin}/cloud?invite=${encodeURIComponent(created.id)}`) }
      setPassword(''); onSaved?.()
    } catch (reason) { setError(reason instanceof Error ? reason.message : t('users.save-failed', '成员保存失败')) } finally { setBusy(false) }
  }
  const copyInvite = () => { if (inviteLink) void navigator.clipboard?.writeText(inviteLink) }
  return <form onSubmit={submit} aria-labelledby="user-form-title" className="flex max-w-md flex-col gap-3 p-3"><h2 id="user-form-title" className="text-base font-semibold">{user ? t('users.edit-title', '编辑成员') : t('users.invite-title', '邀请成员')}</h2><label htmlFor="cloud-user-name" className="text-sm font-medium">{t('users.username-email', '用户名或邮箱')}</label><Input id="cloud-user-name" required value={username} onValueChange={setUsername} className="rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2 text-[var(--on-surface)]" /><label htmlFor="cloud-user-password" className="text-sm font-medium">{user ? t('users.new-password', '新密码（选填）') : t('users.temporary-password', '临时密码')}</label><Input id="cloud-user-password" type="password" autoComplete="new-password" required={!user} value={password} onValueChange={setPassword} className="rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2 text-[var(--on-surface)]" />{user ? <label className="flex items-center gap-2 text-sm"><Checkbox checked={disabled} onCheckedChange={setDisabled} /> {t('users.disabled', '已停用')}</label> : null}<Button type="submit" variant="default" disabled={busy || !username || (!user && !password)} className="rounded bg-[var(--primary)] px-3 py-2 text-[var(--on-primary)] transition hover:brightness-110 disabled:opacity-50">{busy ? t('users.saving', '保存中…') : user ? t('users.save', '保存成员') : t('users.send-invite', '发送邀请')}</Button>{inviteLink && <div role="status" className="rounded border border-emerald-300/60 bg-emerald-950/20 p-3 text-xs"><p>{t('users.invite-created', '邀请已创建，可复制链接发送给目标用户。')}</p><div className="mt-2 flex gap-2"><code className="min-w-0 flex-1 break-all">{inviteLink}</code><Button type="button" variant="link" onClick={copyInvite} className="shrink-0 underline">{t('users.copy', '复制')}</Button></div></div>}{error ? <p role="alert" className="text-sm text-[var(--error)]">{error}</p> : null}</form>
}
