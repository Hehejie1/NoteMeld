import assert from 'node:assert/strict'
import { access, readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const runtimeSource = await readFile(path.join(root, 'src/utils/runtime.ts'), 'utf8')
const requestSource = await readFile(path.join(root, 'src/utils/request.ts'), 'utf8')
const markdownViewerSource = await readFile(
  path.join(root, 'src/pages/HomePage/components/MarkdownViewer.tsx'),
  'utf8',
)
const videoBannerSource = await readFile(
  path.join(root, 'src/pages/HomePage/components/VideoBanner.tsx'),
  'utf8',
)
const appLayoutSource = await readFile(
  path.join(root, 'src/layouts/AppLayout.tsx'),
  'utf8',
)
const landingPageSource = await readFile(
  path.join(root, 'src/pages/LandingPage/index.tsx'),
  'utf8',
)
const aboutPageSource = await readFile(
  path.join(root, 'src/pages/AboutPage.tsx'),
  'utf8',
)
const dataMigrationSource = await readFile(
  path.join(root, 'src/pages/SettingPage/DataMigration.tsx'),
  'utf8',
)
const deviceConnectivitySource = await readFile(
  path.join(root, 'src/pages/Applications/DeviceConnectivityPanel.tsx'),
  'utf8',
)
await access(path.join(root, 'public/notemeld-logo.png'))

assert.match(
  runtimeSource,
  /document\.createElement\(['"]a['"]\)/,
  '浏览器端外链应通过临时 a 标签打开新页面，避免双跳转',
)

assert.doesNotMatch(
  runtimeSource,
  /window\.location\.assign\(url\)/,
  '浏览器端外链不应回退到当前页强跳转',
)

assert.match(
  runtimeSource,
  /document\.readyState\s*===\s*['"]complete['"]/,
  'desktop runtime 注册必须判断页面是否已完成加载',
)

assert.match(
  runtimeSource,
  /window\.addEventListener\(\s*['"]load['"]/,
  'desktop runtime 注册必须绑定 page load 事件作为启动时机',
)

assert.match(
  runtimeSource,
  /RUNTIME_REGISTER_MAX_RETRIES\s*=\s*3/,
  'desktop runtime 自动重试次数必须固定为 3 次',
)

assert.match(
  runtimeSource,
  /RUNTIME_REGISTER_RETRY_DELAY_MS\s*=\s*1000/,
  'desktop runtime 自动重试间隔必须固定为 1000ms',
)

assert.match(
  requestSource,
  /getRuntimeApiBaseUrl\(\)\s*\|\|\s*import\.meta\.env\.VITE_API_BASE_URL\s*\|\|\s*'\/api'/,
  '请求层必须优先读取 runtime 注入的 API 基址',
)

assert.match(
  requestSource,
  /config\.baseURL\s*=\s*resolveApiBaseUrl\(\)/,
  'axios 请求拦截器必须动态写入 baseURL，避免桌面端静态值漂移',
)

assert.match(
  runtimeSource,
  /sessionToken\?:\s*string/,
  'desktop runtime 类型必须包含 sessionToken 字段',
)

assert.match(
  runtimeSource,
  /getRuntimeSessionToken/,
  'runtime 必须提供读取桌面 session token 的 helper',
)

assert.match(
  requestSource,
  /getRuntimeSessionToken/,
  '请求层必须读取 runtime session token',
)

assert.match(
  requestSource,
  /X-NoteMeld-Session/,
  '桌面请求必须自动携带 X-NoteMeld-Session 头',
)

assert.match(
  markdownViewerSource,
  /getRuntimeApiBaseUrl,\s*openExternalUrl/,
  'MarkdownViewer 必须通过 runtime helper 处理基址和外链',
)

assert.match(
  videoBannerSource,
  /getRuntimeApiBaseUrl\(\)\s*\|\|\s*import\.meta\.env\.VITE_API_BASE_URL\s*\|\|\s*'\/api'/,
  '视频封面代理地址必须优先使用 runtime 或 VITE_API_BASE_URL',
)

assert.match(
  appLayoutSource,
  /className="nm-session-section"/,
  '左侧笔记列表外层必须限制高度并交给内部滚动容器处理',
)

assert.match(
  appLayoutSource,
  /className="nm-session-scroll"/,
  '左侧笔记列表 ScrollArea 必须占用剩余高度并支持内部滚动',
)

assert.match(
  appLayoutSource,
  /className="nm-session-list"/,
  '左侧笔记列表内容容器必须限制宽度，避免长标题撑开列表',
)

assert.match(
  appLayoutSource,
  /className={cn\('nm-session-row'/,
  '左侧笔记列表按钮必须限制 flex 宽度，让标题可以按剩余空间省略',
)

assert.match(
  appLayoutSource,
  /<span>\{title\}<\/span>/,
  '左侧笔记标题文本必须使用 w-0 flex-1 truncate 触发省略号',
)

assert.match(
  appLayoutSource,
  /className="nm-sidebar-footer"/,
  '侧边栏 GitHub 区块必须固定占位并使用白色背景避免和列表重叠',
)

assert.match(
  appLayoutSource,
  /const logo = '\/notemeld-logo\.png'/,
  '应用内侧边栏 logo 必须使用桌面 PNG 静态资源，避免和 Tauri 打包图标链路不一致',
)

assert.match(
  landingPageSource,
  /src="\/notemeld-logo\.png"/,
  '首页品牌 logo 必须使用和桌面一致的 PNG 静态资源',
)

assert.match(
  aboutPageSource,
  /src="\/notemeld-logo\.png"/,
  '关于页品牌 logo 必须使用和桌面一致的 PNG 静态资源',
)

assert.match(
  dataMigrationSource,
  /showStoragePressureAlert/,
  '导入迁移包遇到存储空间或内存不足时必须弹窗提示用户',
)

assert.match(deviceConnectivitySource, /get_desktop_device_id/)
assert.match(deviceConnectivitySource, /openDeviceKeyMaterial/)
assert.match(deviceConnectivitySource, /listDevices/)
assert.match(deviceConnectivitySource, /heartbeat/)
assert.match(deviceConnectivitySource, /bootstrap_cloud_host/)
assert.match(deviceConnectivitySource, /LAN 优先，Relay 回退/)
