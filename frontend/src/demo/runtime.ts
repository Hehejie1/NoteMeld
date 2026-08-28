import { demoFixtureSeed } from './fixtures.ts'
import type { DemoListener, DemoRequest, DemoRuntime } from './types.ts'

const clone = <T>(value: T): T => structuredClone(value)

export class DemoEndpointNotImplementedError extends Error {
  constructor(method: string, path: string) {
    super(`Static demo endpoint is not implemented: ${method} ${path}`)
    this.name = 'DemoEndpointNotImplementedError'
  }
}

const normalizePath = (path: string): string => {
  const withoutOrigin = path.replace(/^https?:\/\/[^/]+/i, '')
  const withoutApi = withoutOrigin.replace(/^\/api(?=\/|$)/, '')
  const [pathname] = withoutApi.split('?')
  return pathname || '/'
}

const mergeRecord = (current: Record<string, unknown>, body: unknown) => ({
  ...current,
  ...(body && typeof body === 'object' ? body as Record<string, unknown> : {}),
})

export const createDemoRuntime = (): DemoRuntime => {
  let state = clone(demoFixtureSeed)
  const listeners = new Set<DemoListener>()
  const emit = () => listeners.forEach(listener => listener())

  const findConversation = (id: string) => state.conversations.find(item => item.id === id)

  const request = async <T>({ method, path, body }: DemoRequest): Promise<T> => {
    const pathname = normalizePath(path)

    if (method === 'GET' && pathname === '/conversations') return clone(state.conversations) as T
    if (method === 'GET' && pathname.startsWith('/conversations/')) {
      const id = decodeURIComponent(pathname.split('/')[2] || '')
      const item = findConversation(id)
      if (!item) throw new Error('演示会话不存在')
      return clone(item) as T
    }
    if ((method === 'PUT' || method === 'PATCH') && /^\/conversations\/[^/]+$/.test(pathname)) {
      const id = decodeURIComponent(pathname.split('/')[2] || '')
      const index = state.conversations.findIndex(item => item.id === id)
      const current = index >= 0 ? state.conversations[index] : { id }
      const next = mergeRecord(current, body)
      if (index >= 0) state.conversations[index] = next
      else state.conversations.unshift(next)
      emit()
      return clone(next) as T
    }
    if (method === 'DELETE' && /^\/conversations\/[^/]+$/.test(pathname)) {
      const id = decodeURIComponent(pathname.split('/')[2] || '')
      state.conversations = state.conversations.filter(item => item.id !== id)
      emit()
      return { id } as T
    }
    if (method === 'POST' && /^\/conversations\/[^/]+\/messages$/.test(pathname)) {
      const id = decodeURIComponent(pathname.split('/')[2] || '')
      const item = findConversation(id)
      if (!item) throw new Error('演示会话不存在')
      const messages = Array.isArray(item.messages) ? item.messages : []
      item.messages = [...messages, clone(body as Record<string, unknown>)]
      emit()
      return clone(item) as T
    }
    if (method === 'PATCH' && /^\/conversations\/[^/]+\/messages\/[^/]+$/.test(pathname)) {
      const [, , conversationId, , messageId] = pathname.split('/')
      const item = findConversation(decodeURIComponent(conversationId || ''))
      if (!item) throw new Error('演示会话不存在')
      const messages = Array.isArray(item.messages) ? item.messages : []
      item.messages = messages.map(message => message.id === messageId ? mergeRecord(message, body) : message)
      emit()
      return clone(item) as T
    }
    if (method === 'DELETE' && /^\/conversations\/[^/]+\/documents\/[^/]+$/.test(pathname)) {
      const [, , conversationId, , documentId] = pathname.split('/')
      const item = findConversation(decodeURIComponent(conversationId || ''))
      if (!item) throw new Error('演示会话不存在')
      const documents = Array.isArray(item.documents) ? item.documents : []
      item.documents = documents.filter(document => document.taskId !== documentId)
      item.markdown = ''
      emit()
      return clone(item) as T
    }
    if (method === 'GET' && pathname.startsWith('/task_status/')) {
      const taskId = decodeURIComponent(pathname.slice('/task_status/'.length))
      return clone(state.taskStatuses[taskId] || { status: 'NOT_FOUND', message: '演示任务不存在' }) as T
    }
    if (method === 'POST' && pathname === '/generate_note') {
      return { task_id: 'demo-task-running', conversation_id: 'demo-note-running' } as T
    }
    if (method === 'POST' && pathname === '/delete_task') return { deleted: true } as T
    if (method === 'GET' && pathname === '/applications') return [{ id: 'wiki', name: 'Wiki', version: '1.0.0', description: '浏览由 NoteMeld 编译的来源、实体、概念和关系图谱。', status: 'running', enabled: true, capabilities: ['wiki.read'] }] as T
    if (method === 'GET' && pathname === '/applications/wiki') return { id: 'wiki', name: 'Wiki', version: '1.0.0', description: '浏览由 NoteMeld 编译的来源、实体、概念和关系图谱。', status: 'running', enabled: true, capabilities: ['wiki.read'] } as T
    if (method === 'GET' && pathname === '/applications/wiki/instances') return [{ id: 'demo-wiki-instance', app_id: 'wiki', title: 'Wiki' }] as T
    if (method === 'POST' && pathname === '/applications/wiki/instances') return { id: 'demo-wiki-instance', app_id: 'wiki', title: 'Wiki' } as T
    if (method === 'POST' && /^\/applications\/wiki\/instances\/[^/]+\/runs$/.test(pathname)) return { run_id: 'demo-wiki-run', app_id: 'wiki', instance_id: 'demo-wiki-instance', status: 'running' } as T
    if (method === 'GET' && pathname === '/applications/runs/demo-wiki-run') return { run_id: 'demo-wiki-run', app_id: 'wiki', instance_id: 'demo-wiki-instance', status: 'running' } as T
    if (method === 'POST' && pathname === '/applications/runs/demo-wiki-run/cancel') return { run_id: 'demo-wiki-run', app_id: 'wiki', instance_id: 'demo-wiki-instance', status: 'cancelled' } as T
    if (method === 'POST' && pathname === '/applications/runs/demo-wiki-run/capability') {
      const request = body as { capability?: string; method?: string; input?: { source_id?: string } }
      if (request.capability === 'wiki.read' && request.method === 'graph') return clone(state.wikiGraph) as T
      if (request.capability === 'wiki.read' && request.method === 'article') return { id: request.input?.source_id || 'demo-source', title: 'AI Agent 演示笔记', summary: '这是静态演示中的 Wiki 文章详情。', entities: [{ name: 'AI Agent', entity_type: 'concept', description: '能够规划并调用工具的智能系统。' }], concepts: [{ name: '工具调用', description: '模型通过宿主能力读取和操作知识。' }], claims: [{ claim: 'Agent 通过规划、工具和反馈形成闭环。' }], evidence: [{ evidence_id: 'demo-evidence', text: 'Agent 通过规划、工具和反馈形成闭环。' }], relations: [], markdown: '# AI Agent\n\n这是静态演示文章。' } as T
    }
    if (method === 'GET' && pathname === '/applications/settings/workspace') return { workspace_ref: 'workspace://default', configured: false, root: '/Users/demo/NoteMeld Applications' } as T
    if (method === 'PUT' && pathname === '/applications/settings/workspace') return { workspace_ref: 'workspace://default', configured: true, root: '/Users/demo/NoteMeld Applications' } as T
    if (method === 'GET' && pathname === '/wiki/graph') return clone(state.wikiGraph) as T
    if (method === 'GET' && pathname === '/note_styles') return clone(state.styles) as T
    if (method === 'POST' && pathname === '/note_styles') {
      const next = { id: `demo-style-${state.styles.length + 1}`, ...(body as Record<string, unknown>), builtin: false }
      state.styles.push(next)
      emit()
      return clone(next) as T
    }
    if ((method === 'PUT' || method === 'DELETE') && pathname.startsWith('/note_styles/')) {
      const id = decodeURIComponent(pathname.split('/')[2] || '')
      const index = state.styles.findIndex(item => item.id === id)
      if (method === 'DELETE') state.styles = state.styles.filter(item => item.id !== id)
      else if (index >= 0) state.styles[index] = mergeRecord(state.styles[index], body)
      emit()
      return clone(index >= 0 ? state.styles[index] : undefined) as T
    }

    const settings = state.settings as Record<string, any>
    if (method === 'GET' && pathname === '/get_all_providers') return clone(settings.providers) as T
    if (method === 'GET' && pathname.startsWith('/get_provider_by_id/')) return clone(settings.providers.find((item: any) => item.id === pathname.split('/').pop())) as T
    if (method === 'GET' && pathname === '/model_list') return clone(settings.models) as T
    if (method === 'GET' && pathname.startsWith('/model_enable/')) return clone(settings.models.filter((item: any) => item.provider_id === pathname.split('/').pop())) as T
    if (method === 'GET' && pathname.startsWith('/model_list/')) return { models: clone(settings.models) } as T
    if (method === 'GET' && pathname === '/provider_templates') return [] as T
    if (method === 'POST' && ['/update_provider', '/add_provider', '/connect_test', '/provider_templates', '/models', '/models/probe', '/models/defaults'].includes(pathname)) return clone(body || { ok: true }) as T
    if (method === 'GET' && pathname.startsWith('/models/delete/')) return { deleted: true } as T
    if (method === 'GET' && pathname === '/transcriber_config') return clone(settings.transcriber) as T
    if (method === 'POST' && pathname === '/transcriber_config') { settings.transcriber = mergeRecord(settings.transcriber, body); emit(); return clone(settings.transcriber) as T }
    if (method === 'GET' && pathname === '/transcriber_models_status') return clone(settings.transcriberModels) as T
    if (method === 'POST' && pathname === '/transcriber_download') return { status: 'success', simulated: true } as T
    if (method === 'GET' && pathname.startsWith('/get_downloader_cookie/')) {
      const platform = pathname.split('/').pop() || ''
      return { configured: Boolean(settings.downloaderConfigured[platform]), has_cookie: Boolean(settings.downloaderConfigured[platform]) } as T
    }
    if (method === 'POST' && pathname === '/update_downloader_cookie') return { configured: true, simulated: true } as T
    if (method === 'GET' && ['/sys_health', '/sys_check'].includes(pathname)) return { status: 'ok', demo: true } as T
    if (method === 'GET' && pathname === '/deploy_status') return clone(settings.deployStatus) as T
    if (method === 'POST' && pathname === '/mcp/recheck') return clone(settings.deployStatus.mcp) as T
    if (method === 'GET' && pathname === '/usage/overview') return clone(settings.usageOverview) as T
    if (method === 'GET' && pathname === '/usage/records') return clone(settings.usageRecords) as T
    if (method === 'GET' && pathname === '/usage/task_summary') return [] as T
    if (method === 'GET' && pathname.startsWith('/usage/task_calls/')) return clone(settings.usageRecords) as T
    if (method === 'GET' && pathname === '/mcp_servers') return clone(settings.mcpServers) as T
    if (method === 'GET' && pathname === '/mcp_servers/enabled') return { ...clone(settings.mcpServers), count: 1 } as T
    if (method === 'PUT' && pathname.startsWith('/mcp_servers/')) return { server_id: pathname.split('/').pop(), config: clone(body) } as T
    if (method === 'DELETE' && pathname.startsWith('/mcp_servers/')) return { server_id: pathname.split('/').pop(), deleted: true } as T
    if (method === 'GET' && pathname === '/research-search/config') return clone(settings.researchSearch) as T
    if (method === 'PUT' && pathname === '/research-search/config') { settings.researchSearch = mergeRecord(settings.researchSearch, body); emit(); return clone(settings.researchSearch) as T }

    throw new DemoEndpointNotImplementedError(method, pathname)
  }

  return {
    request,
    reset: () => { state = clone(demoFixtureSeed); emit() },
    subscribe: listener => { listeners.add(listener); return () => listeners.delete(listener) },
    getSnapshot: () => clone({ conversations: state.conversations, taskStatuses: state.taskStatuses, styles: state.styles, settings: state.settings }),
  }
}

export const demoRuntime = createDemoRuntime()
