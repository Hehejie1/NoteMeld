import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(path.join(root, 'src/services/chat.ts'), 'utf8')

assert.match(source, /streamAgentEvents\(/, '流式聊天必须消费 Agent v1 事件流')
assert.match(source, /startAgentTurn\(/, '流式聊天必须通过 Agent v1 创建 turn')

assert.doesNotMatch(
  source,
  /chat\/free\/stream/,
  '前端不得再调用旧 chat/free/stream 执行入口',
)
