import request from '@/utils/request'

export interface WorkspaceEntry {
  name: string
  type: 'file' | 'directory'
  size: number
}

export interface WorkspaceListResult {
  path: string
  entries: WorkspaceEntry[]
}

export interface WorkspaceReadResult {
  path: string
  size: number
  truncated: boolean
  encoding: 'utf-8' | 'base64'
  content: string
}

export interface WorkspaceCancelResult {
  card_id: string
  conversation_id: string
  canceled: boolean
}

/** 列出会话工作空间目录内容（只读） */
export const listWorkspace = async (
  conversationId: string,
  path?: string,
): Promise<WorkspaceListResult> => {
  const query = path ? `?path=${encodeURIComponent(path)}` : ''
  return await request.get<any, WorkspaceListResult>(
    `/conversations/${conversationId}/workspace/list${query}`,
  )
}

/** 读取会话工作空间内文件（只读） */
export const readWorkspaceFile = async (
  conversationId: string,
  path: string,
): Promise<WorkspaceReadResult> => {
  return await request.get<any, WorkspaceReadResult>(
    `/conversations/${conversationId}/workspace/read?path=${encodeURIComponent(path)}`,
  )
}

/** 取消长任务卡片 */
export const cancelWorkspaceTask = async (
  conversationId: string,
  cardId: string,
): Promise<WorkspaceCancelResult> => {
  return await request.post<any, WorkspaceCancelResult>(
    `/conversations/${conversationId}/workspace/cancel_task`,
    { card_id: cardId },
  )
}

/** 从 request 拦截器 reject 的错误中提取业务 code */
export const extractWorkspaceErrorCode = (err: unknown): number | null => {
  if (err && typeof err === 'object' && 'code' in err) {
    const code = (err as { code: unknown }).code
    return typeof code === 'number' ? code : null
  }
  return null
}
