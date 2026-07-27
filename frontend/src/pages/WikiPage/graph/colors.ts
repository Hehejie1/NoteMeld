import type { WikiGraphNode } from '@/services/wiki'

export type NodeType = 'concept' | 'video' | 'source' | 'other'
export type GraphViewMode = 'type' | 'community'

interface NodeMeta {
  key: NodeType
  label: string
  color: string
}

export const NODE_META: Record<NodeType, NodeMeta> = {
  concept: { key: 'concept', label: '核心概念', color: '#4c40f6' },
  video: { key: 'video', label: '视频笔记', color: '#2563eb' },
  source: { key: 'source', label: '参考资源', color: '#10b981' },
  other: { key: 'other', label: '其它', color: '#9ca3af' },
}

export const normalizeType = (value?: string): NodeType => {
  const v = (value || '').toLowerCase()
  if (['concept', 'topic', 'overview', 'root'].includes(v)) return 'concept'
  if (['video', 'entity'].includes(v)) return 'video'
  if (['source', 'document', 'page'].includes(v)) return 'source'
  return 'other'
}

export const nodeWeight = (node: WikiGraphNode): number => {
  if (typeof node.weight === 'number') return node.weight
  if (typeof node.size === 'number') return node.size
  return 1
}

export const nodeTypeColor = (node: WikiGraphNode): string => NODE_META[normalizeType(node.type)].color

export const nodeViewColor = (node: WikiGraphNode, viewMode: GraphViewMode): string => {
  if (viewMode === 'community') return node.community_color || '#64748b'
  return nodeTypeColor(node)
}

export const communityDisplayName = (communityLabel?: string, communityId?: number): string => {
  if (communityLabel && communityLabel.trim()) return communityLabel.trim()
  if (typeof communityId === 'number') return `社群 ${communityId + 1}`
  return '未分组'
}

export const communityDisplayIndex = (communityId?: number): string => {
  if (typeof communityId === 'number') return String(communityId + 1)
  return '-'
}

export const resolveNodeColor = (
  node: Pick<WikiGraphNode, 'type' | 'community_color'>,
  viewMode: GraphViewMode,
): string => {
  if (viewMode === 'community') return node.community_color || '#64748b'
  return NODE_META[normalizeType(node.type)].color
}
