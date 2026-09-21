import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(path.join(root, 'src/contexts/BackendInitContext.tsx'), 'utf8')

assert.match(
  source,
  /export\s+type\s+RuntimeInitStatus\s*=\s*'checking'\s*\|\s*'ready'\s*\|\s*'failed'/,
  '初始化上下文必须单独暴露 runtime 状态，避免把桌面运行时注入和后端探测混成一个阶段',
)

assert.match(
  source,
  /export\s+type\s+BackendInitFailureKind\s*=\s*'runtime'\s*\|\s*'backend'/,
  '初始化上下文必须显式区分 runtime/backend 两类失败，供弹窗和重试逻辑正确分流',
)

assert.match(
  source,
  /runtimeStatus:\s*RuntimeInitStatus[\s\S]*runtimeReady:\s*boolean[\s\S]*backendStatus:\s*BackendInitStatus[\s\S]*backendReady:\s*boolean[\s\S]*failureKind:\s*BackendInitFailureKind\s*\|\s*null/,
  'BackendInitContext 必须同时暴露 runtimeReady/backendReady/failureKind，供页面区分运行时注入失败和后端失败',
)

assert.match(
  source,
  /export\s+const\s+BackendInitProvider/,
  '前端必须提供全局 BackendInitProvider，统一分发 backend init 状态',
)

assert.match(
  source,
  /export\s+const\s+useBackendInitContext/,
  '前端必须提供 useBackendInitContext，供各页面读取全局 backend init 状态',
)

assert.match(
  source,
  /const\s+checkNow\s*=\s*useCallback\(async\s*\(\)\s*=>\s*\{[\s\S]*if\s*\(\s*runtimeStatus\s*!==\s*'ready'\s*\)[\s\S]*runtimeInit\.checkNow\(\)[\s\S]*backendInit\.checkNow\(\)/,
  '全局重试入口必须先处理 runtime 失败，再在 runtime ready 后转向 backend 重试',
)
