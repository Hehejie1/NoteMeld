import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const read = file => readFile(path.join(root, file), 'utf8')

const appService = await read('src/services/applications.ts')
const registry = await read('src/apps/registry.ts')
const wikiManifest = await read('src/apps/wiki/manifest.json')
const host = await read('src/app-host/ApplicationHost.tsx')
const wiki = await read('src/apps/wiki/WikiApplication.tsx')
const app = await read('src/App.tsx')
const layout = await read('src/layouts/AppLayout.tsx')

assert.match(appService, /export\s+interface\s+ApplicationSummary/, '应用 service 必须导出应用列表类型')
assert.match(appService, /applicationPath\(appId\).*wiki\/graph/, 'Wiki 必须通过 Application Host capability 读取图谱')
assert.match(appService, /applicationPath\(appId\).*wiki\/articles/, 'Wiki 必须通过 Application Host capability 读取文章')
assert.match(appService, /run_id/, '应用运行实例必须使用后端定义的 run_id')
assert.match(appService, /settings\/workspace/, '应用默认 workspace 必须提供设置 API')
assert.doesNotMatch(appService, /['"]\/wiki\//, '应用 service 不应把旧 Wiki router 作为数据入口')

assert.match(registry, /WIKI_APPLICATION_ID\s*=\s*['"]wiki['"]/, '内建 registry 必须注册 Wiki 应用')
assert.match(registry, /loadBuiltInApplication/, '应用 UI 必须通过 loader 按需加载')
assert.match(registry, /import\(['"]@\/apps\/wiki\/WikiApplication['"]\)/, 'Wiki 应用组件必须动态加载')
assert.match(wikiManifest, /notemeld\.application\.v1/, 'Wiki 必须拥有独立应用 manifest')
assert.match(host, /capability-missing/, 'Host 必须展示能力缺失状态')
assert.match(host, /state\s*===\s*['"]disabled['"]/, 'Host 必须展示禁用状态')
assert.match(host, /state\s*===\s*['"]interrupted['"]/, 'Host 必须展示运行中断状态')
assert.match(host, /startApplicationRun/, 'Host 必须通过应用 run API 启动应用')

assert.match(wiki, /getApplicationWikiGraph/, 'Wiki 应用必须从 applications service 获取图谱')
assert.match(wiki, /getApplicationWikiArticle/, 'Wiki 应用必须从 applications service 获取文章')
assert.doesNotMatch(wiki, /@\/services\/wiki/, 'Wiki 应用内部不得直接依赖旧 Wiki service')
assert.match(wiki, /类型视图/, 'Wiki 应用必须保留类型视图')
assert.match(wiki, /社群视图/, 'Wiki 应用必须保留社群视图')
assert.match(wiki, /查看文章详情/, 'Wiki 应用必须保留文章查看入口')
assert.match(wiki, /已保留当前图谱/, '刷新失败时必须保留已加载图谱')

assert.match(app, /path="\/applications"/, 'App 必须注册应用列表路由')
assert.match(app, /path="\/applications\/:appId"/, 'App 必须注册应用容器路由')
assert.match(app, /SettingPage\/Applications/, '设置必须提供应用默认 workspace 配置页')
assert.doesNotMatch(app, /path="\/wiki"/, '旧 /wiki 路由必须移除')
assert.doesNotMatch(app, /pages\/WikiPage/, 'App 不得继续直接引用旧 Wiki 页面')
assert.match(layout, /to:\s*['"]\/applications['"]/, '主导航必须提供应用入口')
assert.doesNotMatch(layout, /to:\s*['"]\/wiki['"]/, '主导航不得继续 wiring 旧 Wiki 路由')

console.log('application host contracts passed')
