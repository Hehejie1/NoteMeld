import assert from 'node:assert/strict'
import { access, readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const readSource = relativePath => readFile(path.join(root, relativePath), 'utf8')

const dialogPath = path.join(root, 'src/components/Form/modelForm/AddModelDialog.tsx')
await access(dialogPath)

const form = await readSource('src/components/Form/modelForm/Form.tsx')
const selector = await readSource('src/components/Form/modelForm/ModelSelector.tsx')
const service = await readSource('src/services/model.ts')
const store = await readSource('src/store/modelStore/index.ts')

assert.match(form, /添加模型/, 'Provider 编辑区模型列表标题右侧必须提供“添加模型”入口')
assert.match(form, /AddModelDialog/, 'Provider 编辑区必须通过 Dialog 添加模型')
assert.doesNotMatch(form, /<ModelSelector[\s\S]*providerId=/, 'Provider form 不得内联渲染模型选择与保存控件')

assert.doesNotMatch(selector, /保存模型|addNewModel|handleSubmit/, 'ModelSelector 必须只负责选择模型，不能保存')

for (const field of [
  '选择模型',
  '上下文长度',
  '支持图像',
  '支持流式',
]) {
  assert.match(
    await readSource('src/components/Form/modelForm/AddModelDialog.tsx'),
    new RegExp(field),
    `添加模型弹窗必须提供“${field}”字段`,
  )
}

const dialog = await readSource('src/components/Form/modelForm/AddModelDialog.tsx')
assert.match(dialog, /<Dialog[\s\S]*<DialogContent/, '添加模型必须使用居中的通用 Dialog')
assert.match(dialog, /requestVersionRef/, '模型快速切换时必须忽略迟到的 defaults 响应')
assert.match(dialog, /runtimeConfigDirtyRef/, '用户手动修改运行配置后不得被同一模型的迟到 defaults 覆盖')
assert.match(dialog, /\[loadingDefaults,\s*setLoadingDefaults\]\s*=\s*useState\(false\)/, 'defaults 请求期间必须有显式 loading 状态')
assert.match(dialog, /updateLoadingDefaults\(true\)/, 'defaults 请求启动时必须同步设置保存防御标记')
assert.match(dialog, /requestVersion\s*===\s*requestVersionRef\.current[\s\S]{0,160}updateLoadingDefaults\(false\)/, '只有当前 defaults 请求能结束 loading 状态')
assert.match(dialog, /handleSave\s*=\s*async\s*\(\)\s*=>\s*\{[\s\S]{0,180}loadingDefaultsRef\.current/, '保存处理必须同步防御 defaults pending 期间的快速点击')
assert.match(dialog, /handleOpenChange[\s\S]{0,220}requestVersionRef\.current\s*\+=\s*1/, '关闭弹窗时必须立即使迟到 defaults 响应失效')
assert.match(dialog, /disabled=\{saving\s*\|\|\s*loadingDefaults\s*\|\|\s*!selectedModel\}/, '保存按钮在 defaults pending 期间必须禁用')
assert.match(dialog, /await\s+addNewModel\(\{[\s\S]*provider_id:[\s\S]*model_name:[\s\S]*context_window_tokens:[\s\S]*supports_vision:[\s\S]*supports_stream:/, '保存时必须提交完整五字段运行配置')
assert.match(dialog, /await\s+onSaved\?\.\(\)[\s\S]*onOpenChange\(false\)/, '保存成功后必须刷新已添加模型并关闭弹窗')
assert.doesNotMatch(dialog, /catch[\s\S]{0,240}onOpenChange\(false\)/, '保存失败必须保留弹窗和输入')

for (const field of [
  'provider_id',
  'model_name',
  'context_window_tokens',
  'supports_vision',
  'supports_stream',
]) {
  assert.match(service, new RegExp(field), `模型 API payload 必须包含 ${field}`)
  assert.match(store, new RegExp(field), `模型 store 类型必须保留 ${field}`)
}
assert.match(service, /fetchModelDefaults/, '前端服务必须提供模型 defaults API')
assert.match(store, /addNewModel:\s*\(payload: ModelRuntimeConfigPayload\).*Promise<IModelListItem>/, 'store 必须接收完整 payload 并返回已保存模型行')
