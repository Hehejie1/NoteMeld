export interface LearningWorkspaceMessageLike {
  id?: string
  message_type?: string
  meta?: Record<string, unknown>
}

export interface LearningWorkspaceTarget {
  messageId: string
  canvasId: string
  whiteboardId: string
  status: string
}

export interface SeededWhiteboardTarget {
  key: string
  id: string
}

export function createLearningSeedKey(
  conversationId: string,
  messageId: string,
  canvasId: string,
): string {
  return conversationId && messageId
    ? JSON.stringify([conversationId, messageId, canvasId])
    : ''
}

export function resolveWhiteboardId(
  compactWhiteboardId: string,
  seedRequestKey: string,
  seeded: SeededWhiteboardTarget,
): string {
  if (compactWhiteboardId) return compactWhiteboardId
  return seeded.key === seedRequestKey ? seeded.id : ''
}

export function resolveLatestLearningWorkspace(
  messages: readonly LearningWorkspaceMessageLike[],
): LearningWorkspaceTarget | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.message_type !== 'learning_canvas') continue
    const status = typeof message.meta?.status === 'string' ? message.meta.status : ''
    if (status === 'clarifying') return null
    const canvasId = typeof message.meta?.canvas_id === 'string' ? message.meta.canvas_id : ''
    const whiteboardId = typeof message.meta?.whiteboard_id === 'string'
      ? message.meta.whiteboard_id
      : ''
    if (!canvasId && !whiteboardId) return null
    return {
      messageId: typeof message.id === 'string' ? message.id : `${index}`,
      canvasId,
      whiteboardId,
      status,
    }
  }
  return null
}

export type WhiteboardPublishState = 'unpublished' | 'stale' | 'synced'

export interface WhiteboardPublishPresentation {
  state: WhiteboardPublishState
  label: '尚未发布' | '有未发布变更' | '已同步到笔记'
  actionLabel: '发布为笔记' | '更新笔记'
}

export function getWhiteboardPublishPresentation(input: {
  revision: number
  noteLink: { published_revision: number } | null
}): WhiteboardPublishPresentation {
  if (!input.noteLink) {
    return { state: 'unpublished', label: '尚未发布', actionLabel: '发布为笔记' }
  }
  if (input.revision > input.noteLink.published_revision) {
    return { state: 'stale', label: '有未发布变更', actionLabel: '更新笔记' }
  }
  return { state: 'synced', label: '已同步到笔记', actionLabel: '更新笔记' }
}

export function createSeedAttemptRegistry() {
  const attempted = new Set<string>()
  const keyFor = (conversationId: string, messageId: string) =>
    JSON.stringify([conversationId, messageId])
  return {
    claim(conversationId: string, messageId: string) {
      const key = keyFor(conversationId, messageId)
      if (attempted.has(key)) return false
      attempted.add(key)
      return true
    },
    release(conversationId: string, messageId: string) {
      attempted.delete(keyFor(conversationId, messageId))
    },
  }
}
