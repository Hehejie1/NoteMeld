import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(path.join(root, 'src/layouts/AppLayout.tsx'), 'utf8')

assert.match(
  source,
  /import\s+\{\s*useBackendInitContext\s*\}\s+from\s+['"]@\/contexts\/BackendInitContext\.tsx['"]/,
  'AppLayout 必须接入全局 backend init context，才能按后端状态对侧边栏局部降级',
)

assert.match(
  source,
  /const\s+\{\s*backendReady\s*\}\s*=\s*useBackendInitContext\(\)/,
  'AppLayout 需要读取 backendReady 以控制会话列表加载时机，不能再混用 runtime/backend 状态',
)

assert.match(
  source,
  /if\s*\(\s*backendReady\s*\)\s*\{[\s\S]*loadConversations\(\)/,
  '任务3要求 backend 未就绪时延后加载会话列表，AppLayout 只能在 ready 后触发 loadConversations()',
)

assert.doesNotMatch(
  source,
  /const\s+\{\s*initialized,\s*status\s*\}\s*=\s*useBackendInitContext\(\)/,
  'AppLayout 不应继续基于 initialized/status 判断，否则 runtime/backend 语义仍然耦合',
)

assert.match(
  source,
  /const\s+shouldDeferConversations\s*=\s*!backendReady/,
  '侧边栏降级条件必须只由 backendReady 决定，避免 runtime/backend 状态交叉导致误判',
)

assert.match(
  source,
  /后端尚未就绪，笔记列表将在连接成功后自动加载/,
  '侧边栏在 backend 未就绪时必须展示明确降级提示，而不是空列表或整页阻塞',
)
