import { getRuntimeApiBaseUrl } from '@/utils/runtime'

export const AGENT_SCHEMA_VERSION = '1'

export type AgentEvent = {
  event_id: string
  turn_id: string
  sequence: number
  type: string
  payload?: Record<string, unknown>
}

export type AgentContextRef = {
  type: string
}

export type AgentAttachment = {
  type: string
  content: string
  [key: string]: unknown
}

export type AgentTurnInput = {
  text: string
  attachments?: AgentAttachment[]
  context_refs?: AgentContextRef[]
}

export type AgentTurnRequest = {
  input: string | AgentTurnInput
  model?: string
  idempotency_key?: string
  linked_task_id?: string
  asset_content?: string
  context_refs?: AgentContextRef[]
}

const baseUrl = () => String(getRuntimeApiBaseUrl() || import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl()}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  if (!response.ok) throw new Error(`Agent 请求失败: ${response.status}`)
  return (await response.json()) as T
}

export const startAgentTurn = (sessionId: string, request: AgentTurnRequest) =>
  json<{ data: { turn_id: string; session_id: string; status: string } }>(`/agent/v1/sessions/${sessionId}/turns`, {
    method: 'POST',
    body: JSON.stringify(request),
  })

export const createAgentSession = (sessionId?: string) =>
  json<{ data: { id: string } }>('/agent/v1/sessions', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, title: 'NoteMeld Agent' }),
  })

export const cancelAgentTurn = (turnId: string) => json(`/agent/v1/turns/${turnId}/cancel`, { method: 'POST' })
export const steerAgentTurn = (turnId: string, input: string) =>
  json(`/agent/v1/turns/${turnId}/steer`, { method: 'POST', body: JSON.stringify({ input }) })
export const resolveAgentApproval = (
  approvalId: string,
  decision: 'approve' | 'deny' | boolean,
) =>
  json(`/agent/v1/approvals/${approvalId}`, {
    method: 'POST',
    body: JSON.stringify(
      typeof decision === 'boolean' ? { approved: decision } : { decision },
    ),
  })

export async function* streamAgentEvents(turnId: string, afterSequence = -1): AsyncGenerator<AgentEvent> {
  const headers: Record<string, string> = { Accept: 'text/event-stream' }
  if (afterSequence >= 0) headers['Last-Event-ID'] = String(afterSequence)
  const response = await fetch(`${baseUrl()}/agent/v1/turns/${turnId}/events?after_sequence=${afterSequence}`, {
    headers,
  })
  if (!response.ok || !response.body) throw new Error(`Agent 事件请求失败: ${response.status}`)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let lastEventId: number | null = null
  const parseFrame = function* (frame: string): Generator<AgentEvent> {
      const dataLines: string[] = []
      let frameEventType = 'agent.event'
      const lines = frame.split('\n')
      for (const line of lines) {
        if (!line || line.startsWith(':')) continue
        if (line.startsWith('event:')) frameEventType = line.slice(6).trim() || 'agent.event'
        else if (line.startsWith('id:')) lastEventId = Number.parseInt(line.slice(3).trim(), 10)
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (!dataLines.length) return
      const eventText = dataLines.join('\n')
      if (!eventText) return
      let event: AgentEvent
      try {
        event = JSON.parse(eventText) as AgentEvent
      } catch {
        return
      }
      const sequence = event.sequence ?? (Number.isFinite(lastEventId) ? lastEventId : -1)
      const eventTurnId = event.turn_id || turnId
      const eventType = event.type || frameEventType
      if (eventType === 'agent.schema' || eventTurnId !== turnId || !Number.isInteger(sequence) || sequence < 0) return
      yield {
        ...event,
        type: eventType,
        event_id: event.event_id || String(lastEventId ?? sequence),
        sequence,
        turn_id: eventTurnId,
      }
    }
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        buffer += decoder.decode()
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() || ''
      for (const frame of frames) yield* parseFrame(frame)
    }
    if (buffer.trim()) yield* parseFrame(buffer)
  } finally {
    reader.releaseLock()
  }
}

export const getModelPreference = (sessionId: string) => json(`/agent/v1/sessions/${sessionId}/model-preference`)
export const setModelPreference = (sessionId: string, payload: { default_model_id?: string; fallback_models?: string[] }) =>
  json(`/agent/v1/sessions/${sessionId}/model-preference`, { method: 'PUT', body: JSON.stringify(payload) })

export const listAgentSessions = () => json<{ data: Array<{ id: string }> }>('/agent/v1/sessions')
export const getAgentTurnDiagnostics = (turnId: string) =>
  json<{ data: { turn: Record<string, unknown>; events: AgentEvent[]; event_count: number; last_sequence: number } }>(`/agent/v1/turns/${encodeURIComponent(turnId)}/diagnostics`)
