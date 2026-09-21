import assert from 'node:assert/strict'
import { mergeConversationMessages } from './mergeConversationMessages.ts'

const serverMessages = [
  {
    id: 'user-1',
    role: 'user',
    message_type: 'user_input',
    content: '你是在干什么？',
    createdAt: '2026-05-23T11:56:06.778Z',
    updatedAt: '2026-05-23T11:56:06.778Z',
  },
]

const localMessages = [
  ...serverMessages,
  {
    id: 'assistant-streaming',
    role: 'assistant',
    message_type: 'assistant_text',
    content: '正在回答',
    createdAt: '2026-05-23T11:56:06.827Z',
    updatedAt: '2026-05-23T11:56:07.000Z',
    isStreaming: true,
  },
]

const merged = mergeConversationMessages(serverMessages, localMessages)

assert.equal(merged.length, 2)
assert.equal(merged[0].id, 'user-1')
assert.equal(merged[1].id, 'assistant-streaming')
assert.equal(merged[1].isStreaming, true)

console.log('mergeConversationMessages preserves local streaming assistant messages')
