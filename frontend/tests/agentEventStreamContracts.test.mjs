import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const agentSource = await readFile(path.join(root, 'src/services/agent.ts'), 'utf8')
const reducerSource = await readFile(path.join(root, 'src/store/taskStore/agentEventReducer.ts'), 'utf8')

assert.match(agentSource, /buffer \+= decoder\.decode\(\)/, 'SSE 必须在 EOF flush UTF-8 decoder')
assert.match(agentSource, /if \(buffer\.trim\(\)\) yield\* parseFrame\(buffer\)/, 'SSE 必须解析无尾部分隔符的最后一帧')
assert.match(agentSource, /eventTurnId !== turnId/, 'SSE 必须拒绝其他 Turn 的事件')
assert.match(agentSource, /!Number\.isInteger\(sequence\) \|\| sequence < 0/, 'SSE 必须拒绝非法 sequence')
assert.match(reducerSource, /state\.turnId && event\.turn_id !== state\.turnId/, 'reducer 必须隔离跨 Turn 事件')
assert.match(reducerSource, /previous\?\.role === 'assistant' && previous\.isStreaming/, '完成事件不能修改已完成消息')

console.log('agent event stream guards preserve turn and frame boundaries')
