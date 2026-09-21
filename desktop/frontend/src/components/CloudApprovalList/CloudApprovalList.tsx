import { useEffect, useState } from 'react'
import CloudClient from '../../services/cloud'
import { useCloudLocale } from '../../pages/CloudPage/cloudLocale'

type Approval = { id: string; tool_name?: string; status: string; created_at?: number; arguments?: Record<string, unknown> }

export function CloudApprovalList({ client, sessionId }: { client: CloudClient; sessionId: string }) {
  const { t } = useCloudLocale()
  const [items, setItems] = useState<Approval[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  async function refresh() {
    try {
      setItems(await client.listApprovals(sessionId) as Approval[])
      setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('approvals.read-failed', '无法读取审批列表'))
    }
  }
  useEffect(() => { void refresh() }, [sessionId])
  async function resolve(item: Approval, status: 'approved' | 'rejected') {
    setBusy(item.id)
    setError(null)
    try {
      await client.resolveApproval(sessionId, item.id, status)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('approvals.resolve-failed', '审批处理失败'))
    } finally {
      setBusy(null)
    }
  }
  if (error && !items.length) return <section role="alert" className="p-3 text-sm text-[var(--error)]">{error}</section>
  const pending = items.filter(item => item.status === 'pending')
  if (!pending.length) return <section role="status" aria-label={t('approvals.title', '审批')} className="p-4 text-sm text-[var(--on-surface-variant)]">{t('approvals.empty', '暂无待处理审批。')}</section>
  return <section aria-labelledby="approval-title" className="space-y-2 p-3"><h2 id="approval-title" className="text-base font-semibold text-[var(--on-surface)]">{t('approvals.required', '需要审批')}</h2><ul role="list" className="space-y-2">{pending.map(item => <li key={item.id} className="rounded border border-amber-300/60 bg-amber-500/10 p-3"><p className="text-sm font-medium text-[var(--on-surface)]">{item.tool_name || t('approvals.protected-action', '受保护操作')}</p><p className="mt-1 truncate text-xs text-[var(--on-surface-variant)]">{t('approvals.host-confirmation', '请在主机确认后再允许此操作。')}</p><div className="mt-3 flex gap-2"><button type="button" disabled={busy === item.id} onClick={() => void resolve(item, 'approved')} className="rounded bg-[var(--primary)] px-3 py-1.5 text-xs text-white disabled:opacity-50">{t('approvals.approve', '批准')}</button><button type="button" disabled={busy === item.id} onClick={() => void resolve(item, 'rejected')} className="rounded border border-[var(--border-subtle)] px-3 py-1.5 text-xs text-[var(--on-surface)]">{t('approvals.reject', '拒绝')}</button></div></li>)}</ul>{error ? <p role="alert" className="text-sm text-[var(--error)]">{error}</p> : null}</section>
}
