import { useCallback, useEffect, useState } from 'react'
import {
  listPendingAgentApprovals,
  resolveAgentApproval,
  type PendingAgentApproval,
} from '@/services/agent'
import { Button } from '@notemeld/ui-web'

interface Props {
  backendReady: boolean
  visible: boolean
  onCountChange: (count: number) => void
}

const formatDeadline = (deadline: string | null) => {
  if (!deadline) return '等待 Host 决策'
  const parsed = new Date(deadline)
  return Number.isNaN(parsed.getTime()) ? `截止 ${deadline}` : `截止 ${parsed.toLocaleString()}`
}

export default function HostApprovalInbox({ backendReady, visible, onCountChange }: Props) {
  const [approvals, setApprovals] = useState<PendingAgentApproval[]>([])
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')

  const refresh = useCallback(async () => {
    if (!backendReady) {
      setApprovals([])
      setError('')
      onCountChange(0)
      return
    }
    try {
      const response = await listPendingAgentApprovals()
      setApprovals(response.data)
      setError('')
      onCountChange(response.data.length)
    } catch {
      setError('暂时无法读取待审批请求')
    }
  }, [backendReady, onCountChange])

  useEffect(() => {
    void refresh()
    if (!backendReady) return undefined
    const interval = window.setInterval(() => void refresh(), 2_000)
    return () => window.clearInterval(interval)
  }, [backendReady, refresh])

  const decide = async (approvalId: string, decision: 'approve' | 'deny') => {
    setBusyId(approvalId)
    setError('')
    try {
      await resolveAgentApproval(approvalId, decision)
      await refresh()
    } catch {
      await refresh()
      setError('审批未能提交；请求可能已超时或被其他窗口处理')
    } finally {
      setBusyId('')
    }
  }

  if (!visible) return null

  return <div className="nm-notice-popover" role="region" aria-label="notemeld-host-approval-inbox">
    <div className="nm-approval-heading"><strong>Host 审批</strong><span aria-label={`notemeld-host-approval-count:${approvals.length}`}>{approvals.length}</span></div>
    {!backendReady ? <p>本地 Agent 连接后可处理审批。</p> : error ? <p role="alert">{error}</p> : approvals.length === 0 ? <p>当前没有待审批操作。</p> : <ol className="nm-approval-list">{approvals.map(approval => <li key={approval.approval_id} aria-label={`notemeld-host-approval:${approval.approval_id}`}>
      <strong>{approval.session_title}</strong>
      <p>{approval.summary || 'Agent 请求执行受保护操作'}</p>
      <small>{approval.risk ? `风险：${approval.risk} · ` : ''}{formatDeadline(approval.deadline)}</small>
      <div>
        <Button type="button" variant="secondary" disabled={busyId === approval.approval_id} onClick={() => void decide(approval.approval_id, 'deny')} aria-label={`notemeld-host-approval-deny:${approval.approval_id}`}>拒绝</Button>
        <Button type="button" variant="default" disabled={busyId === approval.approval_id} onClick={() => void decide(approval.approval_id, 'approve')} aria-label={`notemeld-host-approval-approve:${approval.approval_id}`}>批准</Button>
      </div>
    </li>)}</ol>}
  </div>
}
