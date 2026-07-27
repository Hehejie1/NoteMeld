import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(path.join(root, 'src/hooks/useCheckBackend.ts'), 'utf8')

assert.doesNotMatch(
  source,
  /const\s+checkNow\s*=\s*useCallback\(async\s*\(\)\s*=>\s*\{\s*\},\s*\[\]\)/,
  '任务3要求重试按钮真正触发探测，checkNow 不能再是空异步函数',
)

assert.match(
  source,
  /const\s+checkRef\s*=\s*useRef<\(\)\s*=>\s*Promise<void>>/,
  'useCheckBackend 应暴露真实重试入口，至少需要保存当前探测函数引用',
)

assert.match(
  source,
  /const\s+checkNow\s*=\s*useCallback\(async\s*\(\)\s*=>\s*\{[\s\S]*setRetryCount\(0\)[\s\S]*setInitialized\(false\)[\s\S]*setStatus\('checking'\)[\s\S]*await\s+checkRef\.current\(\)/,
  'checkNow 必须重置状态并重新触发静默探测，供 BackendInitDialog 的“重试”按钮复用',
)
