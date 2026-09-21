import request from '@/utils/request'

export type McpTransport = 'stdio' | 'http' | 'sse'
export type McpAuthType = 'bearer' | 'basic' | 'none'

export interface McpServerConfig {
  name: string
  transport: McpTransport
  enabled: boolean
  timeout_seconds?: number | null
  command?: string | null
  args?: string[]
  env?: Record<string, string>
  cwd?: string | null
  url?: string | null
  headers?: Record<string, string>
  auth?: Record<string, unknown>
}

export interface McpServerPayload {
  name: string
  transport: McpTransport
  enabled: boolean
  timeout_seconds?: number | null
  command?: string | null
  args?: string[]
  env?: Record<string, string>
  cwd?: string | null
  url?: string | null
  headers?: Record<string, string>
  auth?: Record<string, unknown>
}

export interface McpServersResult {
  servers: Record<string, McpServerConfig>
}

export interface McpEnabledResult extends McpServersResult {
  count: number
}

export interface McpUpsertResult {
  server_id: string
  config: McpServerConfig
}

export interface McpDeleteResult {
  server_id: string
  deleted: boolean
}

/** 获取所有 MCP server 配置（auth 字段已脱敏） */
export const listMcpServers = async (): Promise<McpServersResult> => {
  return await request.get<unknown, McpServersResult>('/mcp_servers')
}

/** 新增或更新 MCP server；省略或回传脱敏占位符时保留已有敏感字段。 */
export const upsertMcpServer = async (
  serverId: string,
  payload: McpServerPayload,
): Promise<McpUpsertResult> => {
  return await request.put<unknown, McpUpsertResult>(
    `/mcp_servers/${encodeURIComponent(serverId)}`,
    payload,
  )
}

/** 删除 MCP server */
export const deleteMcpServer = async (
  serverId: string,
): Promise<McpDeleteResult> => {
  return await request.delete<unknown, McpDeleteResult>(
    `/mcp_servers/${encodeURIComponent(serverId)}`,
  )
}

/** 获取已启用的 MCP server 列表 */
export const getEnabledMcpServers = async (): Promise<McpEnabledResult> => {
  return await request.get<unknown, McpEnabledResult>('/mcp_servers/enabled')
}
