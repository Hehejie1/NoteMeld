import type { ConversationMessage } from './index'
import type { AgentEvent } from '@/services/agent'

export type AgentReducerState = {
  messages: ConversationMessage[]
  lastSequence: number
  turnId?: string
  terminal?: 'succeeded' | 'failed' | 'cancelled' | 'interrupted'
  error?: string
}

const now = () => new Date().toISOString()

export function reduceAgentEvent(state: AgentReducerState, event: AgentEvent): AgentReducerState {
  if (!event.turn_id || (state.turnId && event.turn_id !== state.turnId)) return state
  if (!Number.isInteger(event.sequence) || event.sequence < 0) return state
  if (event.sequence <= state.lastSequence) return state
  const scopedState = state.turnId ? state : { ...state, turnId: event.turn_id }
  const payload = event.payload || {}
  const timestamp = now()
  if (event.type === 'message.delta') {
    const delta = typeof payload.delta === 'string' ? payload.delta : ''
    if (!delta) return { ...scopedState, lastSequence: event.sequence }
    const previous = scopedState.messages[scopedState.messages.length - 1]
    if (previous?.role === 'assistant' && previous.isStreaming) {
      return {
        ...scopedState,
        lastSequence: event.sequence,
        messages: [...scopedState.messages.slice(0, -1), { ...previous, content: previous.content + delta, updatedAt: timestamp }],
      }
    }
    const message: ConversationMessage = {
      id: `${event.turn_id}:${event.sequence}`,
      role: 'assistant',
      message_type: 'assistant_text',
      content: delta,
      createdAt: timestamp,
      updatedAt: timestamp,
      isStreaming: true,
    }
    return { ...scopedState, lastSequence: event.sequence, messages: [...scopedState.messages, message] }
  }
  if (event.type === 'message.completed') {
    const previous = scopedState.messages[scopedState.messages.length - 1]
    if (previous?.role === 'assistant' && previous.isStreaming) {
      return { ...scopedState, lastSequence: event.sequence, messages: [...scopedState.messages.slice(0, -1), { ...previous, isStreaming: false, updatedAt: timestamp }] }
    }
  }
  if (event.type === 'turn.failed' || event.type === 'turn.cancelled' || event.type === 'turn.interrupted' || event.type === 'turn.succeeded') {
    const error = payload.error
    return {
      ...scopedState,
      lastSequence: event.sequence,
      terminal: event.type.slice(5) as AgentReducerState['terminal'],
      error: typeof error === 'object' && error && 'message' in error ? String(error.message) : undefined,
      messages: scopedState.messages.map(message => message.isStreaming ? { ...message, isStreaming: false, updatedAt: timestamp } : message),
    }
  }
  return { ...scopedState, lastSequence: event.sequence }
}
