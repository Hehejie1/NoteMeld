import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const headerSource = await readFile(
  path.join(root, 'src/pages/HomePage/components/MarkdownHeader.tsx'),
  'utf8',
)
const viewerSource = await readFile(
  path.join(root, 'src/pages/HomePage/components/MarkdownViewer.tsx'),
  'utf8',
)
const combinedSource = `${headerSource}\n${viewerSource}`

assert.match(
  combinedSource,
  /复制 MD/,
  '复制菜单必须提供复制 MD，支持直接复制当前笔记正文',
)

assert.match(
  combinedSource,
  /复制 MCP/,
  '复制菜单必须提供复制 MCP，支持快速引用到 Trae / MCP 工具流',
)

assert.match(
  combinedSource,
  /原文对照/,
  '导出菜单必须支持原文对照 .txt 导出入口',
)

assert.match(
  viewerSource,
  /transcript\??\.\s*full_text/,
  '原文对照导出必须基于当前任务 transcript.full_text 真实数据生成',
)

assert.match(
  headerSource,
  /OPEN_DELAY_MS\s*=\s*\d+/,
  'hover 菜单必须定义打开延迟，避免鼠标快速掠过时误展开',
)

assert.match(
  headerSource,
  /CLOSE_DELAY_MS\s*=\s*\d+/,
  'hover 菜单必须定义关闭延迟，避免按钮到菜单斜切时闪退',
)

assert.match(
  headerSource,
  /bridge|safe zone|安全区/i,
  'hover 菜单必须存在按钮与浮层之间的桥接安全区',
)

assert.match(
  headerSource,
  /icon:\s*[A-Z][A-Za-z]+|item\.icon|ItemIcon/,
  'hover 菜单项必须支持图标渲染，增强分组识别度',
)

assert.doesNotMatch(
  headerSource,
  /overflow-x-auto/,
  'hover 菜单所在 header 不能使用 overflow-x-auto，否则下拉浮层会被裁掉',
)

assert.match(
  headerSource,
  /ChevronDown/,
  '复制和导出按钮必须显示下拉指示，避免看起来像不明按钮',
)
