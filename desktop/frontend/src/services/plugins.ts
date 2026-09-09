import request from '@/utils/request'

export interface PluginVersion { version: string; sha256: string; license: string; sdk_version: string }
export interface PluginInstallation { plugin_id: string; active_version: string | null; enabled: boolean; runtime_status: string; requested_permissions: string[]; granted_permissions: string[]; versions: PluginVersion[] }
export interface PluginInstallPayload { source_url: string; expected_sha256?: string; plugin_id?: string; version?: string; granted_permissions: string[] }
export interface BuiltinPluginCatalogItem {
  plugin_id: string
  name: string
  description: string
  category: string
  capabilities: string[]
  requested_permissions: string[]
  license: string
  recommended?: boolean
  targets: Record<string, 'host-ready' | 'contract-ready' | 'unverified' | 'unsupported'>
}

// Presentation catalog only; installation and runtime state remain backend-owned.
export const BUILTIN_PLUGIN_CATALOG: BuiltinPluginCatalogItem[] = [
  { plugin_id: 'official.link-note', name: '链接转 Note', description: '将受支持的视频或网页链接加工为可追溯 Note。', category: '内容处理', capabilities: ['official-link-note:create'], requested_permissions: ['network', 'note.write'], license: 'MIT', recommended: true, targets: { desktop: 'host-ready', server: 'contract-ready', mobile: 'unverified' } },
  { plugin_id: 'official.browser', name: '浏览器', description: '在宿主授权的浏览器上下文中打开、导航并提取网页内容。', category: '研究工具', capabilities: ['browser.open', 'browser.navigate', 'browser.extract'], requested_permissions: ['network'], license: 'MIT', targets: { desktop: 'unverified', server: 'unverified', mobile: 'unverified' } },
  { plugin_id: 'official.terminal', name: '终端执行', description: '在宿主授权的 workspace 和 sandbox policy 下执行一次性命令。', category: '开发工具', capabilities: ['terminal.exec'], requested_permissions: ['workspace.execute'], license: 'MIT', targets: { desktop: 'host-ready', server: 'contract-ready', mobile: 'unsupported' } },
  { plugin_id: 'official.document-to-markdown', name: '文档转 Markdown', description: '将受支持的文档转换为 Markdown 中间产物。', category: '内容处理', capabilities: ['document.to_markdown'], requested_permissions: ['workspace.read'], license: 'MIT', recommended: true, targets: { desktop: 'host-ready', server: 'contract-ready', mobile: 'unsupported' } },
  { plugin_id: 'official.image-ocr', name: '图片 OCR', description: '识别图片文字并保留基础位置、顺序和置信度。', category: '内容处理', capabilities: ['image.ocr'], requested_permissions: ['workspace.read'], license: 'MIT', targets: { desktop: 'host-ready', server: 'contract-ready', mobile: 'unsupported' } },
  { plugin_id: 'official.video-fetch', name: '视频获取', description: '获取宿主授权链接对应的视频内容。', category: '媒体处理', capabilities: ['video.fetch'], requested_permissions: ['network', 'workspace.write'], license: 'MIT', targets: { desktop: 'host-ready', server: 'contract-ready', mobile: 'unverified' } },
  { plugin_id: 'official.video-frames', name: '视频帧提取', description: '从视频中提取可供 Agent 分析的关键帧。', category: '媒体处理', capabilities: ['video.frames'], requested_permissions: ['workspace.read'], license: 'MIT', targets: { desktop: 'host-ready', server: 'contract-ready', mobile: 'unsupported' } },
  { plugin_id: 'official.audio-extract', name: '音频提取', description: '从媒体中提取音频中间产物。', category: '媒体处理', capabilities: ['audio.extract'], requested_permissions: ['workspace.read'], license: 'MIT', targets: { desktop: 'host-ready', server: 'contract-ready', mobile: 'unsupported' } },
  { plugin_id: 'official.audio-transcribe', name: '音频转写', description: '将音频转换为带来源信息的文本中间产物。', category: '媒体处理', capabilities: ['audio.transcribe'], requested_permissions: ['workspace.read'], license: 'MIT', targets: { desktop: 'host-ready', server: 'contract-ready', mobile: 'unsupported' } },
]

export const listPlugins = () => request.get<unknown, { plugins: PluginInstallation[] }>('/plugins')
export const installPlugin = (payload: PluginInstallPayload) => request.post<unknown, PluginInstallation>('/plugins/install', payload)
export const enablePlugin = (id: string) => request.post<unknown, PluginInstallation>(`/plugins/${encodeURIComponent(id)}/enable`)
export const disablePlugin = (id: string) => request.post<unknown, PluginInstallation>(`/plugins/${encodeURIComponent(id)}/disable`)
export const activatePlugin = (id: string, version: string) => request.post<unknown, PluginInstallation>(`/plugins/${encodeURIComponent(id)}/activate/${encodeURIComponent(version)}`)
export const rollbackPlugin = (id: string, version: string) => request.post<unknown, PluginInstallation>(`/plugins/${encodeURIComponent(id)}/rollback/${encodeURIComponent(version)}`)
