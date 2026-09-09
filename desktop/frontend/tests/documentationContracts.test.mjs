import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..', '..', '..')
const readProjectFile = (relativePath) => readFile(path.join(root, relativePath), 'utf8')

const readme = await readProjectFile('README.md')
const architecture = await readProjectFile('docs/promotion/notemeld-architecture-and-migration.md')

for (const toolName of ['generate_note', 'get_task', 'get_note', 'list_models']) {
  assert.match(readme, new RegExp(`\\\`${toolName}\\\``), `README 必须记录 MCP 工具 ${toolName}`)
  assert.match(architecture, new RegExp(`\\\`${toolName}\\\``), `架构文档必须记录 MCP 工具 ${toolName}`)
}

assert.match(
  readme,
  /Claude Code \/ Cursor \/ Codex \/ OpenClaw/,
  'README 必须记录主流 HTTP MCP 客户端配置入口',
)
assert.match(
  architecture,
  /短任务会直接在 MCP `content\.text` 中返回 Markdown/,
  '架构文档必须说明 MCP 短任务直接返回 Markdown 的行为',
)

for (const mimeType of ['application/octet-stream', 'binary/octet-stream']) {
  assert.match(readme, new RegExp(mimeType), `README 必须记录 Markdown 上传兼容 ${mimeType}`)
  assert.match(architecture, new RegExp(mimeType), `架构文档必须记录 Markdown 上传兼容 ${mimeType}`)
}

for (const releaseGate of ['--release', 'Developer ID', 'notarization', 'stapler staple', 'Gatekeeper']) {
  assert.match(readme, new RegExp(releaseGate), `README 必须记录 DMG 正式发布门禁 ${releaseGate}`)
  assert.match(architecture, new RegExp(releaseGate), `架构文档必须记录 DMG 正式发布门禁 ${releaseGate}`)
}

assert.match(
  architecture,
  /frontend\/tests\/documentationContracts\.test\.mjs/,
  '架构文档必须声明自身对应的文档契约测试',
)

assert.match(
  readme,
  /桌面.*http:\/\/127\.0\.0\.1:8483\/mcp|http:\/\/127\.0\.0\.1:8483\/mcp.*桌面/,
  'README 必须说明桌面 DMG MCP 固定地址',
)
assert.match(
  architecture,
  /桌面.*8483|8483.*桌面/,
  '架构文档必须说明桌面模式固定 MCP 端口 8483',
)
assert.match(
  readme,
  /开机自动启动 NoteMeld|登录项/,
  'README 必须说明开机启动配置入口或手动登录项配置',
)
