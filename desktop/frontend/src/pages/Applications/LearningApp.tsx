import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, BookOpen, CheckCircle2, Network, Play, RefreshCw, Send, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { useTaskStore } from '@/store/taskStore'
import { createLearningCanvas, listDueLearningReviews, listLearningCanvases, seedLearningCanvasWhiteboard, startLearningUnit, submitLearningEvidence, type AggregatedReviewItem, type LearningCanvas } from '@/services/learning'
import { getWhiteboard, mutateWhiteboard, publishWhiteboard, type WhiteboardSnapshot } from '@/services/whiteboard'

type LearningTab = 'spaces' | 'canvas' | 'mastery' | 'review'

export default function LearningApp() {
  const tasks = useTaskStore(state => state.tasks)
  const createConversation = useTaskStore(state => state.createConversation)
  const conversation = tasks[0]
  const [tab, setTab] = useState<LearningTab>('spaces')
  const [goal, setGoal] = useState('理解 Agent Runtime 的事件、工具调度和审批状态机')
  const [canvas, setCanvas] = useState<LearningCanvas | null>(null)
  const [spaces, setSpaces] = useState<LearningCanvas[]>([])
  const [allDueReviews, setAllDueReviews] = useState<AggregatedReviewItem[]>([])
  const [activeNode, setActiveNode] = useState<string | null>(null)
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [whiteboard, setWhiteboard] = useState<WhiteboardSnapshot | null>(null)
  const conversationId = conversation?.id ?? ''
  const activeConversationId = canvas?.conversation_id ?? conversationId
  const dueReviews = useMemo(() => canvas?.review_queue.filter(item => new Date(item.next_review_at).getTime() <= Date.now()) ?? [], [canvas])

  const refreshReviews = () => { void listDueLearningReviews().then(setAllDueReviews).catch(() => setAllDueReviews([])) }
  useEffect(() => { void listLearningCanvases().then(setSpaces).catch(() => setSpaces([])); refreshReviews() }, [])

  const createSpace = async () => {
    setBusy(true); setMessage('')
    try {
      const id = conversationId || createConversation({ mode: 'chat', title: '学习空间' })
      const result = await createLearningCanvas(id, { goal, external_limit: 5 })
      setCanvas(result); setSpaces(current => [result, ...current.filter(item => item.canvas_id !== result.canvas_id)]); setTab('canvas'); setMessage('学习空间已创建，下一步可以开始第一个学习单元。')
    } catch { setMessage('学习空间创建失败，请先确认模型和本地 Agent 已连接。') } finally { setBusy(false) }
  }

  const startUnit = async (nodeId: string) => {
    if (!canvas || !activeConversationId) return
    setBusy(true); setActiveNode(nodeId); setMessage('正在准备掌握验证…')
    try { const result = await startLearningUnit(activeConversationId, canvas.canvas_id, nodeId); setCanvas(result.canvas); setMessage(result.unit.recall_question) } catch { setMessage('学习单元启动失败。') } finally { setBusy(false) }
  }

  const submitEvidence = async () => {
    if (!canvas || !activeConversationId || !activeNode || !answer.trim()) return
    setBusy(true)
    try { const result = await submitLearningEvidence(activeConversationId, canvas.canvas_id, activeNode, { kind: 'explain', answer, rubric_result: { source: 'user-submission' } }); setCanvas(result.canvas); setAnswer(''); refreshReviews(); setMessage('证据已提交，掌握状态由后端重新计算。') } catch { setMessage('证据提交失败，请重试。') } finally { setBusy(false) }
  }

  const openWhiteboard = async () => {
    if (!canvas || !activeConversationId) return
    setBusy(true)
    try { const result = await seedLearningCanvasWhiteboard(activeConversationId, canvas.canvas_id); setWhiteboard(result); setMessage('语义白板已从当前学习画布生成，可继续编辑卡片和关系。') } catch { setMessage('白板生成失败。') } finally { setBusy(false) }
  }

  const saveWhiteboardCard = async (cardId: string, description: string) => {
    if (!whiteboard) return
    try {
      const result = await mutateWhiteboard(whiteboard.conversation_id, whiteboard.id, { base_revision: whiteboard.revision, operations: [{ op: 'card.update', card_id: cardId, patch: { description } }] })
      setWhiteboard(current => current ? { ...current, revision: result.revision, cards: result.cards, relations: result.relations } : current)
      setMessage('白板卡片已保存。')
    } catch {
      try {
        const fresh = await getWhiteboard(whiteboard.conversation_id, whiteboard.id)
        setWhiteboard(fresh)
        setMessage('白板版本已更新，已重新加载最新内容；请确认后再次保存。')
      } catch { setMessage('白板保存失败，且无法重新读取最新版本。') }
    }
  }

  const publishNote = async () => {
    if (!whiteboard) return
    setBusy(true)
    try { const result = await publishWhiteboard(whiteboard.conversation_id, whiteboard.id, { base_revision: whiteboard.revision, scope: 'all', card_ids: whiteboard.cards.map(card => card.id), relation_ids: whiteboard.relations.map(relation => relation.id) }); setMessage(result.message || '白板已发布为笔记。') } catch { setMessage('发布笔记失败。') } finally { setBusy(false) }
  }

  return <div className="h-full overflow-auto bg-surface px-5 py-6 md:px-8"><div className="mx-auto max-w-5xl">
    <div className="flex flex-wrap items-start justify-between gap-4"><div className="flex items-start gap-3"><Link to="/apps" aria-label="返回应用" className="mt-1 rounded-lg p-2 text-on-surface-variant hover:bg-surface-container"><ArrowLeft className="h-4 w-4" /></Link><div><div className="text-[11px] font-medium tracking-[0.16em] text-on-surface-variant">LEARNING SPACES</div><h1 className="mt-1 font-display text-2xl font-bold text-on-surface">学习应用</h1><p className="mt-2 text-sm text-on-surface-variant">学习空间、掌握验证、复习和语义白板共用同一份后端状态。</p></div></div><Button variant="outline" size="sm" onClick={() => setTab('spaces')}><RefreshCw className="mr-2 h-4 w-4" />学习空间</Button></div>
    <div className="mt-6 flex flex-wrap gap-2">{([['spaces', '学习空间'], ['canvas', '学习画布'], ['mastery', '掌握验证'], ['review', '复习']] as const).map(([value, label]) => <button key={value} type="button" onClick={() => setTab(value)} className={tab === value ? 'rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground' : 'rounded-lg px-3 py-2 text-sm text-on-surface-variant hover:bg-surface-container'}>{label}</button>)}</div>
    {message && <div className="mt-4 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-on-surface">{message}</div>}
    {tab === 'spaces' && <><Card className="mt-6"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><Sparkles className="h-4 w-4 text-primary" />创建学习空间</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-sm text-on-surface-variant">学习空间会生成可验证的节点和复习队列；模型、来源和掌握状态由后端保存。</p><Input value={goal} onChange={event => setGoal(event.target.value)} placeholder="你想掌握什么？" aria-label="学习目标" /><Button onClick={() => void createSpace()} disabled={busy || !goal.trim()}>{busy ? '创建中…' : '创建并开始学习'}</Button>{conversation && <div className="text-xs text-on-surface-variant">当前会话：{conversation.title || conversation.id}</div>}</CardContent></Card><Card className="mt-4"><CardHeader><CardTitle className="text-base">已有学习空间</CardTitle></CardHeader><CardContent>{spaces.length ? <div className="divide-y divide-border-subtle">{spaces.map(item => <button key={item.canvas_id} type="button" className="flex w-full items-center justify-between gap-4 py-3 text-left hover:bg-surface-container-low" onClick={() => { setCanvas(item); setTab('canvas') }}><span className="min-w-0"><span className="block truncate font-medium text-on-surface">{item.goal}</span><span className="mt-1 block text-xs text-on-surface-variant">{item.nodes.length} 个节点 · {item.status} · {item.canvas_id}</span></span><span className="text-xs text-primary">打开</span></button>)}</div> : <p className="text-sm text-on-surface-variant">还没有持久化学习空间。</p>}</CardContent></Card></>}
    {tab === 'canvas' && <Card className="mt-6"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><Network className="h-4 w-4 text-primary" />学习画布</CardTitle></CardHeader><CardContent>{!canvas ? <div className="py-8 text-sm text-on-surface-variant">还没有加载学习空间，请先创建一个。</div> : <><div className="grid gap-3 sm:grid-cols-3"><div className="rounded-xl bg-surface-container-low p-3"><div className="text-xs text-on-surface-variant">学习节点</div><div className="mt-1 text-xl font-semibold">{canvas.nodes.length}</div></div><div className="rounded-xl bg-surface-container-low p-3"><div className="text-xs text-on-surface-variant">关系</div><div className="mt-1 text-xl font-semibold">{canvas.edges.length}</div></div><div className="rounded-xl bg-surface-container-low p-3"><div className="text-xs text-on-surface-variant">待复习</div><div className="mt-1 text-xl font-semibold">{dueReviews.length}</div></div></div><div className="mt-5 divide-y divide-border-subtle">{canvas.nodes.map(node => <div key={node.id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0"><div><div className="font-medium text-on-surface">{node.user_label || node.label}</div><div className="mt-1 text-xs text-on-surface-variant">{node.mastery} · {node.summary}</div></div><Button size="sm" variant="outline" onClick={() => void startUnit(node.id)} disabled={busy}><Play className="mr-1.5 h-3.5 w-3.5" />验证</Button></div>)}</div><Button className="mt-4" variant="outline" onClick={() => void openWhiteboard()} disabled={busy}><Network className="mr-2 h-4 w-4" />生成语义白板</Button>{whiteboard && <div className="mt-6 rounded-2xl border border-border-subtle bg-surface-container-low p-4"><div className="flex items-center justify-between gap-3"><div><div className="font-medium text-on-surface">{whiteboard.title}</div><div className="text-xs text-on-surface-variant">修订 {whiteboard.revision} · {whiteboard.cards.length} 张卡片 · {whiteboard.relations.length} 条关系</div></div><Button size="sm" onClick={() => void publishNote()} disabled={busy}>发布为笔记</Button></div><div className="mt-4 space-y-3">{whiteboard.cards.map(card => <div key={card.id} className="rounded-xl border border-border-subtle bg-surface p-3"><div className="mb-2 text-sm font-medium text-on-surface">{card.title}</div><Textarea defaultValue={card.description} onBlur={event => { if (event.target.value !== card.description) void saveWhiteboardCard(card.id, event.target.value) }} placeholder="编辑卡片内容" /></div>)}</div></div>}</>}</CardContent></Card>}
    {tab === 'mastery' && <Card className="mt-6"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><CheckCircle2 className="h-4 w-4 text-primary" />掌握验证</CardTitle></CardHeader><CardContent>{!canvas || !activeNode ? <div className="py-8 text-sm text-on-surface-variant">先在学习画布中选择一个节点开始验证。</div> : <div className="space-y-4"><div className="rounded-xl bg-surface-container-low p-4 text-sm text-on-surface-variant">当前节点：{canvas.nodes.find(node => node.id === activeNode)?.label || activeNode}<br />后端会根据回答和证据计算掌握状态。</div><Textarea value={answer} onChange={event => setAnswer(event.target.value)} placeholder="用自己的话解释这个概念，并给出一个应用场景。" aria-label="掌握验证回答" /><Button onClick={() => void submitEvidence()} disabled={busy || !answer.trim()}><Send className="mr-2 h-4 w-4" />提交证据</Button></div>}</CardContent></Card>}
    {tab === 'review' && <Card className="mt-6"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><BookOpen className="h-4 w-4 text-primary" />跨学习空间复习队列</CardTitle></CardHeader><CardContent>{allDueReviews.length === 0 ? <div className="py-8 text-sm text-on-surface-variant">当前没有到期复习项。</div> : <div className="divide-y divide-border-subtle">{allDueReviews.map(item => <div key={`${item.canvas_id}:${item.node_id}`} className="flex items-center justify-between gap-3 py-3"><span className="min-w-0 text-sm text-on-surface"><span className="block truncate">{item.node_label}</span><span className="mt-1 block truncate text-xs text-on-surface-variant">{item.goal} · {item.mastery}</span></span><Button size="sm" onClick={() => { const next = spaces.find(space => space.canvas_id === item.canvas_id); if (next) setCanvas(next); setActiveNode(item.node_id); setTab('mastery') }}>开始复习</Button></div>)}</div>}</CardContent></Card>}
  </div></div>
}
