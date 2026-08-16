import { getRuntimeApiBaseUrl } from '@/utils/runtime'

export const AGENT_SCHEMA_VERSION = '1'

export type AgentEvent = {
  event_id: string
  turn_id: string
  sequence: number
  type: string
  payload?: Record<string, unknown>
}

export type AgentTurnRequest = {
  input: string
  model?: string
  idempotency_key?: string
  linked_task_id?: string
  asset_content?: string
  context_refs?: unknown[]
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

export const cancelAgentTurn = (turnId: string) => json(`/agent/v1/turns/${turnId}/cancel`, { method: 'POST' })
export const steerAgentTurn = (turnId: string, input: string) =>
  json(`/agent/v1/turns/${turnId}/steer`, { method: 'POST', body: JSON.stringify({ input }) })
export const resolveAgentApproval = (approvalId: string, approved: boolean) =>
  json(`/agent/v1/approvals/${approvalId}`, { method: 'POST', body: JSON.stringify({ approved }) })

export async function* streamAgentEvents(turnId: string, afterSequence = -1): AsyncGenerator<AgentEvent> {
  const response = await fetch(`${baseUrl()}/agent/v1/turns/${turnId}/events?after_sequence=${afterSequence}`, {
    headers: { Accept: 'text/event-stream' },
  })
  if (!response.ok || !response.body) throw new Error(`Agent 事件请求失败: ${response.status}`)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    for (const frame of frames) {
      const line = frame.split('\n').find(item => item.startsWith('data:'))
      if (!line) continue
      const event = JSON.parse(line.slice(5).trim()) as AgentEvent
      if (event.type && event.type !== 'agent.schema') yield event
    }
  }
}

export const getModelPreference = (sessionId: string) => json(`/agent/v1/sessions/${sessionId}/model-preference`)
export const setModelPreference = (sessionId: string, payload: { default_model_id?: string; fallback_models?: string[] }) =>
  json(`/agent/v1/sessions/${sessionId}/model-preference`, { method: 'PUT', body: JSON.stringify(payload) })
