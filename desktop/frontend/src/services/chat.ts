import type { ConversationMessage, ConversationSource } from '@/store/taskStore'
import { isDemoMode } from '@/demo/mode'
import { demoStreamFreeChat } from '@/demo/transport'
import { createAgentSession, startAgentTurn, streamAgentEvents } from '@/services/agent'

export interface LegacyConversationContextRef {
  id: string
  type: 'note_selection' | 'whiteboard_node'
  document_task_id?: string
  canvas_id?: string
  node_id?: string
  label: string
  snapshot: string
  source_ids?: string[]
}

export interface WhiteboardSelectionContextRef {
  id: string
  type: 'whiteboard_selection'
  whiteboard_id: string
  revision: number
  card_ids: string[]
  relation_ids: string[]
  label: string
  snapshot: string
  source_ids?: string[]
}

export type ConversationContextRef = LegacyConversationContextRef | WhiteboardSelectionContextRef

export interface FreeChatPayload {
  question: string
  history: Pick<ConversationMessage, 'role' | 'content'>[]
  provider_id: string
  model_name: string
  conversation_id?: string
  linked_task_id?: string
  use_wiki?: boolean
  asset_content?: string
  context_refs?: ConversationContextRef[]
}

export interface FreeChatResponse {
  answer: string
  sources: ConversationSource[]
}

export type TaskCardStreamStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'CANCELED'

export interface TaskCardStreamEvent {
  type: 'task_card'
  card_id: string
  kind: string
  task_id?: string
  status: TaskCardStreamStatus
  title: string
  progress: number | null
}

export interface TaskCardProgressStreamEvent {
  type: 'task_card_progress'
  card_id: string
  status: TaskCardStreamStatus
  progress: number | null
  details?: string
}

export interface ParameterRequestStreamEvent {
  kind: 'parameter_request'
  call_id: string
  params: Array<{
    key: string
    label: string
    widget: string
    options?: unknown
  }>
  ts?: string
}

export interface FreeChatStreamEvent {
  type: 'delta' | 'done' | 'error' | 'task_card' | 'task_card_progress'
  kind?: string
  content?: string
  answer?: string
  message?: string
  sources?: ConversationSource[]
  card_id?: string
  task_id?: string
  status?: TaskCardStreamStatus
  title?: string
  progress?: number | null
  details?: string
  call_id?: string
  params?: unknown
  ts?: string
}

export interface FreeChatStreamHandlers {
  onDelta: (chunk: string) => void
  onDone: (payload: { answer: string; sources: ConversationSource[] }) => void
  onError: (message: string) => void
  onTaskCard?: (event: TaskCardStreamEvent) => void
  onTaskCardProgress?: (event: TaskCardProgressStreamEvent) => void
  onParameterRequest?: (event: ParameterRequestStreamEvent) => void
}

export const askFreeChat = async (data: FreeChatPayload): Promise<FreeChatResponse> => {
  const session = data.conversation_id || (await createAgentSession()).data.id
  const input: {
    text: string
    attachments?: Array<{ type: string; content: string }>
    context_refs?: ConversationContextRef[]
  } = {
    text: data.question,
  }
  if (data.asset_content) {
    input.attachments = [{ type: 'text', content: data.asset_content }]
  }
  if (data.context_refs?.length) {
    input.context_refs = data.context_refs
  }
  const turn = await startAgentTurn(session, {
    input,
    model: data.model_name,
    linked_task_id: data.linked_task_id,
    asset_content: data.asset_content,
    context_refs: data.context_refs,
  })
  let answer = ''
  for await (const event of streamAgentEvents(turn.data.turn_id)) {
    const payload = event.payload || {}
    if (event.type === 'message.delta') answer += String(payload.delta || payload.content || '')
    if (event.type === 'turn.failed' || event.type === 'turn.cancelled') {
      throw new Error(String((payload.error as { message?: string } | undefined)?.message || 'Agent turn failed'))
    }
  }
  return { answer, sources: [] }
}

const isTaskCardStatus = (value: unknown): value is TaskCardStreamStatus =>
  value === 'PENDING' ||
  value === 'RUNNING' ||
  value === 'SUCCESS' ||
  value === 'FAILED' ||
  value === 'CANCELED'

export const streamFreeChat = async (
  data: FreeChatPayload,
  handlers: FreeChatStreamHandlers,
) => {
  if (isDemoMode()) {
    await demoStreamFreeChat(data, handlers)
    return
  }
  const session = data.conversation_id || (await createAgentSession()).data.id
  const input: {
    text: string
    attachments?: Array<{ type: string; content: string }>
    context_refs?: ConversationContextRef[]
  } = {
    text: data.question,
  }
  if (data.asset_content) {
    input.attachments = [{ type: 'text', content: data.asset_content }]
  }
  if (data.context_refs?.length) {
    input.context_refs = data.context_refs
  }
  const turn = await startAgentTurn(session, {
    input,
    model: data.model_name,
    linked_task_id: data.linked_task_id,
    asset_content: data.asset_content,
    context_refs: data.context_refs,
  })
  let answer = ''
  for await (const event of streamAgentEvents(turn.data.turn_id)) {
      const eventPayload = event.payload || {}
      const payload = {
        ...eventPayload,
        type: event.type === 'message.delta' ? 'delta' : event.type === 'turn.succeeded' ? 'done' : event.type === 'turn.failed' || event.type === 'turn.cancelled' ? 'error' : event.type,
        content: eventPayload.delta || eventPayload.content,
      } as FreeChatStreamEvent

      // parameter_request 在 payload 顶层用 kind 区分，没有 type 字段
      if (payload.kind === 'parameter_request' && handlers.onParameterRequest) {
        handlers.onParameterRequest({
          kind: 'parameter_request',
          call_id: String(payload.call_id || ''),
          params: Array.isArray(payload.params) ? (payload.params as ParameterRequestStreamEvent['params']) : [],
          ts: payload.ts,
        })
        continue
      }

      if (payload.type === 'delta' && payload.content) {
        answer += payload.content
        handlers.onDelta(payload.content)
      } else if (payload.type === 'done') {
        handlers.onDone({
          answer: payload.answer || answer,
          sources: payload.sources || [],
        })
      } else if (payload.type === 'error') {
        handlers.onError(String(payload.message || '聊天失败，请重试'))
      } else if (payload.type === 'task_card' && handlers.onTaskCard) {
        const status: TaskCardStreamStatus = isTaskCardStatus(payload.status)
          ? payload.status
          : 'PENDING'
        handlers.onTaskCard({
          type: 'task_card',
          card_id: String(payload.card_id || ''),
          kind: String(payload.kind || ''),
          task_id: payload.task_id ? String(payload.task_id) : undefined,
          status,
          title: String(payload.title || ''),
          progress: typeof payload.progress === 'number' ? payload.progress : null,
        })
      } else if (payload.type === 'task_card_progress' && handlers.onTaskCardProgress) {
        const status: TaskCardStreamStatus = isTaskCardStatus(payload.status)
          ? payload.status
          : 'RUNNING'
        handlers.onTaskCardProgress({
          type: 'task_card_progress',
          card_id: String(payload.card_id || ''),
          status,
          progress: typeof payload.progress === 'number' ? payload.progress : null,
          details: typeof payload.details === 'string' ? payload.details : undefined,
        })
      }
      // 其他未知 type 静默忽略，保证旧前端不 crash
  }
}
