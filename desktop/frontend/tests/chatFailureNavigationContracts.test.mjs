import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(
  path.join(root, 'src/pages/HomePage/components/ChatComposer.tsx'),
  'utf8',
)

const turnBlock = source.match(
  /const turn = await startAgentTurn\([\s\S]*?for await \(const event of streamAgentEvents\(turn\.data\.turn_id\)\)/,
)

assert.ok(turnBlock, '聊天提交必须创建 Agent turn 并消费事件流')
assert.match(
  source,
  /navigate\(`\/notes\/\$\{conversationId\}`\)/,
  'turn 被接受后必须立即进入会话，不能等待模型流结束',
)
assert.match(
  source,
  /event\.type === 'message\.completed'/,
  '聊天必须消费 Agent 的 message.completed 终态正文',
)
assert.match(
  source,
  /payload\.answer \|\| payload\.content/,
  '聊天必须从 turn.succeeded 终态 payload 兜底读取正文',
)

assert.doesNotMatch(
  source,
  /await runChatRequest\([\s\S]*?\)\s*\n\s*clearContextRefs\(\)\s*\n\s*navigate\(`\/notes\//,
  'submitChat 不能把导航放在完整流式请求结束之后',
)
