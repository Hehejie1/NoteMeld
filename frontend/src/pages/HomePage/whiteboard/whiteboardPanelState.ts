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

export interface WhiteboardSeedErrorTarget {
  key: string
  message: string
}

export function resolveSeedError(
  seedRequestKey: string,
  error: WhiteboardSeedErrorTarget,
): string {
  return error.key === seedRequestKey ? error.message : ''
}

export interface SeedAttemptRegistry {
  claim: (conversationId: string, messageId: string) => boolean
}

export interface WhiteboardNoteDocumentLike {
  taskId: string
  content?: string
  status?: string
}

export function resolveWhiteboardNoteDocument<T extends WhiteboardNoteDocumentLike>(
  noteLink: { note_task_id: string } | null,
  documents: readonly T[],
): {
  taskId: string
  content: string
  status: 'idle' | 'loading' | 'success' | 'failed'
  document: T | null
} {
  const taskId = noteLink?.note_task_id || ''
  if (!taskId) return { taskId: '', content: '', status: 'idle', document: null }
  const document = documents.find(item => item.taskId === taskId) || null
  const normalizedStatus = document?.status?.toUpperCase() || ''
  const status = normalizedStatus === 'FAILED' || normalizedStatus === 'CANCELED'
    ? 'failed'
    : document?.content
    ? 'success'
    : 'loading'
  return { taskId, content: document?.content || '', status, document }
}

export async function runLegacyWhiteboardSeed<T>({
  backendReady,
  conversationId,
  messageId,
  canvasId,
  registry,
  request,
}: {
  backendReady: boolean
  conversationId: string
  messageId: string
  canvasId: string
  registry: SeedAttemptRegistry
  request: () => Promise<T>
}): Promise<{ status: 'waiting' | 'skipped' } | { status: 'seeded'; value: T }> {
  if (!backendReady) return { status: 'waiting' }
  if (!conversationId || !messageId || !canvasId) return { status: 'skipped' }
  if (!registry.claim(conversationId, messageId)) return { status: 'skipped' }
  return { status: 'seeded', value: await request() }
}

export async function completePublishedConversationRefresh<T>({
  conversationId,
  getCurrentConversationId,
  refresh,
  apply,
}: {
  conversationId: string
  getCurrentConversationId: () => string | null
  refresh: () => Promise<T>
  apply: (value: T) => void
}): Promise<{ status: 'applied'; value: T } | { status: 'stale' }> {
  const value = await refresh()
  if (getCurrentConversationId() !== conversationId) return { status: 'stale' }
  apply(value)
  return { status: 'applied', value }
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
