import request from '@/utils/request'

export interface WorkspaceProjection {
  workspace: {
    id: string
    display_name: string
    folders: string[]
    policies: Record<string, boolean>
    revision: number
    updated_at: string | null
  }
  memories: Array<{
    id: string
    workspace_id: string
    content: string
    source: string
    created_at: string | null
    updated_at: string | null
  }>
}

export const getMobileProjection = (workspaceId = 'default') =>
  request.get<WorkspaceProjection>('/mobile/projection', { params: { workspace_id: workspaceId } }) as unknown as Promise<WorkspaceProjection>

export const updateMobileWorkspace = (payload: {
  workspaceId?: string
  display_name: string
  folders: string[]
  policies: Record<string, boolean>
  revision: number
}) => {
  const { workspaceId = 'default', ...body } = payload
  return request.put<WorkspaceProjection['workspace']>('/mobile/workspace', body, { params: { workspace_id: workspaceId } }) as unknown as Promise<WorkspaceProjection['workspace']>
}

export const createMobileMemory = (content: string, source = 'user', workspaceId = 'default') =>
  request.post<WorkspaceProjection['memories'][number]>('/mobile/memories', { content, source, workspace_id: workspaceId }) as unknown as Promise<WorkspaceProjection['memories'][number]>

export const deleteMobileMemory = (memoryId: string) =>
  request.delete<{ deleted: boolean; id: string }>(`/mobile/memories/${encodeURIComponent(memoryId)}`) as unknown as Promise<{ deleted: boolean; id: string }>
