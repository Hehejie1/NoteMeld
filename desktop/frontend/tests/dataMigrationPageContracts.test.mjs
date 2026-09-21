import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const pageSource = await readFile(path.join(root, 'src/pages/SettingPage/DataMigration.tsx'), 'utf8')

assert.match(
  pageSource,
  /startMigrationExport,\s*startMigrationImport,\s*getMigrationJob/,
  'DataMigration 页面必须接入 migration service 的导出、导入和任务轮询能力',
)

assert.doesNotMatch(
  pageSource,
  /selectMigrationDirectoryPath/,
  'DataMigration 页面不应再暴露目录选择入口',
)

assert.match(pageSource, /selectMigrationPackagePath/, 'DataMigration 页面必须保留 zip 迁移包选择 helper')

assert.match(
  pageSource,
  /preloadDesktopFileDialog/,
  'DataMigration 页面必须预加载桌面文件选择插件，避免点击导入迁移包后才动态加载导致弹窗慢',
)

assert.match(
  pageSource,
  /useTaskStore\(state\s*=>\s*state\.loadConversations\)/,
  'DataMigration 页面必须能在导入完成后刷新左侧笔记列表',
)

assert.match(
  pageSource,
  /loadConversations\(\)/,
  '导入迁移包完成后必须重新拉取会话列表',
)

assert.match(
  pageSource,
  /const\s+\[jobId,\s*setJobId\]/,
  'DataMigration 页面必须维护当前迁移任务 jobId',
)

assert.match(
  pageSource,
  /setInterval\(\(\)\s*=>\s*\{\s*void\s+pollMigrationJob\(jobId\)/,
  'DataMigration 页面必须在任务进行中轮询迁移进度',
)

assert.match(
  pageSource,
  /window\.clearInterval\(timer\)/,
  'DataMigration 页面卸载或任务结束后必须停止轮询',
)

assert.match(
  pageSource,
  /package_path:\s*packagePath/,
  'DataMigration 页面导入时必须传递 package_path',
)

assert.match(
  pageSource,
  /支持导出 zip 迁移包、导入 zip 迁移包/,
  'DataMigration 页面说明文案必须聚焦 zip 主流程',
)

assert.match(
  pageSource,
  /请先填写或选择 zip 迁移包路径|当前仅支持导入 \.zip 迁移包/,
  'DataMigration 页面必须明确提示仅支持 zip 迁移包',
)

assert.match(
  pageSource,
  /当前为浏览器模式：导出完成后会触发普通下载，导入仍需使用桌面端选择或拖拽本地 zip/,
  'DataMigration 页面在非桌面端必须提示浏览器导入导出差异',
)
