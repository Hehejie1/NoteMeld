import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(path.join(root, 'src/hooks/useCheckBackend.ts'), 'utf8')

const maxRetries = Number(source.match(/const\s+MAX_RETRIES\s*=\s*(\d+)/)?.[1])
const retryInterval = Number(source.match(/const\s+RETRY_INTERVAL\s*=\s*(\d+)/)?.[1])

assert.ok(Number.isFinite(maxRetries), 'useCheckBackend 必须显式定义 MAX_RETRIES')
assert.ok(Number.isFinite(retryInterval), 'useCheckBackend 必须显式定义 RETRY_INTERVAL')
assert.ok(
  maxRetries * retryInterval >= 60_000,
  '桌面后端首次启动可能需要 PyInstaller/模型/SQLite 初始化，前端静默等待窗口不能少于 60 秒',
)
