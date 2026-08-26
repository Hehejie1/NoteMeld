import request from '@/utils/request'

export interface PluginVersion { version: string; sha256: string; license: string; sdk_version: string }
export interface PluginInstallation { plugin_id: string; active_version: string | null; enabled: boolean; runtime_status: string; requested_permissions: string[]; granted_permissions: string[]; versions: PluginVersion[] }
export interface PluginInstallPayload { source_url: string; expected_sha256?: string; plugin_id?: string; version?: string; granted_permissions: string[] }
export const listPlugins = () => request.get<any, { plugins: PluginInstallation[] }>('/plugins')
export const installPlugin = (payload: PluginInstallPayload) => request.post<any, PluginInstallation>('/plugins/install', payload)
export const enablePlugin = (id: string) => request.post<any, PluginInstallation>(`/plugins/${encodeURIComponent(id)}/enable`)
export const disablePlugin = (id: string) => request.post<any, PluginInstallation>(`/plugins/${encodeURIComponent(id)}/disable`)
export const activatePlugin = (id: string, version: string) => request.post<any, PluginInstallation>(`/plugins/${encodeURIComponent(id)}/activate/${encodeURIComponent(version)}`)
export const rollbackPlugin = (id: string, version: string) => request.post<any, PluginInstallation>(`/plugins/${encodeURIComponent(id)}/rollback/${encodeURIComponent(version)}`)
