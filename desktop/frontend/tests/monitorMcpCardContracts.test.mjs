import { readFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const monitor = await readFile(path.join(root, 'src/pages/SettingPage/Monitor.tsx'), 'utf8')
const systemService = await readFile(path.join(root, 'src/services/system.ts'), 'utf8')

assert.match(monitor, /MCP 服务/, '部署监控必须展示 MCP 服务卡片')
assert.match(monitor, /http:\/\/127\.0\.0\.1:8483\/mcp/, 'MCP 卡片必须展示固定 MCP URL')
assert.match(monitor, /复制地址/, 'MCP 卡片必须提供复制地址操作')
assert.match(monitor, /刷新状态|重试 MCP 检查/, 'MCP 卡片必须提供状态刷新操作')
assert.match(systemService, /mcp:\s*\{/, 'DeployStatus 类型必须包含 mcp 字段')
assert.match(systemService, /recheckMcpStatus/, '系统服务必须提供 MCP 重检 API')
