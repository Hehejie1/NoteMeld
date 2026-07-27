import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const appSource = await readFile(path.join(root, 'src/App.tsx'), 'utf8')
const menuSource = await readFile(path.join(root, 'src/pages/SettingPage/Menu.tsx'), 'utf8')

assert.match(
  appSource,
  /const\s+DataMigration\s*=\s*lazy\(\(\)\s*=>\s*import\(['"]@\/pages\/SettingPage\/DataMigration\.tsx['"]\)\)/,
  '设置页路由必须懒加载 DataMigration 页面',
)

assert.match(
  appSource,
  /<Route\s+path="data-migration"\s+element=\{<DataMigration\s*\/>\}\s*\/>/,
  '设置页必须注册 /settings/data-migration 路由',
)

assert.match(
  menuSource,
  /id:\s*['"]data-migration['"],\s*name:\s*['"]数据与迁移['"]/,
  '设置页菜单必须暴露“数据与迁移”入口',
)

assert.match(
  menuSource,
  /path:\s*['"]\/settings\/data-migration['"]/,
  '设置页菜单必须跳转到 /settings/data-migration',
)
