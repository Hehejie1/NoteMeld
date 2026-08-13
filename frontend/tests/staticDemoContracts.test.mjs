import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const read = file => readFile(path.join(root, file), 'utf8')

const [modeSource, contextSource, mainSource, requestSource, chatSource, desktopSource, updaterSource, videoBannerSource] = await Promise.all([
  read('src/demo/mode.ts').catch(() => ''),
  read('src/contexts/BackendInitContext.tsx'),
  read('src/main.tsx'),
  read('src/utils/request.ts'),
  read('src/services/chat.ts'),
  read('src/services/desktopRuntime.ts'),
  read('src/services/desktopUpdater.ts'),
  read('src/pages/HomePage/components/VideoBanner.tsx'),
])

assert.match(
  modeSource,
  /import\.meta\.env\.VITE_NOTEMELD_DEMO\s*===\s*['"]true['"]/,
  'demo mode must require the explicit compile-time flag',
)

assert.match(
  requestSource,
  /isDemoMode\(\)[\s\S]*createDemoAxiosAdapter/,
  'Axios requests must use the in-browser adapter in demo mode',
)
assert.match(
  chatSource,
  /if\s*\(isDemoMode\(\)\)[\s\S]*demoStreamFreeChat/,
  'streaming chat must delegate before fetch in demo mode',
)
assert.match(
  desktopSource,
  /if\s*\(isDemoMode\(\)\)[\s\S]*demoDesktopAction/,
  'desktop commands must be simulated in demo mode',
)
assert.match(
  updaterSource,
  /if\s*\(isDemoMode\(\)\)[\s\S]*demoCheckUpdate/,
  'desktop update checks must be simulated in demo mode',
)
assert.match(
  contextSource,
  /isDemoMode\(\)[\s\S]*DemoBackendInitProvider/,
  'demo mode must use a fixed-ready provider instead of probing the backend',
)
assert.match(
  contextSource,
  /ProductionBackendInitProvider[\s\S]*useCheckBackend/,
  'production mode must retain the real backend readiness hook',
)
assert.match(
  mainSource,
  /if\s*\(!isDemoMode\(\)\)\s*\{[\s\S]*registerDesktopRuntimeOnPageLoad\(\)/,
  'demo mode must not register the desktop runtime',
)
assert.match(
  videoBannerSource,
  /isDemoMode\(\)[\s\S]*rawCover[\s\S]*image_proxy/,
  'demo cover images must bypass the backend image proxy',
)
