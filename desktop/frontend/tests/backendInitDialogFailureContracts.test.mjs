import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(path.join(root, 'src/components/BackendInitDialog.tsx'), 'utf8')

assert.match(
  source,
  /interface\s+Props\s*\{[\s\S]*failureKind\??:\s*'runtime'\s*\|\s*'backend'[\s\S]*onRetry:\s*\(\)\s*=>\s*void[\s\S]*onClose:\s*\(\)\s*=>\s*void[\s\S]*\}/,
  '失败提示弹窗必须接收 failureKind/onRetry/onClose，以支持 runtime/backend 失败的分流提示与重试',
)

assert.match(
  source,
  /const\s+title\s*=\s*failureKind\s*===\s*'runtime'[\s\S]*桌面运行时[\s\S]*后端/,
  'BackendInitDialog 必须按 failureKind 区分 runtime 失败标题和 backend 失败标题',
)

assert.match(
  source,
  /const\s+message\s*=\s*failureKind\s*===\s*'runtime'[\s\S]*桌面环境[\s\S]*后端服务/,
  'BackendInitDialog 必须按 failureKind 区分 runtime 注入失败与 backend 探测失败的说明文案',
)

assert.match(
  source,
  /<Button[^>]*onClick=\{onRetry\}[^>]*>\s*重试\s*<\/Button>/,
  'BackendInitDialog 在失败态必须提供“重试”按钮',
)

assert.match(
  source,
  /<Button[^>]*onClick=\{onClose\}[^>]*>\s*关闭\s*<\/Button>/,
  'BackendInitDialog 在失败态必须提供“关闭”按钮，实现非阻塞提示',
)

assert.doesNotMatch(
  source,
  /<Loader2/,
  '任务2要求失败后展示非阻塞提示，不应继续沿用纯加载中的转圈弹窗',
)
