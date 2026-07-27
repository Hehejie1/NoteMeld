const URL_REGEX = /(https?:\/\/[^\s]+)/i

export interface ParsedMessageContent {
  url: string
  text: string
}

export interface TimelineMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  message_type: 'user_input' | 'assistant_text' | 'note_progress' | 'note_result' | 'system_error'
  content: string
  status?: 'pending' | 'running' | 'success' | 'failed'
  meta?: Record<string, unknown>
  createdAt?: string
  sources?: unknown[]
  error?: boolean
  isStreaming?: boolean
  updatedAt?: string
}

export interface TimelineTask {
  mode?: 'chat' | 'note'
  status?: string
  noteState?: string
  messages?: TimelineMessage[]
}

export interface NoteDocumentSummary {
  taskId: string
  title: string
  sourceUrl: string
  platform: string
  createdAt?: string
}

export interface TimelineItem {
  type: 'message'
  id: string
  message: TimelineMessage
}

export const composeNoteFirstMessage = (url?: string, text?: string): string => {
  const normalizedUrl = (url || '').trim()
  const normalizedText = (text || '').trim()
  if (normalizedUrl && normalizedText) return `${normalizedUrl}\n${normalizedText}`
  return normalizedUrl || normalizedText
}

export const parseMessageContent = (content?: string): ParsedMessageContent => {
  const raw = content || ''
  const match = raw.match(URL_REGEX)
  if (!match) {
    return { url: '', text: raw.trim() }
  }

  const url = match[0]
  const text = raw.replace(url, '').replace(/\n{3,}/g, '\n\n').trim()
  return { url, text }
}

export const buildConversationTimeline = (task?: TimelineTask | null): TimelineItem[] => {
  const messages = task?.messages || []
  return messages.map(message => ({
    type: 'message' as const,
    id: message.id,
    message,
  }))
}

export const extractNoteDocuments = (messages?: TimelineMessage[]): NoteDocumentSummary[] => {
  const documents = new Map<string, NoteDocumentSummary>()
  for (const message of messages || []) {
    if (message.message_type !== 'note_result') continue
    const taskId = typeof message.meta?.task_id === 'string' ? message.meta.task_id : ''
    if (!taskId) continue
    documents.set(taskId, {
      taskId,
      title:
        (typeof message.meta?.title === 'string' && message.meta.title) ||
        message.content ||
        '未命名笔记',
      sourceUrl: typeof message.meta?.source_url === 'string' ? message.meta.source_url : '',
      platform: typeof message.meta?.platform === 'string' ? message.meta.platform : '',
      createdAt: message.createdAt,
    })
  }
  return [...documents.values()]
}
