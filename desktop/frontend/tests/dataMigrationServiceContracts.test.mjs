import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const migrationServiceSource = await readFile(path.join(root, 'src/services/migration.ts'), 'utf8')
const fileDialogSource = await readFile(path.join(root, 'src/utils/fileDialog.ts'), 'utf8')
const dataMigrationPageSource = await readFile(path.join(root, 'src/pages/SettingPage/DataMigration.tsx'), 'utf8')

assert.match(
  migrationServiceSource,
  /request\.post\(['"]\/migration\/export['"],\s*payload\)/,
  '前端 migration service 必须提供导出接口封装',
)

assert.match(
  migrationServiceSource,
  /request\.post\(['"]\/migration\/import['"],\s*payload\)/,
  '前端 migration service 必须提供导入接口封装',
)

assert.match(
  migrationServiceSource,
  /uploadMigrationPackage/,
  '前端 migration service 必须提供浏览器上传迁移包接口',
)

assert.match(
  migrationServiceSource,
  /request\.post\(['"]\/migration\/import\/upload['"],\s*formData/,
  '浏览器上传迁移包必须调用后端 import/upload 接口',
)

assert.match(
  dataMigrationPageSource,
  /browserImportFile/,
  '浏览器拖拽或点击选择 zip 时必须保存 File 对象，不能依赖本地路径',
)

assert.match(
  dataMigrationPageSource,
  /uploadMigrationPackage\(browserImportFile\)/,
  '浏览器导入必须先上传 File 并用后端返回的 package_path 启动导入',
)

assert.match(
  dataMigrationPageSource,
  /String\(job\?\.status\s*\|\|\s*''\)\.trim\(\)\.toLowerCase\(\)\s*===\s*'failed'\s*&&\s*job\?\.error/,
  '迁移页面只能在 failed 状态展示 job.error，避免 completed 任务显示历史错误',
)

assert.match(
  migrationServiceSource,
  /package_path:\s*string/,
  '前端 migration service 导入参数必须使用 package_path 字段',
)

assert.match(
  migrationServiceSource,
  /request\.get\(`\/migration\/\$\{jobId\}\/job`\)/,
  '前端 migration service 必须提供任务轮询接口封装',
)

assert.match(
  migrationServiceSource,
  /getMigrationPackageDownloadUrl/,
  '前端 migration service 必须提供浏览器端下载迁移包的 URL helper',
)

assert.match(
  migrationServiceSource,
  /\/migration\/\$\{encodeURIComponent\(jobId\)\}\/download/,
  '迁移包下载 URL 必须指向后端 download 路由并编码 jobId',
)

assert.doesNotMatch(
  dataMigrationPageSource,
  /disabled=\{isSubmitting\s*\|\|\s*!supportsNativeFileDialog\}/,
  '浏览器端导出按钮不能因为缺少 Tauri 系统弹窗能力而禁用',
)

assert.match(
  migrationServiceSource,
  /request\.post\(['"]\/migration\/reindex['"],\s*payload\)/,
  '前端 migration service 必须提供索引重建接口封装',
)

assert.match(
  fileDialogSource,
  /isDesktopEmbedded\(\)/,
  '文件选择 helper 必须根据桌面运行时决定是否调用原生对话框',
)

assert.match(
  fileDialogSource,
  /import\(['"]@tauri-apps\/plugin-dialog['"]\)/,
  '桌面端文件选择必须通过 tauri dialog plugin 动态导入',
)

assert.match(
  fileDialogSource,
  /let\s+dialogModulePromise/,
  '文件选择 helper 必须缓存 Tauri dialog 动态导入，避免每次点击重新加载',
)

assert.match(
  fileDialogSource,
  /export\s+function\s+preloadDesktopFileDialog/,
  '文件选择 helper 必须提供桌面文件选择插件预加载入口',
)

assert.doesNotMatch(
  fileDialogSource,
  /export\s+async\s+function\s+selectMigrationDirectoryPath/,
  '文件选择 helper 不应再暴露目录选择能力',
)

assert.match(
  fileDialogSource,
  /export\s+async\s+function\s+selectMigrationPackagePath/,
  '文件选择 helper 必须提供迁移包路径选择能力',
)

assert.match(
  fileDialogSource,
  /extensions:\s*\['zip'\]/,
  '迁移包选择器必须仅允许 zip 扩展名',
)
