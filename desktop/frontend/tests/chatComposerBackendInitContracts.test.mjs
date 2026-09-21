import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(
  path.join(root, 'src/pages/HomePage/components/ChatComposer.tsx'),
  'utf8',
)

assert.match(
  source,
  /import\s+\{\s*useBackendInitContext\s*\}\s+from\s+['"]@\/contexts\/BackendInitContext\.tsx['"]/,
  'ChatComposer 必须感知全局 backend init 状态，才能在局部降级模式下给出明确提示',
)

assert.match(
  source,
  /const\s+\{\s*backendReady\s*\}\s*=\s*useBackendInitContext\(\)/,
  'ChatComposer 需要读取 backendReady，以避免把 runtime/backend 状态混为一个 initialized',
)

assert.doesNotMatch(
  source,
  /useEffect\(\(\)\s*=>\s*\{\s*loadEnabledModels\(\)[\s\S]*fetchProviderList\(\)[\s\S]*fetchNoteStyles\(\)/,
  'ChatComposer 不能再在挂载时直接并发拉模型、Provider 和风格模板，否则 /new 会出现首屏三连 toast',
)

assert.match(
  source,
  /useEffect\(\(\)\s*=>\s*\{[\s\S]*if\s*\(\s*!backendReady\s*\)\s*return[\s\S]*loadEnabledModels\(\)[\s\S]*fetchProviderList\(\)[\s\S]*fetchNoteStyles\(\)/,
  'ChatComposer 的 backend 依赖首屏请求必须等 backendReady 后再发',
)

assert.match(
  source,
  /const\s+canSubmit\s*=\s*\(\s*!!plainText\s*\|\|\s*!!urlChip\s*\|\|\s*!!pendingUploadedFile\s*\)\s*&&\s*!uploading\s*&&\s*!submitting/,
  '发送按钮可点击状态仍只能受输入、上传和 submitting 影响，不能被 backend 未就绪直接禁用',
)

assert.match(
  source,
  /const\s+ensureBackendReady\s*=\s*\(\)\s*=>\s*\{[\s\S]*if\s*\(\s*!backendReady\s*\)[\s\S]*toast\.error\('后端尚未就绪，请稍后重试或点击顶部提示中的重试'\)/,
  'backend 未就绪时，ChatComposer 必须给出明确错误提示，而不是落入模糊的通用失败提示',
)

assert.match(
  source,
  /toast\.error\('请先在设置中添加模型'\)[\s\S]*navigate\('\/settings\/model'\)/,
  '模型缺失时仍必须优先提示去设置模型，不能被 backend 状态覆盖',
)
