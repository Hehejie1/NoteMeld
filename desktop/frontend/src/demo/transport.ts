import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type { FreeChatPayload, FreeChatStreamHandlers } from '@/services/chat'
import type { DesktopUpdateCheckResult, DesktopUpdateProgress } from '@/services/desktopUpdater'
import { demoRuntime } from './runtime.ts'
import type { DemoMethod } from './types.ts'

const methodOf = (config: InternalAxiosRequestConfig): DemoMethod =>
  String(config.method || 'GET').toUpperCase() as DemoMethod

export const createDemoAxiosAdapter = (): AxiosAdapter => async config => {
  const data = await demoRuntime.request({
    method: methodOf(config),
    path: config.url || '/',
    body: config.data,
    query: config.params,
  })
  return {
    data: { code: 0, msg: 'success', data },
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
    request: { demo: true },
  } as AxiosResponse
}

const wait = (milliseconds: number) => new Promise(resolve => window.setTimeout(resolve, milliseconds))

export const demoStreamFreeChat = async (
  payload: FreeChatPayload,
  handlers: FreeChatStreamHandlers,
): Promise<void> => {
  const answer = payload.question.includes('区别')
    ? '核心区别是 Agent 会围绕目标规划、调用工具并根据反馈继续行动；普通大模型主要完成一次输入到输出。'
    : '这是静态演示回复。它复用了正式消息渲染，但不会调用任何模型或后端服务。'
  for (const chunk of ['正在读取演示知识…\n\n', answer]) {
    await wait(180)
    handlers.onDelta(chunk)
  }
  handlers.onDone({
    answer: `正在读取演示知识…\n\n${answer}`,
    sources: [{ text: 'Agent 通过规划、工具和反馈形成闭环。', title: 'AI Agent 演示笔记', type: 'note', snippet: 'Agent 通过规划、工具和反馈形成闭环。' }],
  })
}

export const demoDesktopAction = async (action: string, value?: unknown): Promise<unknown> => {
  if (action === 'get_autostart_enabled') return false
  if (action === 'set_autostart_enabled') return value ?? true
  if (action === 'select_migration_package') return 'demo-migration-package.zip'
  if (action === 'select_export_package') return 'notemeld-demo-export.zip'
  return null
}

export const demoCheckUpdate = async (): Promise<DesktopUpdateCheckResult> => ({
  status: 'available',
  version: '0.0.5-demo',
  date: '2026-08-13',
  body: '静态演示：展示版本检查和下载流程，不会访问更新服务。',
})

export const demoInstallUpdate = async (
  onProgress?: (progress: DesktopUpdateProgress) => void,
): Promise<void> => {
  onProgress?.({ phase: 'started', total: 100 })
  await wait(180)
  onProgress?.({ phase: 'progress', downloaded: 64, total: 100 })
  await wait(180)
  onProgress?.({ phase: 'finished', downloaded: 100, total: 100 })
}
