import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
} from 'react'
import Sigma from 'sigma'

import type { WikiGraph } from '@/services/wiki'

import {
  buildGraphologyGraph,
  type WikiGraphologyGraph,
  type WikiSigmaEdgeAttributes,
  type WikiSigmaNodeAttributes,
} from './buildGraphologyGraph'
import { type GraphViewMode } from './colors'
import { runInitialLayout } from './layout'

// ForceAtlas2 layout is applied inside runInitialLayout before Sigma mounts.

export interface SigmaWikiGraphHandle {
  zoomIn: () => void
  zoomOut: () => void
  resetView: () => void
  focusNode: (nodeId: string) => void
}

interface SigmaWikiGraphProps {
  graph: WikiGraph
  viewMode: GraphViewMode
  selectedNodeId: string | null
  hoveredNodeId: string | null
  onSelectNode: (nodeId: string | null) => void
  onHoverNode: (nodeId: string | null) => void
}

const DIM_NODE_COLOR = '#cbd5e1'
const DIM_EDGE_COLOR = 'rgba(148, 163, 184, 0.08)'
const ACTIVE_EDGE_COLOR = 'rgba(79, 70, 229, 0.52)'
const RELATED_EDGE_COLOR = 'rgba(148, 163, 184, 0.2)'

const SigmaWikiGraph = forwardRef<SigmaWikiGraphHandle, SigmaWikiGraphProps>(function SigmaWikiGraph(
  { graph, viewMode, selectedNodeId, hoveredNodeId, onSelectNode, onHoverNode },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const rendererRef = useRef<Sigma<WikiSigmaNodeAttributes, WikiSigmaEdgeAttributes> | null>(null)
  const graphRef = useRef<WikiGraphologyGraph | null>(null)
  const hoverCallbackRef = useRef(onHoverNode)
  const selectCallbackRef = useRef(onSelectNode)

  useEffect(() => {
    hoverCallbackRef.current = onHoverNode
  }, [onHoverNode])

  useEffect(() => {
    selectCallbackRef.current = onSelectNode
  }, [onSelectNode])

  const selectedRelatedNodeIds = useMemo(() => {
    const next = new Set<string>()
    const sigmaGraph = graphRef.current
    if (selectedNodeId == null || sigmaGraph == null || sigmaGraph.hasNode(selectedNodeId) === false) return next
    next.add(selectedNodeId)
    sigmaGraph.neighbors(selectedNodeId).forEach(nodeId => next.add(String(nodeId)))
    return next
  }, [graph, selectedNodeId, viewMode])

  const refreshAppearance = useCallback(() => {
    const renderer = rendererRef.current
    const sigmaGraph = graphRef.current
    if (renderer == null || sigmaGraph == null) return

    renderer.setSetting('nodeReducer', (node, data) => {
      const isSelected = Boolean(selectedNodeId) && node === selectedNodeId
      const isHovered = Boolean(hoveredNodeId) && node === hoveredNodeId
      const isSelectionContext = selectedNodeId != null
      const isRelatedToSelection = isSelectionContext ? selectedRelatedNodeIds.has(String(node)) : true

      if (isRelatedToSelection === false) {
        return {
          ...data,
          color: DIM_NODE_COLOR,
          zIndex: 0,
        }
      }

      return {
        ...data,
        size: isSelected ? data.size * 1.3 : isHovered ? data.size * 1.15 : data.size,
        forceLabel: data.forceLabel || isSelected || isHovered,
        zIndex: isSelected || isHovered ? 1 : 0,
      }
    })

    renderer.setSetting('edgeReducer', (edge, data) => {
      const source = sigmaGraph.source(edge)
      const target = sigmaGraph.target(edge)
      const isHoveredEdge =
        hoveredNodeId != null && (source === hoveredNodeId || target === hoveredNodeId)
      const isSelectedEdge =
        selectedNodeId != null && (source === selectedNodeId || target === selectedNodeId)
      const isRelatedToSelection =
        selectedNodeId != null
          ? selectedRelatedNodeIds.has(String(source)) && selectedRelatedNodeIds.has(String(target))
          : true

      if (isRelatedToSelection === false) {
        return {
          ...data,
          color: DIM_EDGE_COLOR,
          size: 0.5,
          zIndex: 0,
        }
      }

      return {
        ...data,
        color: isHoveredEdge || isSelectedEdge ? ACTIVE_EDGE_COLOR : RELATED_EDGE_COLOR,
        size: isHoveredEdge || isSelectedEdge ? Math.max(1.8, data.size) : data.size,
        zIndex: isHoveredEdge || isSelectedEdge ? 1 : 0,
      }
    })

    renderer.refresh()
  }, [hoveredNodeId, selectedNodeId, selectedRelatedNodeIds])

  useEffect(() => {
    const container = containerRef.current
    if (container == null) return

    const sigmaGraph = buildGraphologyGraph(graph, viewMode)
    runInitialLayout(sigmaGraph)

    const renderer = new Sigma(sigmaGraph, container, {
      renderEdgeLabels: false,
      labelDensity: 0.16,
      labelGridCellSize: 96,
      labelRenderedSizeThreshold: 6,
      zIndex: true,
      allowInvalidContainer: true,
    })

    renderer.on('enterNode', ({ node }) => hoverCallbackRef.current(String(node)))
    renderer.on('leaveNode', () => hoverCallbackRef.current(null))
    renderer.on('clickNode', ({ node }) => selectCallbackRef.current(String(node)))
    renderer.on('clickStage', () => selectCallbackRef.current(null))

    rendererRef.current = renderer
    graphRef.current = sigmaGraph
    renderer.refresh()

    return () => {
      renderer.kill()
      rendererRef.current = null
      graphRef.current = null
    }
  }, [graph, viewMode])

  useEffect(() => {
    refreshAppearance()
  }, [refreshAppearance])

  useImperativeHandle(ref, () => ({
    zoomIn: () => {
      const camera = rendererRef.current?.getCamera()
      if (camera == null) return
      const state = camera.getState()
      camera.animate({ ratio: Math.max(0.08, state.ratio / 1.35) }, { duration: 220 })
    },
    zoomOut: () => {
      const camera = rendererRef.current?.getCamera()
      if (camera == null) return
      const state = camera.getState()
      camera.animate({ ratio: Math.min(3, state.ratio * 1.35) }, { duration: 220 })
    },
    resetView: () => {
      const camera = rendererRef.current?.getCamera()
      if (camera == null) return
      camera.animate({ x: 0, y: 0, ratio: 1, angle: 0 }, { duration: 240 })
    },
    focusNode: (nodeId: string) => {
      const camera = rendererRef.current?.getCamera()
      const sigmaGraph = graphRef.current
      if (camera == null || sigmaGraph == null || sigmaGraph.hasNode(nodeId) === false) return
      const attrs = sigmaGraph.getNodeAttributes(nodeId)
      const currentRatio = camera.getState().ratio
      camera.animate(
        {
          x: attrs.x,
          y: attrs.y,
          ratio: Math.min(currentRatio, 0.35),
        },
        { duration: 260 },
      )
    },
  }))

  return <div ref={containerRef} className="h-full w-full" />
})

export default SigmaWikiGraph
