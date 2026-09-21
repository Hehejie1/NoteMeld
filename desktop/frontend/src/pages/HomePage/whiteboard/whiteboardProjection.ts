import { MarkerType, type Edge, type Node } from '@xyflow/react'
import type {
  CardMoveResizeItem,
  WhiteboardCard,
  WhiteboardOperation,
  WhiteboardRelation,
  WhiteboardSnapshot,
} from './types'

export interface WhiteboardCardNodeData extends Record<string, unknown> {
  card: WhiteboardCard
  active: boolean
}

export interface WhiteboardRelationEdgeData extends Record<string, unknown> {
  relation: WhiteboardRelation
  onEdit?: (relationId: string) => void
}

export type WhiteboardFlowNode = Node<WhiteboardCardNodeData, 'whiteboardCard'>
export type WhiteboardFlowEdge = Edge<WhiteboardRelationEdgeData, 'whiteboardRelation'>

const relationColor = (relation: WhiteboardRelation) => {
  switch (relation.style.color) {
    case 'accent': return '#6366f1'
    case 'positive': return '#16a34a'
    case 'warning': return '#d97706'
    case 'danger': return '#dc2626'
    case 'muted': return '#94a3b8'
    default: return '#64748b'
  }
}

const relationWidth = (relation: WhiteboardRelation) => {
  if (relation.style.width === 'thick') return 3
  if (relation.style.width === 'medium') return 2
  return 1.5
}

const relationDash = (relation: WhiteboardRelation) => {
  if (relation.style.pattern === 'dashed') return '8 5'
  if (relation.style.pattern === 'dotted') return '2 4'
  return undefined
}

const relationMarker = (relation: WhiteboardRelation) => ({
  type: MarkerType.ArrowClosed,
  color: relationColor(relation),
})

export function projectWhiteboard(
  snapshot: WhiteboardSnapshot,
  options: {
    selectedCardIds?: ReadonlySet<string>
    selectedRelationIds?: ReadonlySet<string>
    activeCardId?: string | null
  } = {},
): { nodes: WhiteboardFlowNode[]; edges: WhiteboardFlowEdge[] } {
  const nodes = snapshot.cards.map<WhiteboardFlowNode>(card => ({
    id: card.id,
    type: 'whiteboardCard',
    position: { x: card.position.x, y: card.position.y },
    width: card.size.width,
    height: card.size.height,
    style: { width: card.size.width, height: card.size.height },
    zIndex: card.z_index,
    selected: options.selectedCardIds?.has(card.id) ?? false,
    data: { card, active: options.activeCardId === card.id },
  }))

  const edges = snapshot.relations.map<WhiteboardFlowEdge>(relation => {
    const marker = relationMarker(relation)
    return {
      id: relation.id,
      type: 'whiteboardRelation',
      source: relation.source_card_id,
      target: relation.target_card_id,
      label: relation.label,
      selected: options.selectedRelationIds?.has(relation.id) ?? false,
      data: { relation },
      style: {
        stroke: relationColor(relation),
        strokeWidth: relationWidth(relation),
        strokeDasharray: relationDash(relation),
      },
      markerStart: relation.direction === 'backward' || relation.direction === 'both' ? marker : undefined,
      markerEnd: relation.direction === 'forward' || relation.direction === 'both' ? marker : undefined,
    }
  })

  return { nodes, edges }
}

export function cardMoveResizeOperation(
  nodes: ReadonlyArray<Pick<WhiteboardFlowNode, 'id' | 'position' | 'width' | 'height'>>,
): WhiteboardOperation {
  const items: CardMoveResizeItem[] = nodes.map(node => ({
    card_id: node.id,
    position: { x: node.position.x, y: node.position.y },
    ...(typeof node.width === 'number' && typeof node.height === 'number'
      ? { size: { width: node.width, height: node.height } }
      : {}),
  }))
  return { op: 'card.move_resize', items }
}
