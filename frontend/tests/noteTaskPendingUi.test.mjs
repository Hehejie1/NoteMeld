import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const progressStepsSource = await readFile(path.join(root, 'src/pages/HomePage/progressSteps.ts'), 'utf8')
const taskStoreSource = await readFile(path.join(root, 'src/store/taskStore/index.ts'), 'utf8')
const messageRenderersSource = await readFile(
  path.join(root, 'src/pages/HomePage/messageRenderers.tsx'),
  'utf8',
)

assert.match(
  progressStepsSource,
  /label:\s*['"]等待执行['"],\s*key:\s*['"]PENDING['"],\s*matches:\s*\[['"]PENDING['"]\]/,
  'PENDING 必须作为“等待执行”独立步骤展示，不能冒充“解析链接”',
)

assert.match(
  taskStoreSource,
  /\|\s*['"]CANCELED['"]/,
  '前端任务状态类型必须支持后端返回的 CANCELED',
)

assert.match(
  taskStoreSource,
  /\|\s*['"]NOT_FOUND['"]/,
  '前端任务状态类型必须支持后端返回的 NOT_FOUND',
)

assert.match(
  messageRenderersSource,
  /handleCopyLogId/,
  '生成中任务卡片必须提供复制日志 ID 的处理函数，方便通过 task_id 查询后端日志',
)

assert.match(
  messageRenderersSource,
  /navigator\.clipboard\.writeText\(retryTaskId\)/,
  '复制日志 ID 必须复制当前 note_progress 消息 meta.task_id，不能复制 URL 或展示文案',
)

assert.match(
  messageRenderersSource,
  /toast\.success\(`\$\{retryTaskId\} 复制成功`\)/,
  '复制日志 ID 成功后必须提示“{task_id} 复制成功”，方便用户确认复制内容',
)

assert.match(
  messageRenderersSource,
  /aria-label=["']复制日志 ID["']/,
  '生成中任务卡片标题旁必须有可访问的复制日志 ID 按钮',
)
