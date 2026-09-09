import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const read = file => readFile(path.join(root, file), 'utf8')

const appService = await read('src/services/applications.ts')
const host = await read('src/app-host/ApplicationHost.tsx')
const packageManifest = await read('../../../packages/notemeld-applications/apps/wiki/manifest.json')
const app = await read('src/App.tsx')
const layout = await read('src/layouts/AppLayout.tsx')

assert.match(appService, /export\s+interface\s+ApplicationSummary/, '应用 service 必须导出应用列表类型')
assert.match(appService, /invokeApplicationCapability/, 'Wiki 必须通过 Application Host capability bridge 读取数据')
assert.match(appService, /run_id/, '应用运行实例必须使用后端定义的 run_id')
assert.match(appService, /settings\/workspace/, '应用默认 workspace 必须提供设置 API')
assert.doesNotMatch(appService, /['"]\/wiki\//, '应用 service 不应把旧 Wiki router 作为数据入口')

assert.match(packageManifest, /notemeld\.application\.v1/, '独立 Wiki 包必须声明应用协议')
assert.match(host, /<iframe/, '应用 UI 必须通过隔离 iframe 加载')
assert.match(host, /notemeld\.application\.invoke/, 'Application Host 必须提供应用 Bridge')
assert.doesNotMatch(host, /loadBuiltInApplication|@\/apps/, 'Application Host 不得 import NoteMeld 应用源码')
assert.match(host, /capability-missing/, 'Host 必须展示能力缺失状态')
assert.match(host, /state\s*===\s*['"]disabled['"]/, 'Host 必须展示禁用状态')
assert.match(host, /state\s*===\s*['"]interrupted['"]/, 'Host 必须展示运行中断状态')
assert.match(host, /startApplicationRun/, 'Host 必须通过应用 run API 启动应用')


assert.match(app, /path="\/applications"/, 'App 必须注册应用列表路由')
assert.match(app, /path="\/applications\/:appId"/, 'App 必须注册应用容器路由')
assert.match(app, /SettingPage\/Applications/, '设置必须提供应用默认 workspace 配置页')
assert.doesNotMatch(app, /path="\/wiki"/, '旧 /wiki 路由必须移除')
assert.doesNotMatch(app, /pages\/WikiPage/, 'App 不得继续直接引用旧 Wiki 页面')
assert.match(layout, /to:\s*['"]\/applications['"]/, '主导航必须提供应用入口')
assert.doesNotMatch(layout, /to:\s*['"]\/wiki['"]/, '主导航不得继续 wiring 旧 Wiki 路由')

console.log('application host contracts passed')
