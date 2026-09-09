import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, FileText, Import, RefreshCw, Search, Workflow } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { listNoteLibrary, readNoteByTitle, type NoteLibraryItem, type NoteReadResult } from '@/services/note'
import { importConversationMarkdown } from '@/services/conversation'
import { cancelWikiExtraction, getWikiArticleDetail, getWikiExtractionStatus, getWikiGraph, retryWikiExtraction, type WikiArticleDetail, type WikiGraph } from '@/services/wiki'
import StylesPage from '@/pages/StylesPage'

type NotesTab = 'library' | 'styles' | 'wiki'
const PAGE_SIZE = 50

export default function NotesApp() {
  const [query, setQuery] = useState('')
  const [items, setItems] = useState<NoteLibraryItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<NotesTab>('library')
  const [wiki, setWiki] = useState<WikiGraph | null>(null)
  const [wikiLoading, setWikiLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [selectedNote, setSelectedNote] = useState<NoteReadResult | null>(null)
  const [selectedArticle, setSelectedArticle] = useState<WikiArticleDetail | null>(null)
  const [opening, setOpening] = useState(false)
  const [wikiBusyTask, setWikiBusyTask] = useState<string | null>(null)
  const libraryRequest = useRef<AbortController | null>(null)

  const load = useCallback(async () => {
    libraryRequest.current?.abort()
    const controller = new AbortController()
    libraryRequest.current = controller
    setLoading(true)
    setError('')
    try {
      const page = await listNoteLibrary({ q: query, offset, limit: PAGE_SIZE, signal: controller.signal })
      setItems(page.items)
      setTotal(page.pagination.total)
    } catch (cause: unknown) {
      const error = cause as { code?: string; name?: string }
      if (error.code !== 'ERR_CANCELED' && error.name !== 'CanceledError') setError('笔记库读取失败，请确认本地 Agent 已连接。')
    } finally {
      setLoading(false)
    }
  }, [offset, query])

  useEffect(() => { void load(); return () => libraryRequest.current?.abort() }, [load])

  useEffect(() => {
    if (tab !== 'wiki' || wiki) return
    setWikiLoading(true)
    void getWikiGraph().then(setWiki).catch(() => setError('Wiki 图谱读取失败。')).finally(() => setWikiLoading(false))
  }, [tab, wiki])

  useEffect(() => {
    const active = items.filter(item => ['pending', 'running'].includes(item.wikiStatus || '')).map(item => item.taskId)
    if (!active.length) return
    const timer = window.setInterval(() => {
      void Promise.all(active.map(async taskId => ({ taskId, status: await getWikiExtractionStatus(taskId) }))).then(rows => {
        setItems(current => current.map(item => {
          const row = rows.find(value => value.taskId === item.taskId)
          const status = row?.status.status
          return row && typeof status === 'string' ? { ...item, wikiStatus: status } : item
        }))
      }).catch(() => undefined)
    }, 1500)
    return () => window.clearInterval(timer)
  }, [items])

  const importMarkdown = async (file: File | undefined) => {
    if (!file) return
    setImporting(true); setError('')
    try {
      const content = await file.text()
      await importConversationMarkdown({ import_mode: 'note', title: file.name.replace(/\.md$/i, ''), content, format: 'markdown', file_name: file.name, source_type: 'markdown' })
      await load()
    } catch { setError('Markdown 导入失败，请检查文件格式或后端状态。') } finally { setImporting(false) }
  }

  const openNote = async (title: string) => {
    if (!title) return
    setOpening(true); setError('')
    try { setSelectedNote(await readNoteByTitle(title)) } catch { setError('笔记详情读取失败。') } finally { setOpening(false) }
  }

  const openArticle = async (sourceId: string) => {
    setOpening(true); setError('')
    try { setSelectedArticle(await getWikiArticleDetail(sourceId)) } catch { setError('Wiki 文章详情读取失败。') } finally { setOpening(false) }
  }

  const rebuildWiki = async (taskId: string) => {
    setOpening(true); setWikiBusyTask(taskId); setError('')
    try { await retryWikiExtraction(taskId); await load() } catch { setError('Wiki 重建任务提交失败。') } finally { setOpening(false); setWikiBusyTask(null) }
  }

  const cancelWiki = async (taskId: string) => {
    setWikiBusyTask(taskId); setError('')
    try { await cancelWikiExtraction(taskId); setItems(current => current.map(item => item.taskId === taskId ? { ...item, wikiStatus: 'canceled' } : item)) } catch { setError('Wiki 任务取消失败。') } finally { setWikiBusyTask(null) }
  }

  return <div className="h-full overflow-auto bg-surface px-5 py-6 md:px-8"><div className="mx-auto max-w-5xl">
    <div className="flex flex-wrap items-start justify-between gap-4"><div className="flex items-start gap-3"><Link to="/apps" aria-label="返回应用" className="mt-1 rounded-lg p-2 text-on-surface-variant hover:bg-surface-container"><ArrowLeft className="h-4 w-4" /></Link><div><div className="text-[11px] font-medium tracking-[0.16em] text-on-surface-variant">NOTE LIBRARY</div><h1 className="mt-1 font-display text-2xl font-bold text-on-surface">笔记应用</h1><p className="mt-2 text-sm text-on-surface-variant">从真实笔记文档和 Wiki 状态开始管理知识产物。</p></div></div><div className="flex gap-2"><label className="inline-flex cursor-pointer items-center rounded-lg border border-border-subtle px-3 py-2 text-sm text-on-surface-variant hover:bg-surface-container"><Import className="mr-2 h-4 w-4" />{importing ? '导入中…' : '导入 Markdown'}<input type="file" accept=".md,text/markdown" className="hidden" disabled={importing} onChange={event => { void importMarkdown(event.target.files?.[0]); event.currentTarget.value = '' }} /></label><Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}><RefreshCw className={loading ? 'mr-2 h-4 w-4 animate-spin' : 'mr-2 h-4 w-4'} />刷新</Button></div></div>
    <div className="mt-6 flex flex-wrap gap-2"><button type="button" onClick={() => setTab('library')} className={tab === 'library' ? 'rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground' : 'rounded-lg px-3 py-2 text-sm text-on-surface-variant hover:bg-surface-container'}>笔记列表</button><button type="button" onClick={() => setTab('styles')} className={tab === 'styles' ? 'rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground' : 'rounded-lg px-3 py-2 text-sm text-on-surface-variant hover:bg-surface-container'}>样式与模板</button><button type="button" onClick={() => setTab('wiki')} className={tab === 'wiki' ? 'rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground' : 'rounded-lg px-3 py-2 text-sm text-on-surface-variant hover:bg-surface-container'}>Wiki 知识图谱</button><Link to="/new" className="rounded-lg px-3 py-2 text-sm text-on-surface-variant hover:bg-surface-container">新建笔记</Link></div>
    {tab === 'library' && <>{error && <div role="alert" className="mt-5 rounded-xl border border-error/30 bg-error/5 px-4 py-3 text-sm text-error">{error}</div>}<Card className="mt-6"><CardContent className="flex items-center gap-3 pt-6"><Search className="h-4 w-4 text-on-surface-variant" /><Input value={query} onChange={event => { setQuery(event.target.value); setOffset(0) }} onKeyDown={event => { if (event.key === 'Enter') void load() }} placeholder="搜索笔记标题" aria-label="搜索笔记标题" /><span className="shrink-0 text-sm text-on-surface-variant">{total} 篇</span></CardContent></Card><Card className="mt-4"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><FileText className="h-4 w-4 text-primary" />最近笔记</CardTitle></CardHeader><CardContent>{loading ? <div className="py-10 text-center text-sm text-on-surface-variant">正在读取笔记库…</div> : items.length === 0 ? <div className="py-10 text-center text-sm text-on-surface-variant">还没有符合条件的笔记。</div> : <div className="divide-y divide-border-subtle">{items.map(item => <article key={item.taskId} className="flex flex-wrap items-center justify-between gap-3 py-4 first:pt-0 last:pb-0"><button type="button" className="min-w-0 text-left" onClick={() => void openNote(item.title)} disabled={opening} title={item.title || '未命名笔记'}><h2 className="truncate font-medium text-on-surface hover:text-primary">{item.title || '未命名笔记'}</h2><p className="mt-1 text-xs text-on-surface-variant">{item.platform || '本地来源'} · {item.style || '默认样式'} · Wiki {item.wikiStatus || 'pending'}</p></button><div className="flex items-center gap-2"><span className="rounded-full bg-surface-container px-2.5 py-1 text-xs text-on-surface-variant">{item.status || 'unknown'}</span>{item.wikiStatus === 'running' ? <Button size="sm" variant="ghost" onClick={() => void cancelWiki(item.taskId)} disabled={wikiBusyTask === item.taskId}>取消 Wiki</Button> : ['failed', 'pending', 'canceled'].includes(item.wikiStatus || '') && <Button size="sm" variant="ghost" onClick={() => void rebuildWiki(item.taskId)} disabled={wikiBusyTask === item.taskId}>重建 Wiki</Button>}</div></article>)}</div>}</CardContent></Card>{total > PAGE_SIZE && <div className="mt-4 flex items-center justify-between rounded-xl border border-border-subtle px-4 py-3 text-sm"><span className="text-on-surface-variant">第 {Math.floor(offset / PAGE_SIZE) + 1} / {Math.max(1, Math.ceil(total / PAGE_SIZE))} 页</span><div className="flex gap-2"><Button size="sm" variant="outline" disabled={offset === 0 || loading} onClick={() => setOffset(current => Math.max(0, current - PAGE_SIZE))}>上一页</Button><Button size="sm" variant="outline" disabled={offset + PAGE_SIZE >= total || loading} onClick={() => setOffset(current => current + PAGE_SIZE)}>下一页</Button></div></div>}<div className="mt-4 flex items-center gap-2 text-xs text-on-surface-variant"><Workflow className="h-3.5 w-3.5" />笔记列表来自本地 `note_documents`，页面不维护第二份数据。</div></>}
    {tab === 'styles' && <div className="mt-4 min-h-[620px] overflow-hidden rounded-2xl border border-border-subtle bg-surface-container-low"><StylesPage /></div>}
    {tab === 'wiki' && <Card className="mt-4"><CardHeader><CardTitle className="text-base">Wiki 知识图谱</CardTitle></CardHeader><CardContent>{wikiLoading ? <div className="py-10 text-sm text-on-surface-variant">正在读取图谱…</div> : !wiki || wiki.nodes.length === 0 ? <div className="py-10 text-sm text-on-surface-variant">当前没有可展示的 Wiki 节点。</div> : <><div className="grid gap-3 sm:grid-cols-3"><div className="rounded-xl bg-surface-container-low p-3"><div className="text-xs text-on-surface-variant">节点</div><div className="mt-1 text-xl font-semibold">{wiki.nodes.length}</div></div><div className="rounded-xl bg-surface-container-low p-3"><div className="text-xs text-on-surface-variant">关系</div><div className="mt-1 text-xl font-semibold">{wiki.edges.length}</div></div><div className="rounded-xl bg-surface-container-low p-3"><div className="text-xs text-on-surface-variant">社区</div><div className="mt-1 text-xl font-semibold">{wiki.clusters.length}</div></div></div><div className="mt-5 grid gap-2 sm:grid-cols-2">{wiki.nodes.slice(0, 20).map(node => <button type="button" key={node.id} onClick={() => void openArticle(node.id)} className="rounded-xl border border-border-subtle p-3 text-left hover:border-primary/40"><div className="font-medium text-on-surface">{node.label}</div><div className="mt-1 text-xs text-on-surface-variant">{node.type} · {node.community_label || '未分类'}</div></button>)}</div></>}</CardContent></Card>}
    {selectedNote && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true" aria-labelledby="note-detail-title"><Card className="max-h-[85vh] w-full max-w-3xl overflow-auto"><CardHeader className="flex flex-row items-center justify-between"><CardTitle id="note-detail-title">{selectedNote.title}</CardTitle><Button variant="ghost" onClick={() => setSelectedNote(null)} aria-label="关闭笔记详情">关闭</Button></CardHeader><CardContent><pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-on-surface">{selectedNote.content}</pre></CardContent></Card></div>}
    {selectedArticle && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true" aria-labelledby="wiki-article-title"><Card className="max-h-[85vh] w-full max-w-3xl overflow-auto"><CardHeader className="flex flex-row items-center justify-between"><CardTitle id="wiki-article-title">{selectedArticle.title}</CardTitle><Button variant="ghost" onClick={() => setSelectedArticle(null)} aria-label="关闭 Wiki 文章">关闭</Button></CardHeader><CardContent><p className="mb-4 text-sm text-on-surface-variant">{selectedArticle.summary || '暂无摘要'} · {selectedArticle.relations.length} 条关系 · {selectedArticle.evidence.length} 条证据</p><pre className="whitespace-pre-wrap font-sans text-sm leading-7 text-on-surface">{selectedArticle.markdown || selectedArticle.claims.map(claim => claim.claim).join('\n')}</pre></CardContent></Card></div>}
  </div></div>
}
