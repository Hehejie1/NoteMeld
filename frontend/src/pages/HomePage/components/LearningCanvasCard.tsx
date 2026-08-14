import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, MessageSquarePlus, Minus, Plus, Scan, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useBackendInitContext } from '@/contexts/BackendInitContext'
import { getLearningCanvas, type LearningCanvas } from '@/services/learning'
import { useTaskStore } from '@/store/taskStore'
import type { SigmaWikiGraphHandle } from '@/pages/WikiPage/graph/SigmaWikiGraph'
import LearningCanvasGraph from './LearningCanvasGraph'

interface LearningCanvasCardProps {
  conversationId: string
  canvasId: string
}

export default function LearningCanvasCard({ conversationId, canvasId }: LearningCanvasCardProps) {
  const { backendReady } = useBackendInitContext()
  const addContextRef = useTaskStore(state => state.addContextRef)
  const [canvas, setCanvas] = useState<LearningCanvas | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const graphRef = useRef<SigmaWikiGraphHandle | null>(null)

  useEffect(() => {
    if (!backendReady) return
    let active = true
    setLoading(true)
    getLearningCanvas(conversationId, canvasId)
      .then(result => {
        if (!active) return
        setCanvas(result)
        setSelectedNodeId(result.current_node_id || result.nodes[0]?.id || null)
        setError('')
      })
      .catch(() => active && setError('研究白板加载失败'))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [backendReady, canvasId, conversationId])

  useEffect(() => {
    const handleFocus = (event: Event) => {
      const detail = (event as CustomEvent<{ canvasId?: string; nodeId?: string }>).detail
      if (detail?.canvasId !== canvasId || !detail.nodeId) return
      setSelectedNodeId(detail.nodeId)
      graphRef.current?.focusNode(detail.nodeId)
    }
    window.addEventListener('notemeld:focus-research-node', handleFocus)
    return () => window.removeEventListener('notemeld:focus-research-node', handleFocus)
  }, [canvasId])

  const selectedNode = useMemo(
    () => canvas?.nodes.find(node => node.id === selectedNodeId) || null,
    [canvas, selectedNodeId],
  )

  const addNodeToConversation = (nodeId: string) => {
    const node = canvas?.nodes.find(item => item.id === nodeId)
    if (!canvas || !node) return
    addContextRef({
      id: `whiteboard:${canvas.canvas_id}:${node.id}`,
      type: 'whiteboard_node',
      document_task_id: canvas.document_task_id || undefined,
      canvas_id: canvas.canvas_id,
      node_id: node.id,
      label: node.user_label || node.label,
      snapshot: node.user_summary || node.summary || node.label,
      source_ids: node.source_ids,
    })
  }

  if (loading) {
    return <div className="flex h-full items-center justify-center gap-2 text-sm text-on-surface-variant"><Loader2 className="h-4 w-4 animate-spin" />研究白板加载中…</div>
  }
  if (!canvas || error) return <div className="p-4 text-sm text-destructive">{error || '研究白板不存在'}</div>

  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-border-subtle px-3">
        <div>
          <div className="text-[13px] font-semibold text-on-surface">研究白板</div>
          <div className="max-w-[360px] truncate text-[11px] text-on-surface-variant">{canvas.goal}</div>
        </div>
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" aria-label="放大白板" onClick={() => graphRef.current?.zoomIn()}><Plus className="h-4 w-4" /></Button>
          <Button size="icon" variant="ghost" aria-label="缩小白板" onClick={() => graphRef.current?.zoomOut()}><Minus className="h-4 w-4" /></Button>
          <Button size="icon" variant="ghost" aria-label="适配白板" onClick={() => graphRef.current?.resetView()}><Scan className="h-4 w-4" /></Button>
        </div>
      </div>
      <div className="relative min-h-0 flex-1 overflow-hidden">
        <LearningCanvasGraph
          ref={graphRef}
          canvas={canvas}
          selectedNodeId={selectedNodeId}
          onSelectNode={setSelectedNodeId}
          onAddToConversation={addNodeToConversation}
        />
        {canvas.edges.length === 0 && (
          <div className="pointer-events-none absolute left-4 top-4 rounded-full border border-border-subtle/80 bg-white/85 px-3 py-1.5 text-[11px] text-on-surface-variant shadow-sm backdrop-blur">
            当前是主题节点视图，尚未形成可靠关系
          </div>
        )}
        {selectedNode ? (
          <div className="absolute bottom-4 left-4 right-4 z-10 max-w-[420px] rounded-xl border border-border-subtle bg-white/95 p-3.5 shadow-lg backdrop-blur">
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-medium uppercase tracking-wide text-primary">{selectedNode.type}</div>
                <div className="mt-1 text-sm font-semibold text-on-surface">{selectedNode.user_label || selectedNode.label}</div>
                <p className="mt-1.5 line-clamp-3 text-[12px] leading-5 text-on-surface-variant">{selectedNode.user_summary || selectedNode.summary || '这个节点还没有摘要，可在对话中继续研究。'}</p>
                <Button className="mt-3" size="sm" variant="outline" onClick={() => addNodeToConversation(selectedNode.id)}>
                  <MessageSquarePlus className="mr-1.5 h-3.5 w-3.5" />添加到对话
                </Button>
              </div>
              <Button size="icon" variant="ghost" aria-label="关闭节点详情" onClick={() => setSelectedNodeId(null)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
