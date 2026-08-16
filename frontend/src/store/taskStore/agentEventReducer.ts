import type { ConversationMessage } from './index'
import type { AgentEvent } from '@/services/agent'

export type AgentReducerState = {
  messages: ConversationMessage[]
  lastSequence: number
  terminal?: 'succeeded' | 'failed' | 'cancelled' | 'interrupted'
  error?: string
}

const now = () => new Date().toISOString()

export function reduceAgentEvent(state: AgentReducerState, event: AgentEvent): AgentReducerState {
  if (event.sequence <= state.lastSequence) return state
  const payload = event.payload || {}
  const timestamp = now()
  if (event.type === 'message.delta') {
    const delta = typeof payload.delta === 'string' ? payload.delta : ''
    if (!delta) return { ...state, lastSequence: event.sequence }
    const previous = state.messages[state.messages.length - 1]
    if (previous?.role === 'assistant' && previous.isStreaming) {
      return {
        ...state,
        lastSequence: event.sequence,
        messages: [...state.messages.slice(0, -1), { ...previous, content: previous.content + delta, updatedAt: timestamp }],
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
    return { ...state, lastSequence: event.sequence, messages: [...state.messages, message] }
  }
  if (event.type === 'message.completed') {
    const previous = state.messages[state.messages.length - 1]
    if (previous?.role === 'assistant') {
      return { ...state, lastSequence: event.sequence, messages: [...state.messages.slice(0, -1), { ...previous, isStreaming: false, updatedAt: timestamp }] }
    }
  }
  if (event.type === 'turn.failed' || event.type === 'turn.cancelled' || event.type === 'turn.interrupted' || event.type === 'turn.succeeded') {
    const error = payload.error
    return {
      ...state,
      lastSequence: event.sequence,
      terminal: event.type.slice(5) as AgentReducerState['terminal'],
      error: typeof error === 'object' && error && 'message' in error ? String(error.message) : undefined,
      messages: state.messages.map(message => message.isStreaming ? { ...message, isStreaming: false, updatedAt: timestamp } : message),
    }
  }
  return { ...state, lastSequence: event.sequence }
}
