import { readFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
async function readOptional(relativePath) {
  try {
    return await readFile(path.join(root, relativePath), 'utf8')
  } catch {
    return ''
  }
}

const monitor = await readOptional('src/pages/SettingPage/Monitor.tsx')
const runtimeService = await readOptional('src/services/desktopRuntime.ts')

const combined = `${monitor}\n${runtimeService}`

assert.match(combined, /开机自动启动 NoteMeld/, '设置页必须提供开机自动启动开关')
assert.match(combined, /get_autostart_enabled/, '前端必须读取 autostart 状态')
assert.match(combined, /set_autostart_enabled/, '前端必须设置 autostart 状态')
assert.doesNotMatch(
  monitor,
  /<Card className="mt-6">[\s\S]*开机自动启动 NoteMeld/,
  '开机自启动必须作为上方状态卡展示，不能放在底部大卡片',
)
