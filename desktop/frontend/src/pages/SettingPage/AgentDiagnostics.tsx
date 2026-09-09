import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useBackendInitContext } from '@/contexts/BackendInitContext'
import { getAgentTurnDiagnostics, listAgentSessions } from '@/services/agent'

type Turn = { turn_id?: string; status?: string; updated_at?: string }

export default function AgentDiagnostics() {
  const { backendReady } = useBackendInitContext()
  const [turns, setTurns] = useState<Turn[]>([])
  useEffect(() => {
    if (!backendReady) return
    void listAgentSessions().then(response => {
      const sessions = response.data || []
      return Promise.all(sessions.map(session => fetch(`/api/agent/v1/sessions/${encodeURIComponent(session.id)}`).then(item => item.json())))
    }).then(values => setTurns(values.flatMap(value => Array.isArray(value?.data?.turns) ? value.data.turns : []))).catch(() => setTurns([]))
  }, [backendReady])
  return <div className="flex h-full flex-col gap-4 overflow-y-auto p-5 md:p-8">
    <div><h1 className="text-xl font-semibold text-on-surface">Agent 任务诊断</h1><p className="mt-1 text-sm text-on-surface-variant">查看 Host 持久化的 Turn 状态、事件数量和最后序号。</p></div>
    {!backendReady && <div role="status" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">后端尚未 ready，诊断请求已暂停。</div>}
    {turns.length === 0 && backendReady && <Card><CardContent className="p-5 text-sm text-on-surface-variant">暂无 Agent 任务。</CardContent></Card>}
    {turns.map(turn => <DiagnosticCard key={turn.turn_id} turn={turn} />)}
  </div>
}

function DiagnosticCard({ turn }: { turn: Turn }) {
  const [diagnostic, setDiagnostic] = useState<{ event_count: number; last_sequence: number }>()
  useEffect(() => { if (turn.turn_id) void getAgentTurnDiagnostics(turn.turn_id).then(value => setDiagnostic(value.data)).catch(() => undefined) }, [turn.turn_id])
  return <Card><CardHeader><CardTitle className="flex justify-between text-sm"><span className="font-mono">{turn.turn_id}</span><span>{turn.status}</span></CardTitle></CardHeader><CardContent className="text-xs text-on-surface-variant">事件 {diagnostic?.event_count ?? '…'} · 最后序号 {diagnostic?.last_sequence ?? '…'}<br />更新时间 {turn.updated_at || '未知'}</CardContent></Card>
}
