import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Maximize2, Minus, Plus, RefreshCw, X } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { toast } from 'react-hot-toast'

import KnowledgeEmptyState from '@/components/KnowledgeEmptyState'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { FeatureGuideTarget } from '@/demo/FeatureGuideTarget'
import {
  invokeApplicationCapability,
  type WikiArticleDetail,
  type WikiGraph,
  type WikiGraphNode,
} from '@/services/applications'
import { useBackendInitContext } from '@/contexts/BackendInitContext'
import SigmaWikiGraph, { type SigmaWikiGraphHandle } from '@/pages/WikiPage/graph/SigmaWikiGraph'
import {
  NODE_META,
  communityDisplayIndex,
  communityDisplayName,
  nodeViewColor,
  normalizeType,
  type GraphViewMode,
  type NodeType,
} from '@/pages/WikiPage/graph/colors'

const emptyGraph: WikiGraph = { nodes: [], edges: [], clusters: [] }

interface DisplayNode extends WikiGraphNode {
  normalizedType: NodeType
  degree: number
}

interface WikiApplicationProps {
  applicationId: string
  runId: string
}

const buildDegreeMap = (graph: WikiGraph) => {
  const degreeMap = new Map<string, number>()
  graph.edges.forEach(edge => {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1)
    degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1)
  })
  return degreeMap
}

const WikiArticle = ({ article, onClose }: { article: WikiArticleDetail; onClose: () => void }) => (
  <aside className="absolute inset-y-3 right-3 z-20 flex w-[min(440px,calc(100%-24px))] flex-col overflow-hidden rounded-xl border border-border-subtle bg-white shadow-xl">
    <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border-subtle px-5 py-4">
      <div className="min-w-0">
        <div className="text-[11px] font-medium tracking-[0.14em] text-on-surface-variant">WIKI ARTICLE</div>
        <h2 className="mt-1 truncate font-display text-lg font-bold text-on-surface">{article.title}</h2>
      </div>
      <button
        type="button"
        onClick={onClose}
        className="rounded-md p-1 text-on-surface-variant hover:bg-surface-container hover:text-on-surface"
        aria-label="关闭文章详情"
      >
        <X className="h-4 w-4" />
      </button>
    </header>
    <ScrollArea className="min-h-0 flex-1">
      <div className="space-y-5 px-5 py-4 text-sm text-on-surface">
        {article.summary && <p className="leading-6 text-on-surface-variant">{article.summary}</p>}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <Stat label="实体" value={String(article.entities.length)} />
          <Stat label="概念" value={String(article.concepts.length)} />
          <Stat label="观点" value={String(article.claims.length)} />
          <Stat label="证据" value={String(article.evidence.length)} />
        </div>
        {article.markdown && (
          <article className="prose prose-sm max-w-none leading-6">
            <ReactMarkdown>{article.markdown}</ReactMarkdown>
          </article>
        )}
        {article.entities.length > 0 && (
          <ArticleList title="实体" items={article.entities.map(item => item.name)} />
        )}
        {article.concepts.length > 0 && (
          <ArticleList title="概念" items={article.concepts.map(item => item.name)} />
        )}
        {article.claims.length > 0 && (
          <ArticleList title="观点" items={article.claims.map(item => item.claim)} />
        )}
        {article.evidence.length > 0 && (
          <ArticleList title="证据" items={article.evidence.map(item => item.text)} />
        )}
        {article.relations.length > 0 && (
          <ArticleList
            title="关系"
            items={article.relations.map(item => `${item.source} · ${item.relation_type} · ${item.target}`)}
          />
        )}
      </div>
    </ScrollArea>
  </aside>
)

const ArticleList = ({ title, items }: { title: string; items: string[] }) => (
  <section>
    <h3 className="mb-2 text-xs font-semibold tracking-wide text-on-surface-variant">本篇{title}</h3>
    <ul className="space-y-1.5">
      {items.map((item, index) => (
        <li key={`${title}-${index}`} className="rounded-lg border border-border-subtle bg-surface-container/40 px-3 py-2 leading-5">
          {item}
        </li>
      ))}
    </ul>
  </section>
)

const Stat = ({ label, value }: { label: string; value: string }) => (
  <div className="min-w-0 rounded-lg border border-border-subtle bg-surface-container/50 px-3 py-2">
    <div className="truncate text-[10px] text-on-surface-variant">{label}</div>
    <div className="mt-0.5 font-display text-lg font-bold text-on-surface">{value}</div>
  </div>
)

const WikiApplication = ({ applicationId: _applicationId, runId }: WikiApplicationProps) => {
  const { backendReady } = useBackendInitContext()
  const [graph, setGraph] = useState<WikiGraph>(emptyGraph)
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [hoveredNodeId, setHoveredNodeId] = useState('')
  const [loading, setLoading] = useState(true)
  const [hasLoaded, setHasLoaded] = useState(false)
  const [error, setError] = useState('')
  const [viewMode, setViewMode] = useState<GraphViewMode>('type')
  const [article, setArticle] = useState<WikiArticleDetail | null>(null)
  const [articleLoading, setArticleLoading] = useState(false)
  const [articleError, setArticleError] = useState('')
  const graphHandleRef = useRef<SigmaWikiGraphHandle | null>(null)

  const loadWiki = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await invokeApplicationCapability<WikiGraph>(runId, 'wiki.read', 'graph')
      setGraph({ nodes: result.nodes || [], edges: result.edges || [], clusters: result.clusters || [] })
      setHasLoaded(true)
    } catch {
      setError('Wiki 图谱加载失败，请检查应用能力或稍后重试')
      toast.error('Wiki 图谱加载失败')
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    if (backendReady) void loadWiki()
  }, [backendReady, loadWiki])

  const degreeMap = useMemo(() => buildDegreeMap(graph), [graph])
  const nodeMap = useMemo(() => {
    const map = new Map<string, DisplayNode>()
    graph.nodes.forEach(node => {
      map.set(node.id, { ...node, normalizedType: normalizeType(node.type), degree: degreeMap.get(node.id) || 0 })
    })
    return map
  }, [degreeMap, graph.nodes])
  const selectedNode = selectedNodeId ? nodeMap.get(selectedNodeId) : undefined

  useEffect(() => {
    if (selectedNodeId && !nodeMap.has(selectedNodeId)) setSelectedNodeId('')
  }, [nodeMap, selectedNodeId])

  const communityLegend = useMemo(() => {
    const byId = new Map<number, { id: number; label: string; color: string; size: number }>()
    graph.nodes.forEach(node => {
      if (typeof node.community_id !== 'number') return
      const current = byId.get(node.community_id)
      byId.set(node.community_id, {
        id: node.community_id,
        label: communityDisplayName(node.community_label, node.community_id),
        color: node.community_color || '#64748b',
        size: (current?.size || 0) + 1,
      })
    })
    return Array.from(byId.values()).sort((left, right) => right.size - left.size)
  }, [graph.nodes])

  const neighborList = useMemo(() => {
    if (!selectedNodeId) return []
    const neighborIds = new Set<string>()
    graph.edges.forEach(edge => {
      if (edge.source === selectedNodeId) neighborIds.add(edge.target)
      if (edge.target === selectedNodeId) neighborIds.add(edge.source)
    })
    return Array.from(neighborIds)
      .map(id => nodeMap.get(id))
      .filter((node): node is DisplayNode => Boolean(node))
      .sort((left, right) => right.degree - left.degree)
  }, [graph.edges, nodeMap, selectedNodeId])

  const focusNode = (nodeId: string) => {
    setSelectedNodeId(nodeId)
    graphHandleRef.current?.focusNode(nodeId)
  }

  const openArticle = async () => {
    if (!selectedNode) return
    setArticleLoading(true)
    setArticleError('')
    try {
      setArticle(await invokeApplicationCapability<WikiArticleDetail>(runId, 'wiki.read', 'article', { source_id: selectedNode.id }))
    } catch {
      setArticleError('文章详情暂时无法打开，请稍后重试')
    } finally {
      setArticleLoading(false)
    }
  }

  const initialError = Boolean(error && !hasLoaded && graph.nodes.length === 0)

  return (
    <div className="relative flex h-full w-full overflow-hidden bg-surface">
      <div className="relative flex-1 overflow-hidden">
        <div data-graph-control="true" className="absolute left-3 top-3 z-10 flex flex-col gap-2 md:left-4 md:top-4">
          <div className="flex rounded-lg border border-border-subtle bg-white p-1 text-[12px] shadow-sm">
            <FeatureGuideTarget featureId="wiki-view-mode" onExecute={() => setViewMode('type')}>
              <button type="button" onClick={() => setViewMode('type')} className={cn('rounded-md px-3 py-1.5 font-medium', viewMode === 'type' ? 'bg-primary text-white' : 'text-on-surface-variant hover:bg-surface-container')}>
                类型视图
              </button>
            </FeatureGuideTarget>
            <FeatureGuideTarget featureId="wiki-view-mode" onExecute={() => setViewMode('community')}>
              <button type="button" onClick={() => setViewMode('community')} className={cn('rounded-md px-3 py-1.5 font-medium', viewMode === 'community' ? 'bg-primary text-white' : 'text-on-surface-variant hover:bg-surface-container')}>
                社群视图
              </button>
            </FeatureGuideTarget>
          </div>
          <div className="flex w-fit flex-col gap-1 rounded-lg border border-border-subtle bg-white p-1 shadow-sm">
            <button type="button" onClick={() => graphHandleRef.current?.zoomIn()} className="flex h-8 w-8 items-center justify-center rounded-md text-on-surface-variant hover:bg-surface-container hover:text-primary" title="放大" aria-label="放大"><Plus className="h-4 w-4" /></button>
            <button type="button" onClick={() => graphHandleRef.current?.zoomOut()} className="flex h-8 w-8 items-center justify-center rounded-md text-on-surface-variant hover:bg-surface-container hover:text-primary" title="缩小" aria-label="缩小"><Minus className="h-4 w-4" /></button>
            <button type="button" onClick={() => graphHandleRef.current?.resetView()} className="flex h-8 w-8 items-center justify-center rounded-md text-on-surface-variant hover:bg-surface-container hover:text-primary" title="重置视图" aria-label="重置视图"><Maximize2 className="h-4 w-4" /></button>
          </div>
        </div>

        <div data-graph-control="true" className="absolute right-3 top-3 z-10 flex max-w-[58vw] flex-wrap items-center justify-end gap-2 rounded-lg border border-border-subtle bg-white/95 px-2 py-2 text-[11px] shadow-sm md:right-4 md:top-4 md:gap-3 md:px-3 md:text-[12px]">
          {viewMode === 'type' ? (['concept', 'video', 'source'] as NodeType[]).map(type => <span key={type} className="flex items-center gap-1.5 text-on-surface-variant"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: NODE_META[type].color }} />{NODE_META[type].label}</span>) : communityLegend.slice(0, 8).map(community => <span key={community.id} className="flex items-center gap-1.5 text-on-surface-variant"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: community.color }} /><span className="max-w-[120px] truncate">{community.label}</span><span className="font-mono text-[10px]">{community.size}</span></span>)}
          <Button variant="ghost" size="sm" onClick={() => void loadWiki()} disabled={loading} className="ml-1 h-7 px-2 text-[12px] text-on-surface-variant hover:text-primary" aria-label="刷新 Wiki 图谱"><RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} /></Button>
        </div>

        {error && hasLoaded && <div role="alert" className="absolute inset-x-3 top-[88px] z-10 flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 md:inset-x-4"><span>{error}，已保留当前图谱。</span><Button variant="outline" size="sm" onClick={() => void loadWiki()} disabled={loading}>重试</Button></div>}
        {loading && !hasLoaded ? <div className="flex h-full items-center justify-center px-6"><KnowledgeEmptyState status="loading" title="正在启动 Wiki 应用" description="正在通过 Application Host 读取来源、概念与引用关系。" /></div> : initialError ? <div className="flex h-full items-center justify-center px-6"><KnowledgeEmptyState status="error" title="Wiki 应用暂时无法打开" description="图谱加载失败，可以刷新后重试。" detail={error} action={<Button onClick={() => void loadWiki()} variant="outline" size="sm"><RefreshCw className="mr-2 h-3.5 w-3.5" />重新加载</Button>} /></div> : graph.nodes.length === 0 ? <div className="flex h-full items-center justify-center px-6"><KnowledgeEmptyState title="知识库正在等待第一条线索" description="生成第一篇笔记后，实体、概念和来源会自动连接成一张可浏览的 Wiki 图谱。" /></div> : <SigmaWikiGraph ref={graphHandleRef} graph={graph} viewMode={viewMode} selectedNodeId={selectedNodeId || null} hoveredNodeId={hoveredNodeId || null} onSelectNode={nodeId => setSelectedNodeId(nodeId || '')} onHoverNode={nodeId => setHoveredNodeId(nodeId || '')} />}
      </div>

      {selectedNode && !article && <aside className="w-[320px] shrink-0 border-l border-border-subtle/60 bg-surface px-4 py-4"><div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border-subtle bg-white shadow-sm"><div className="flex shrink-0 items-start justify-between gap-2 border-b border-border-subtle px-4 py-4"><div className="min-w-0"><div className="mb-1 flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: nodeViewColor(selectedNode, viewMode) }} /><span className="text-[11px] text-on-surface-variant">{viewMode === 'community' ? communityDisplayName(selectedNode.community_label, selectedNode.community_id) : NODE_META[selectedNode.normalizedType].label}</span></div><h2 className="truncate font-display text-lg font-bold text-on-surface">{selectedNode.label || selectedNode.id}</h2></div><button type="button" onClick={() => setSelectedNodeId('')} className="rounded p-1 text-on-surface-variant hover:bg-surface-container" aria-label="关闭节点详情"><X className="h-4 w-4" /></button></div><ScrollArea className="min-h-0 flex-1"><div className="space-y-4 px-4 py-4"><Stat label="关联节点" value={String(selectedNode.degree)} /><div className="grid grid-cols-2 gap-2"><Stat label="社群编号" value={communityDisplayIndex(selectedNode.community_id)} /><Stat label="社群名称" value={communityDisplayName(selectedNode.community_label, selectedNode.community_id)} /></div>{(normalizeType(selectedNode.type) === 'source' || selectedNode.type === 'document' || selectedNode.type === 'page') && <Button variant="outline" size="sm" onClick={() => void openArticle()} disabled={articleLoading} className="w-full">{articleLoading ? '正在读取文章…' : '查看文章详情'}</Button>}{articleError && <p role="alert" className="text-xs text-red-600">{articleError}</p>}<section><h3 className="mb-2 text-xs font-semibold text-on-surface-variant">关联推荐</h3><div className="space-y-1">{neighborList.map(node => <button type="button" key={node.id} onClick={() => focusNode(node.id)} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-container"><span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: nodeViewColor(node, viewMode) }} /><span className="min-w-0 flex-1 truncate">{node.label || node.id}</span></button>)}{neighborList.length === 0 && <p className="text-xs text-on-surface-variant">暂无相邻节点。</p>}</div></section></div></ScrollArea></div></aside>}
      {article && <WikiArticle article={article} onClose={() => setArticle(null)} />}
    </div>
  )
}

export default WikiApplication
