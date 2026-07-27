import request from '@/utils/request'
import { getRuntimeApiBaseUrl } from '@/utils/runtime'
import type { ConversationMessage, ConversationSource } from '@/store/taskStore'

export interface FreeChatPayload {
  question: string
  history: Pick<ConversationMessage, 'role' | 'content'>[]
  provider_id: string
  model_name: string
  conversation_id?: string
  linked_task_id?: string
  use_wiki?: boolean
  asset_content?: string
}

export interface FreeChatResponse {
  answer: string
  sources: ConversationSource[]
}

export interface FreeChatStreamEvent {
  type: 'delta' | 'done' | 'error'
  content?: string
  answer?: string
  message?: string
  sources?: ConversationSource[]
}

export const askFreeChat = async (data: FreeChatPayload): Promise<FreeChatResponse> => {
  return await request.post('/chat/free', data)
}

export const streamFreeChat = async (
  data: FreeChatPayload,
  handlers: {
    onDelta: (chunk: string) => void
    onDone: (payload: { answer: string; sources: ConversationSource[] }) => void
    onError: (message: string) => void
  },
) => {
  const baseURL = String(getRuntimeApiBaseUrl() || import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
  const response = await fetch(`${baseURL}/chat/free/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })

  if (!response.ok || !response.body) {
    throw new Error(`聊天请求失败: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const events = buffer.split('\n\n')
    buffer = events.pop() || ''

    for (const rawEvent of events) {
      const dataLine = rawEvent
        .split('\n')
        .find(line => line.startsWith('data: '))
      if (!dataLine) continue
      const payload = JSON.parse(dataLine.slice(6)) as FreeChatStreamEvent
      if (payload.type === 'delta' && payload.content) {
        handlers.onDelta(payload.content)
      } else if (payload.type === 'done') {
        handlers.onDone({
          answer: payload.answer || '',
          sources: payload.sources || [],
        })
      } else if (payload.type === 'error') {
        handlers.onError(payload.message || '聊天失败，请重试')
      }
    }
  }
}
