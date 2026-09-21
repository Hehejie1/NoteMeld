import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(path.join(root, 'src/App.tsx'), 'utf8')
const mainSource = await readFile(path.join(root, 'src/main.tsx'), 'utf8')

assert.doesNotMatch(
  source,
  /import\s+\{\s*useCheckBackend\s*\}\s+from\s+['"]@\/hooks\/useCheckBackend\.ts['"]/,
  'App 不应继续直接依赖 useCheckBackend；任务2要求改为接入全局 BackendInitProvider',
)

assert.match(
  source,
  /import\s+\{\s*BackendInitProvider,\s*useBackendInitContext\s*\}\s+from\s+['"]@\/contexts\/BackendInitContext\.tsx['"]/,
  'App 必须接入 BackendInitProvider，并通过 useBackendInitContext 读取全局初始化状态',
)

assert.match(
  source,
  /const\s+\{\s*backendReady,\s*phase,\s*failureKind,\s*checkNow\s*\}\s*=\s*useBackendInitContext\(\)/,
  'WorkspaceApp 必须读取 backendReady/failureKind/checkNow，才能区分 runtime/backend 失败并正确路由重试',
)

assert.doesNotMatch(
  source,
  /if\s*\(\s*!initialized\s*\)\s*\{\s*return[\s\S]*<BackendInitDialog/,
  '任务2必须移除整页路由阻塞，不能再因为 initialized 为 false 而直接拦截整个工作区渲染',
)

assert.match(
  source,
  /return\s*\(\s*<>\s*<WorkspaceRoutes\s*\/>\s*<BackendInitDialog[\s\S]*<\/>\s*\)/,
  '任务2要求工作区路由始终渲染，BackendInitDialog 只能作为非阻塞提示附着在路由之上',
)

assert.match(
  source,
  /useEffect\(\(\)\s*=>\s*\{[\s\S]*if\s*\(\s*backendReady\s*\)\s*\{[\s\S]*systemCheck\(\)/,
  'systemCheck 必须等 backendReady 后再触发，避免 runtime/backend 尚未就绪时抢跑业务请求',
)

assert.match(
  source,
  /open=\{!!failureKind\s*&&\s*!dialogDismissed\}/,
  'BackendInitDialog 只能在存在 runtime/backend 失败时打开，不能继续把 checking/retrying 当失败态',
)

assert.match(
  source,
  /failureKind=\{failureKind(?:\s*\?\?\s*undefined)?\}/,
  'App 必须把 failureKind 透传给 BackendInitDialog，供弹窗区分 runtime/backend 失败文案',
)

assert.match(
  source,
  /<BackendInitProvider>\s*<RouterComponent>/,
  '顶层 App 必须用 BackendInitProvider 包裹路由树，使初始化状态全局可用',
)

assert.doesNotMatch(
  source,
  /const\s+RouterComponent\s*=\s*isDesktopEmbedded\(\)\s*\?\s*HashRouter\s*:\s*BrowserRouter/,
  '顶层路由器选择不能继续依赖 runtime 注入后的 isDesktopEmbedded()，否则页面先渲染后会拿到错误路由模式',
)

assert.match(
  source,
  /const\s+RouterComponent\s*=\s*shouldUseDesktopRuntime\(\)\s*\?\s*HashRouter\s*:\s*BrowserRouter/,
  '桌面环境的首屏路由模式必须基于 shouldUseDesktopRuntime() 判断，避免等待 runtime 注入后才知道自己是桌面端',
)

assert.doesNotMatch(
  mainSource,
  /initializeDesktopRuntime\(\)\.finally\(\(\)\s*=>\s*\{/,
  'React 首屏挂载不能继续等待 runtime 注册 promise 结束后才执行',
)

assert.match(
  mainSource,
  /createRoot\(rootElement\)\.render\(/,
  'main.tsx 必须直接挂载 React 应用，保证首屏立即可见',
)
