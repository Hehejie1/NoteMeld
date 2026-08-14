import { forwardRef, useMemo, useState } from 'react'
import SigmaWikiGraph, { type SigmaWikiGraphHandle } from '@/pages/WikiPage/graph/SigmaWikiGraph'
import type { WikiGraph } from '@/services/wiki'
import type { LearningCanvas, MasteryStatus } from '@/services/learning'

const masteryColor: Record<MasteryStatus, string> = {
  unknown: '#94a3b8',
  exposed: '#64748b',
  learning: '#f59e0b',
  provisional: '#7c3aed',
  mastered: '#16a34a',
}

interface LearningCanvasGraphProps {
  canvas: LearningCanvas
  selectedNodeId: string | null
  onSelectNode: (nodeId: string | null) => void
  onAddToConversation?: (nodeId: string) => void
}

const LearningCanvasGraph = forwardRef<SigmaWikiGraphHandle, LearningCanvasGraphProps>(function LearningCanvasGraph({
  canvas,
  selectedNodeId,
  onSelectNode,
  onAddToConversation,
}: LearningCanvasGraphProps, ref) {
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const graph = useMemo<WikiGraph>(
    () => ({
      nodes: canvas.nodes.map(node => ({
        id: node.id,
        label: node.user_label || node.label,
        type: node.type,
        community_color: masteryColor[node.mastery],
        weight: node.priority === 'high' ? 3 : node.priority === 'medium' ? 2 : 1,
      })),
      edges: canvas.edges,
      clusters: [],
    }),
    [canvas],
  )

  return (
    <div className="relative h-full min-h-[320px] overflow-hidden bg-surface-container-low">
      <SigmaWikiGraph
        ref={ref}
        graph={graph}
        viewMode="community"
        selectedNodeId={selectedNodeId}
        hoveredNodeId={hoveredNodeId}
        onSelectNode={onSelectNode}
        onHoverNode={setHoveredNodeId}
        onContextMenuNode={nodeId => onAddToConversation?.(nodeId)}
      />
    </div>
  )
})

export default LearningCanvasGraph
