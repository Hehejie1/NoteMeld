import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(path.join(root, 'src/App.tsx'), 'utf8')

assert.match(
  source,
  /const\s+\{\s*backendReady\s*\}\s*=\s*useBackendInitContext\(\)[\s\S]*useTaskPolling\(3000,\s*shouldPollTasks\s*&&\s*backendReady\)/,
  '工作区轮询必须等 backendReady 后再启动，避免桌面端首次启动后端未就绪时抢跑业务请求并弹“请求失败”',
)
