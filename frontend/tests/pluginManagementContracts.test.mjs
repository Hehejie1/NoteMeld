import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const page = fs.readFileSync(path.join(root, 'src/pages/SettingPage/Plugins.tsx'), 'utf8')
const service = fs.readFileSync(path.join(root, 'src/services/plugins.ts'), 'utf8')

for (const pluginId of ['official.link-note', 'official.browser', 'official.terminal', 'official.document-to-markdown']) {
  assert.match(service, new RegExp(pluginId.replace('.', '\\.') ), `内置 catalog 必须包含 ${pluginId}`)
}
for (const label of ['插件目录', '已安装', '添加插件 / 内容', '搜索插件、能力或简介', '确认安装', '后端尚未 ready']) {
  assert.match(page, new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')), `插件页面必须包含 ${label}`)
}
for (const api of ['listPlugins', 'installPlugin', 'enablePlugin', 'disablePlugin', 'activatePlugin', 'rollbackPlugin']) {
  assert.match(page, new RegExp(api), `插件页面必须保留 ${api} 调用`)
}
assert.match(page, /if \(!backendReady\) return/, 'backend 未 ready 时不能请求插件列表')
assert.match(page, /!backendReady \|\| busy \|\| !sourceUrl\.trim\(\)/, '安装必须受 ready、busy 和 URL 门禁')
assert.doesNotMatch(page, /child_process|eval\(|new Function\(/, '插件页面不得执行插件代码')

console.log('plugin management contracts passed')
