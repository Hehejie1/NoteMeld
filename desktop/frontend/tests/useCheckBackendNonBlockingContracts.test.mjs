import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(path.join(root, 'src/hooks/useCheckBackend.ts'), 'utf8')

assert.match(
  source,
  /export\s+type\s+UseCheckBackendOptions\s*=\s*\{[\s\S]*runtimeReady:\s*boolean[\s\S]*\}/,
  'useCheckBackend 必须显式依赖 runtimeReady，而不是在 hook 内部偷偷初始化 runtime',
)

assert.match(
  source,
  /export\s+const\s+useCheckBackend\s*=\s*\(\s*\{\s*runtimeReady\s*\}\s*:\s*UseCheckBackendOptions\s*\)/,
  'useCheckBackend 入口必须接收 runtimeReady 参数，明确 backend 探测的前置依赖',
)

assert.match(
  source,
  /useEffect\(\(\)\s*=>\s*\{[\s\S]*if\s*\(\s*!runtimeReady\s*\)\s*\{[\s\S]*return[\s\S]*\}[\s\S]*check\(\)/,
  'backend 探测 effect 必须等 runtimeReady 后再启动，避免 runtime 未注入时就发起 /sys_check',
)

assert.doesNotMatch(
  source,
  /initializeDesktopRuntime/,
  'useCheckBackend 不得再直接初始化 runtime；runtime 与 backend 状态必须拆分',
)

assert.match(
  source,
  /const\s+RETRY_INTERVAL\s*=\s*3000/,
  'backend 探测自动重试间隔必须固定为 3000ms，避免失败后长时间卡在等待状态',
)

assert.match(
  source,
  /export\s+type\s+UseCheckBackendResult\s*=\s*\{[\s\S]*status:\s*BackendInitStatus[\s\S]*blocking:\s*boolean[\s\S]*initialized:\s*boolean[\s\S]*phase:\s*BackendCheckPhase[\s\S]*retryCount:\s*number[\s\S]*checkNow:\s*\(\)\s*=>\s*Promise<void>[\s\S]*\}/,
  'useCheckBackend 仍必须返回非阻塞状态接口，供全局 provider 组合 runtime/backend 状态',
)
