import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const source = await readFile(path.join(root, 'src/services/chat.ts'), 'utf8')

assert.match(
  source,
  /getRuntimeApiBaseUrl\(\)\s*\|\|\s*import\.meta\.env\.VITE_API_BASE_URL\s*\|\|\s*'\/api'/,
  '流式聊天接口必须显式使用 runtime 或 VITE_API_BASE_URL，避免桌面端请求落到错误的根路径',
)

assert.doesNotMatch(
  source,
  /request\.defaults\.baseURL/,
  '流式聊天不能依赖 axios defaults.baseURL；当前实例通过拦截器按请求注入 baseURL，这里会拿到空值',
)

