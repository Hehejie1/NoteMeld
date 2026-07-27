import { FC, useEffect, useMemo, useRef, useState } from 'react'
import { Maximize2, Minus, Plus, RefreshCw, Sparkles, X } from 'lucide-react'
import { toast } from 'react-hot-toast'

import KnowledgeEmptyState from '@/components/KnowledgeEmptyState'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { getWikiGraph, type WikiGraph, type WikiGraphNode } from '@/services/wiki'

import SigmaWikiGraph, { type SigmaWikiGraphHandle } from './graph/SigmaWikiGraph'
import {
  NODE_META,
  communityDisplayIndex,
  communityDisplayName,
  nodeViewColor,
  normalizeType,
  type GraphViewMode,
  type NodeType,
} from './graph/colors'

const emptyGraph: WikiGraph = { nodes: [], edges: [], clusters: [] }

interface DisplayNode extends WikiGraphNode {
  normalizedType: NodeType
  degree: number
}

const buildDegreeMap = (graph: WikiGraph) => {
  const degreeMap = new Map<string, number>()
  graph.edges.forEach(edge => {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1)
    degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1)
  })
  return degreeMap
}

const WikiPage: FC = () => {
  const [graph, setGraph] = useState<WikiGraph>(emptyGraph)
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [hoveredNodeId, setHoveredNodeId] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [viewMode, setViewMode] = useState<GraphViewMode>('type')
  const [isMobile, setIsMobile] = useState(false)
  const graphHandleRef = useRef<SigmaWikiGraphHandle | null>(null)

  const loadWiki = async () => {
    setLoading(true)
    setError('')
    try {
      const result = await getWikiGraph()
      setGraph({
        nodes: result.nodes || [],
        edges: result.edges || [],
        clusters: result.clusters || [],
      })
    } catch {
      setError('知识库加载失败，请检查后端服务或稍后重试')
      toast.error('知识库加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadWiki()
  }, [])

  useEffect(() => {
    const media = window.matchMedia('(max-width: 767px)')
    const sync = () => setIsMobile(media.matches)
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])

  const degreeMap = useMemo(() => buildDegreeMap(graph), [graph])

  const nodeMap = useMemo(() => {
    const map = new Map<string, DisplayNode>()
    graph.nodes.forEach(node => {
      map.set(node.id, {
        ...node,
        normalizedType: normalizeType(node.type),
        degree: degreeMap.get(node.id) || 0,
      })
    })
    return map
  }, [degreeMap, graph.nodes])

  useEffect(() => {
    if (!selectedNodeId) return
    if (!nodeMap.has(selectedNodeId)) {
      setSelectedNodeId('')
      setHoveredNodeId('')
    }
  }, [selectedNodeId, nodeMap])

  const selectedNode = selectedNodeId ? nodeMap.get(selectedNodeId) : undefined

  const neighborIds = useMemo(() => {
    const related = new Set<string>()
    if (!selectedNodeId) return related
    graph.edges.forEach(edge => {
      if (edge.source === selectedNodeId) related.add(edge.target)
      if (edge.target === selectedNodeId) related.add(edge.source)
    })
    return related
  }, [graph.edges, selectedNodeId])

  const communityLegend = useMemo(() => {
    const byId = new Map<
      number,
      {
        id: number
        label: string
        color: string
        size: number
        cohesion?: number
        isWeak?: boolean
      }
    >()
    graph.nodes.forEach(node => {
      if (typeof node.community_id !== 'number') return
      const current = byId.get(node.community_id)
      byId.set(node.community_id, {
        id: node.community_id,
        label: communityDisplayName(node.community_label, node.community_id),
        color: node.community_color || '#64748b',
        size: (current?.size || 0) + 1,
        cohesion: node.community_cohesion ?? current?.cohesion,
        isWeak: node.community_is_weak ?? current?.isWeak,
      })
    })
    return Array.from(byId.values()).sort((a, b) => b.size - a.size)
  }, [graph.nodes])

  const neighborList = useMemo(() => {
    return Array.from(neighborIds)
      .map(id => nodeMap.get(id))
      .filter((node): node is DisplayNode => Boolean(node))
      .sort((a, b) => b.degree - a.degree)
  }, [neighborIds, nodeMap])

  const sameCommunityList = useMemo(() => {
    if (!selectedNode || typeof selectedNode.community_id !== 'number') return []
    return graph.nodes
      .map(node => nodeMap.get(node.id))
      .filter((node): node is DisplayNode => Boolean(node))
      .filter(node => node.id !== selectedNode.id && node.community_id === selectedNode.community_id)
      .sort((a, b) => b.degree - a.degree)
  }, [graph.nodes, nodeMap, selectedNode])

  const focusNode = (nodeId: string) => {
    setSelectedNodeId(nodeId)
    graphHandleRef.current?.focusNode(nodeId)
  }

  return (
    <div className="relative flex h-full w-full overflow-hidden bg-surface">
      <div className="relative flex-1 overflow-hidden">
        <div
          data-graph-control="true"
          className="absolute left-3 top-3 z-10 flex flex-col gap-2 md:left-4 md:top-4"
        >
          <div className="flex rounded-lg border border-border-subtle bg-white p-1 text-[12px] shadow-sm">
            <button
              onClick={() => setViewMode('type')}
              className={cn(
                'rounded-md px-3 py-1.5 font-medium transition-colors',
                viewMode === 'type'
                  ? 'bg-primary text-white'
                  : 'text-on-surface-variant hover:bg-surface-container hover:text-primary',
              )}
            >
              类型视图
            </button>
            <button
              onClick={() => setViewMode('community')}
              className={cn(
                'rounded-md px-3 py-1.5 font-medium transition-colors',
                viewMode === 'community'
                  ? 'bg-primary text-white'
                  : 'text-on-surface-variant hover:bg-surface-container hover:text-primary',
              )}
            >
              社群视图
            </button>
          </div>
          <div className="flex w-fit flex-col gap-1 rounded-lg border border-border-subtle bg-white p-1 shadow-sm">
            <button
              onClick={() => graphHandleRef.current?.zoomIn()}
              className="flex h-8 w-8 items-center justify-center rounded-md text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary"
              title="放大"
            >
              <Plus className="h-4 w-4" />
            </button>
            <button
              onClick={() => graphHandleRef.current?.zoomOut()}
              className="flex h-8 w-8 items-center justify-center rounded-md text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary"
              title="缩小"
            >
              <Minus className="h-4 w-4" />
            </button>
            <button
              onClick={() => graphHandleRef.current?.resetView()}
              className="flex h-8 w-8 items-center justify-center rounded-md text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary"
              title="重置视图"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div
          data-graph-control="true"
          className="absolute right-3 top-3 z-10 flex max-w-[48vw] flex-wrap items-center justify-end gap-2 rounded-lg border border-border-subtle bg-white/95 px-2 py-2 text-[11px] shadow-sm md:right-4 md:top-4 md:max-w-[520px] md:gap-3 md:px-3 md:text-[12px]"
        >
          {viewMode === 'type'
            ? (['concept', 'video', 'source'] as NodeType[]).map(type => (
                <span key={type} className="flex items-center gap-1.5 text-on-surface-variant">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: NODE_META[type].color }} />
                  {NODE_META[type].label}
                </span>
              ))
            : communityLegend.slice(0, 8).map(community => (
                <span key={community.id} className="flex items-center gap-1.5 text-on-surface-variant">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: community.color }} />
                  <span className="max-w-[120px] truncate">{community.label}</span>
                  <span className="font-mono text-[10px] text-on-surface-variant/70">{community.size}</span>
                </span>
              ))}
          <Button
            variant="ghost"
            size="sm"
            onClick={loadWiki}
            disabled={loading}
            className="ml-1 h-7 px-2 text-[12px] text-on-surface-variant hover:text-primary"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
          </Button>
        </div>

        {loading ? (
          <div className="flex h-full items-center justify-center px-6">
            <KnowledgeEmptyState
              status="loading"
              title="正在读取知识图谱"
              description="系统正在同步来源、概念与引用关系，知识网络会在这里逐步浮现。"
            />
          </div>
        ) : error ? (
          <div className="flex h-full items-center justify-center px-6">
            <KnowledgeEmptyState
              status="error"
              title="知识库暂时无法打开"
              description="图谱加载失败，可以刷新后重试。"
              detail={error}
              action={
                <Button onClick={loadWiki} disabled={loading} variant="outline" size="sm">
                  <RefreshCw className={cn('mr-2 h-3.5 w-3.5', loading && 'animate-spin')} />
                  重新加载
                </Button>
              }
            />
          </div>
        ) : graph.nodes.length === 0 ? (
          <div className="flex h-full items-center justify-center px-6">
            <KnowledgeEmptyState
              title="知识库正在等待第一条线索"
              description="生成第一篇笔记后，实体、概念和来源会自动连接成一张可浏览的个人 Wiki 图谱。"
            />
          </div>
        ) : (
          <div className="h-full w-full">
            <SigmaWikiGraph
              ref={graphHandleRef}
              graph={graph}
              viewMode={viewMode}
              selectedNodeId={selectedNodeId || null}
              hoveredNodeId={hoveredNodeId || null}
              onSelectNode={nodeId => setSelectedNodeId(nodeId || '')}
              onHoverNode={nodeId => setHoveredNodeId(nodeId || '')}
            />
          </div>
        )}
      </div>

      {selectedNode && (
        <aside
          className={cn(
            isMobile
              ? 'absolute inset-x-3 bottom-5 z-20 overflow-hidden rounded-2xl border border-border-subtle/70 bg-white shadow-2xl'
              : 'w-[368px] shrink-0 border-l border-border-subtle/60 bg-surface px-4 py-4',
          )}
          style={
            isMobile
              ? {
                  height:
                    'min(360px, calc(100dvh - var(--mobile-bottom-nav-height) - env(safe-area-inset-bottom) - 128px))',
                }
              : undefined
          }
        >
          <div className="flex h-full min-h-0 w-full flex-col overflow-hidden rounded-2xl border border-border-subtle/60 bg-white shadow-sm md:max-w-[336px]">
            <div className="shrink-0 flex items-start justify-between gap-2 border-b border-border-subtle/60 px-5 py-4">
              <div className="min-w-0">
                <div className="mb-1 flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: nodeViewColor(selectedNode, viewMode) }} />
                  <span className="text-[11px] font-medium tracking-wide text-on-surface-variant">
                    {viewMode === 'community'
                      ? communityDisplayName(selectedNode.community_label, selectedNode.community_id)
                      : NODE_META[selectedNode.normalizedType].label}
                  </span>
                </div>
                <h2 className="font-display truncate text-[18px] font-bold text-on-surface">
                  {selectedNode.label || selectedNode.id}
                </h2>
              </div>
              <button
                onClick={() => setSelectedNodeId('')}
                className="rounded p-1 text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <ScrollArea className="min-h-0 min-w-0 flex-1 overscroll-contain [&_[data-slot=scroll-area-viewport]>div]:!block [&_[data-slot=scroll-area-viewport]>div]:min-w-0 [&_[data-slot=scroll-area-viewport]>div]:!w-full">
              <div className="space-y-5 px-5 py-4 pr-5 pb-6">
                <Stat label="关联节点" value={selectedNode.degree.toString()} />
                <div className="grid grid-cols-2 gap-2">
                  <Stat label="社群编号" value={communityDisplayIndex(selectedNode.community_id)} />
                  <Stat label="社群名称" value={communityDisplayName(selectedNode.community_label, selectedNode.community_id)} />
                  <Stat
                    label="社群凝聚度"
                    value={
                      typeof selectedNode.community_cohesion === 'number'
                        ? selectedNode.community_cohesion.toFixed(3)
                        : '-'
                    }
                  />
                  <Stat label="弱社群" value={selectedNode.community_is_weak ? '是' : '否'} />
                </div>

                {sameCommunityList.length > 0 && (
                  <section>
                    <div className="mb-2 flex items-center gap-1.5">
                      <Sparkles className="h-3.5 w-3.5 text-primary" />
                      <h3 className="text-[12px] font-semibold text-on-surface">同社群节点</h3>
                    </div>
                    <div className="space-y-1">
                      {sameCommunityList.slice(0, 12).map(node => (
                        <button
                          key={node.id}
                          onClick={() => focusNode(node.id)}
                          className="group flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-[13px] text-on-surface transition-colors hover:bg-surface-container"
                        >
                          <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: nodeViewColor(node, viewMode) }} />
                          <span className="min-w-0 flex-1 truncate">{node.label || node.id}</span>
                          <span className="shrink-0 pl-2 font-mono text-[10px] text-on-surface-variant/60 group-hover:text-primary">
                            {node.degree}
                          </span>
                        </button>
                      ))}
                    </div>
                  </section>
                )}

                {neighborList.length > 0 && (
                  <section>
                    <div className="mb-2 flex items-center gap-1.5">
                      <Sparkles className="h-3.5 w-3.5 text-primary" />
                      <h3 className="text-[12px] font-semibold text-on-surface">关联推荐</h3>
                    </div>
                    <div className="space-y-1">
                      {neighborList.map(node => (
                        <button
                          key={node.id}
                          onClick={() => focusNode(node.id)}
                          className="group flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-[13px] text-on-surface transition-colors hover:bg-surface-container"
                        >
                          <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: nodeViewColor(node, viewMode) }} />
                          <span className="min-w-0 flex-1 truncate">{node.label || node.id}</span>
                          <span className="shrink-0 pl-2 font-mono text-[10px] text-on-surface-variant/60 group-hover:text-primary">
                            {node.degree}
                          </span>
                        </button>
                      ))}
                    </div>
                  </section>
                )}
              </div>
            </ScrollArea>
          </div>
        </aside>
      )}
    </div>
  )
}

const Stat: FC<{ label: string; value: string; className?: string }> = ({ label, value, className }) => (
  <div
    className={cn('min-w-0 rounded-lg border border-border-subtle bg-surface-container/50 px-3 py-2', className)}
    title={value}
  >
    <div className="truncate text-[10px] tracking-wide text-on-surface-variant" title={label}>
      {label}
    </div>
    <div className="font-display mt-0.5 truncate text-[18px] font-bold text-on-surface" title={value}>
      {value}
    </div>
  </div>
)

export default WikiPage
