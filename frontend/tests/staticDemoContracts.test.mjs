import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const read = file => readFile(path.join(root, file), 'utf8')

const [modeSource, contextSource, mainSource] = await Promise.all([
  read('src/demo/mode.ts').catch(() => ''),
  read('src/contexts/BackendInitContext.tsx'),
  read('src/main.tsx'),
])

assert.match(
  modeSource,
  /import\.meta\.env\.VITE_NOTEMELD_DEMO\s*===\s*['"]true['"]/,
  'demo mode must require the explicit compile-time flag',
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
