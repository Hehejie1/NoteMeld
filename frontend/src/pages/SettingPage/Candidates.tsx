import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { approveCandidate, declineCandidate, listCandidates, validateCandidate, type Candidate } from '@/services/candidates'

export default function Candidates() {
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const refresh = async () => setCandidates((await listCandidates()).candidates)
  useEffect(() => { void refresh() }, [])
  const run = async (id: string, action: () => Promise<unknown>) => { setBusy(id); try { await action(); await refresh() } finally { setBusy(null) } }
  return <div className="flex h-full flex-col gap-5 overflow-y-auto p-5 md:p-8">
    <div><h1 className="text-xl font-semibold text-on-surface">Application / plugin candidate</h1><p className="mt-1 text-sm text-on-surface-variant">只展示、验证和人工审批；N06 不会 patch 或激活 Application。</p></div>
    <div className="grid gap-4">{candidates.map(candidate => <Card key={candidate.id}><CardHeader><CardTitle className="flex items-center justify-between"><span>{candidate.title}</span><span className="text-sm font-normal">{candidate.kind} · {candidate.status}</span></CardTitle></CardHeader><CardContent className="space-y-3"><p className="text-sm text-on-surface-variant">{candidate.next_step}</p><div className="grid gap-1 text-xs text-on-surface-variant"><span>scope：{JSON.stringify(candidate.scope)}</span><span>evidence / trace / tests / risks：{candidate.evidence.length} / {candidate.trace.length} / {candidate.tests.length} / {candidate.risks.length}</span><span>permissions：{candidate.permissions.join(', ') || '无'}；rollback：{Object.keys(candidate.rollback).length ? '已保存' : '缺失'}</span></div>{candidate.model_safety_claim ? <p className="text-xs text-amber-700">模型安全声明仅供诊断，不计入审批门禁。</p> : null}{candidate.validation.errors?.length ? <ul className="list-disc pl-5 text-sm text-red-600">{candidate.validation.errors.map(error => <li key={error}>{error}</li>)}</ul> : null}<div className="flex gap-2"><Button disabled={busy === candidate.id} variant="outline" onClick={() => void run(candidate.id, () => validateCandidate(candidate.id))}>重新验证</Button><Button disabled={busy === candidate.id || candidate.status !== 'approvable'} onClick={() => void run(candidate.id, () => approveCandidate(candidate.id))}>审批</Button><Button disabled={busy === candidate.id || candidate.status === 'declined'} variant="destructive" onClick={() => void run(candidate.id, () => declineCandidate(candidate.id))}>拒绝</Button></div></CardContent></Card>)}</div>
    {!candidates.length && <p className="text-sm text-on-surface-variant">暂无 candidate。</p>}
  </div>
}
