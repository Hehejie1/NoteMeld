import Graph from 'graphology'

import type { WikiGraph, WikiGraphEdge, WikiGraphNode } from '@/services/wiki'

import { normalizeType, nodeWeight, resolveNodeColor, type GraphViewMode, type NodeType } from './colors'

export interface WikiSigmaNodeAttributes {
  label: string
  size: number
  color: string
  x: number
  y: number
  forceLabel: boolean
  raw: WikiGraphNode
  normalizedType: NodeType
  communityKey: string
}

export interface WikiSigmaEdgeAttributes {
  size: number
  color: string
  raw: WikiGraphEdge
}

export type WikiGraphologyGraph = Graph<WikiSigmaNodeAttributes, WikiSigmaEdgeAttributes>

const communityKeyOf = (node: WikiGraphNode): string =>
  typeof node.community_id === 'number' ? String(node.community_id) : 'unassigned'

const initialPosition = (index: number, total: number) => {
  const angle = (index / Math.max(total, 1)) * Math.PI * 2 * 2.2
  const radius = 18 + index * 2.8
  return {
    x: Math.cos(angle) * radius,
    y: Math.sin(angle) * radius,
  }
}

const edgePairKey = (edge: WikiGraphEdge): string => `${edge.source}=>${edge.target}`
const MIN_PERSISTENT_LABEL_COUNT = 3

const pickPersistentLabelNodeIds = (payload: WikiGraph): Set<string> => {
  if (payload.nodes.length === 0) return new Set()

  const degreeByNodeId = new Map<string, number>()
  payload.edges.forEach(edge => {
    degreeByNodeId.set(edge.source, (degreeByNodeId.get(edge.source) || 0) + 1)
    degreeByNodeId.set(edge.target, (degreeByNodeId.get(edge.target) || 0) + 1)
  })

  const typePriority = (node: WikiGraphNode): number => {
    const normalizedType = normalizeType(node.type)
    if (normalizedType === 'concept') return 3
    if (normalizedType === 'source') return 2
    if (normalizedType === 'video') return 1
    return 0
  }

  return new Set(
    [...payload.nodes]
      .sort((left, right) => {
        const degreeDelta = (degreeByNodeId.get(right.id) || 0) - (degreeByNodeId.get(left.id) || 0)
        if (degreeDelta !== 0) return degreeDelta

        const weightDelta = nodeWeight(right) - nodeWeight(left)
        if (weightDelta !== 0) return weightDelta

        const typeDelta = typePriority(right) - typePriority(left)
        if (typeDelta !== 0) return typeDelta

        return (left.label || left.id).localeCompare(right.label || right.id)
      })
      .slice(0, Math.min(MIN_PERSISTENT_LABEL_COUNT, payload.nodes.length))
      .map(node => node.id),
  )
}

export const buildGraphologyGraph = (
  payload: WikiGraph,
  viewMode: GraphViewMode,
): WikiGraphologyGraph => {
  const graph = new Graph<WikiSigmaNodeAttributes, WikiSigmaEdgeAttributes>()
  const total = Math.max(payload.nodes.length, 1)
  const mergedEdgesByPair = new Map<string, WikiGraphEdge>()
  const persistentLabelNodeIds = pickPersistentLabelNodeIds(payload)

  payload.nodes.forEach((node, index) => {
    const point = initialPosition(index, total)
    graph.addNode(node.id, {
      label: node.label || node.id,
      size: Math.max(5, Math.min(24, 6 + Math.sqrt(nodeWeight(node)) * 3)),
      color: resolveNodeColor(node, viewMode),
      x: point.x,
      y: point.y,
      forceLabel: persistentLabelNodeIds.has(node.id),
      raw: node,
      normalizedType: normalizeType(node.type),
      communityKey: communityKeyOf(node),
    })
  })

  payload.edges.forEach(edge => {
    if (graph.hasNode(edge.source) === false || graph.hasNode(edge.target) === false) return
    const pairKey = edgePairKey(edge)
    const previous = mergedEdgesByPair.get(pairKey)
    if (previous == null) {
      mergedEdgesByPair.set(pairKey, edge)
      return
    }
    if ((edge.weight || 1) > (previous.weight || 1)) {
      mergedEdgesByPair.set(pairKey, edge)
    }
  })

  Array.from(mergedEdgesByPair.values()).forEach((edge, index) => {
    graph.addEdgeWithKey(String(index), edge.source, edge.target, {
      size: Math.max(0.8, Math.min(3, edge.weight || 1)),
      color: 'rgba(148, 163, 184, 0.28)',
      raw: edge,
    })
  })

  return graph
}
