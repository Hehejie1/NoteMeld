import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(path.join(root, 'src/hooks/useCheckBackend.ts'), 'utf8')

assert.doesNotMatch(
  source,
  /import\s+request\s+from\s+['"]@\/utils\/request['"]/,
  '打包版后端初始化轮询不能使用全局 request；全局拦截器会在后端尚未 ready 时弹“请求失败”误报',
)

assert.match(
  source,
  /silentBackendGet/,
  '后端初始化轮询必须走静默健康检查，失败时只更新初始化弹窗状态，不弹 toast',
)
