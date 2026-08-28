import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle, Ban, CircleAlert, LoaderCircle, RefreshCw, ShieldAlert } from 'lucide-react'

import KnowledgeEmptyState from '@/components/KnowledgeEmptyState'
import { Button } from '@/components/ui/button'
import {
  createApplicationInstance,
  cancelApplicationRun,
  getApplication,
  getApplicationRun,
  listApplicationInstances,
  startApplicationRun,
  invokeApplicationCapability,
  type ApplicationDetail,
  type ApplicationRun,
} from '@/services/applications'
import { useBackendInitContext } from '@/contexts/BackendInitContext'

export type HostUiState = 'starting' | 'running' | 'disabled' | 'capability-missing' | 'failed' | 'interrupted'

interface ApplicationHostProps {
  applicationId: string
}

const stateCopy: Record<HostUiState, { title: string; description: string }> = {
  starting: { title: '正在启动应用', description: 'Application Host 正在校验应用声明并准备运行实例。' },
  running: { title: '应用运行中', description: '应用已由 NoteMeld Host 启动，正在加载自己的界面。' },
  disabled: { title: '应用已禁用', description: '这个应用当前被禁用，请在应用列表中重新启用后再打开。' },
  'capability-missing': { title: '应用能力不可用', description: '宿主没有提供该应用声明所需的能力，应用已安全停止。' },
  failed: { title: '应用启动失败', description: '应用没有成功启动。可以重新加载应用状态后重试。' },
  interrupted: { title: '应用运行已中断', description: '宿主检测到应用运行被中断，已保留安全诊断。' },
}

const HostState = ({ state, detail, error, onRetry }: { state: HostUiState; detail?: ApplicationDetail | null; error?: string; onRetry: () => void }) => {
  const copy = stateCopy[state]
  const Icon = state === 'disabled' ? Ban : state === 'capability-missing' ? ShieldAlert : state === 'interrupted' ? AlertTriangle : CircleAlert
  return (
    <div className="flex h-full items-center justify-center px-6">
      <section role="alert" className="w-full max-w-lg rounded-2xl border border-border-subtle bg-white p-7 shadow-sm">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-surface-container text-primary"><Icon className="h-5 w-5" /></div>
        <h1 className="mt-5 font-display text-xl font-bold text-on-surface">{copy.title}</h1>
        <p className="mt-2 text-sm leading-6 text-on-surface-variant">{copy.description}</p>
        {detail?.missing_capabilities && detail.missing_capabilities.length > 0 && <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">缺少能力：{detail.missing_capabilities.join('、')}</p>}
        {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs leading-5 text-red-700">{error}</p>}
        {state !== 'disabled' && <Button variant="outline" size="sm" onClick={onRetry} className="mt-5"><RefreshCw className="mr-2 h-3.5 w-3.5" />重新加载</Button>}
      </section>
    </div>
  )
}

export const ApplicationHost = ({ applicationId }: ApplicationHostProps) => {
  const { backendReady } = useBackendInitContext()
  const [detail, setDetail] = useState<ApplicationDetail | null>(null)
  const [run, setRun] = useState<ApplicationRun | null>(null)
  const [state, setState] = useState<HostUiState>('starting')
  const [error, setError] = useState('')
  const applicationFrameRef = useRef<HTMLIFrameElement | null>(null)

  const start = useCallback(async () => {
    if (!backendReady) return
    setState('starting')
    setError('')
    setRun(null)
    try {
      const nextDetail = await getApplication(applicationId)
      setDetail(nextDetail)
      if (!nextDetail.enabled || nextDetail.status === 'disabled') {
        setState('disabled')
        return
      }
      if ((nextDetail.missing_capabilities?.length || 0) > 0) {
        setState('capability-missing')
        return
      }
      const instances = await listApplicationInstances(applicationId)
      const instance = instances[0] || await createApplicationInstance(applicationId, { title: nextDetail.name })
      const nextRun = await startApplicationRun(applicationId, instance.id)
      setRun(nextRun)
      if (nextRun.status === 'interrupted') setState('interrupted')
      else if (nextRun.status === 'failed') setState('failed')
      else setState('running')
    } catch (cause) {
      setState('failed')
      setError(cause && typeof cause === 'object' && 'msg' in cause ? String(cause.msg) : 'Host 无法建立应用运行实例')
    }
  }, [applicationId, backendReady])

  useEffect(() => {
    if (!run || !detail || state !== 'running') return
    const frame = applicationFrameRef.current
    if (!frame) return
    const onMessage = async (event: MessageEvent) => {
      if (event.source !== frame.contentWindow) return
      const message = event.data
      if (!message || message.app_id !== applicationId || message.run_id !== run.run_id) return
      if (message.type === 'notemeld.application.ready' && message.app_id === applicationId && message.run_id === run.run_id) {
        frame.contentWindow?.postMessage({ type: 'notemeld.application.host-ready', app_id: applicationId, run_id: run.run_id }, '*')
        return
      }
      if (message.type !== 'notemeld.application.invoke') return
      const respond = (payload: Record<string, unknown>) => frame.contentWindow?.postMessage({ type: 'notemeld.application.result', request_id: message.request_id, ...payload }, '*')
      try {
        const result = await invokeApplicationCapability(run.run_id, message.capability, message.method, message.input || {})
        respond({ ok: true, result })
      } catch (cause) {
        respond({ ok: false, error: { code: 'capability_failed', message: cause && typeof cause === 'object' && 'msg' in cause ? String(cause.msg) : '应用能力调用失败' } })
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [applicationId, detail, run, state])

  useEffect(() => {
    if (backendReady) void start()
  }, [backendReady, start])

  useEffect(() => {
    if (!run || !['queued', 'running', 'waiting_user'].includes(run.status)) return
    const timer = window.setInterval(() => {
      void getApplicationRun(run.run_id).then(nextRun => {
        setRun(nextRun)
        if (nextRun.status === 'interrupted') setState('interrupted')
        if (nextRun.status === 'failed') setState('failed')
      }).catch(() => undefined)
    }, 2500)
    return () => window.clearInterval(timer)
  }, [run])

  const activeRunRef = useRef<ApplicationRun | null>(null)
  activeRunRef.current = run
  useEffect(() => () => {
    const activeRun = activeRunRef.current
    if (activeRun && ['queued', 'running', 'waiting_user'].includes(activeRun.status)) {
      void cancelApplicationRun(activeRun.run_id)
    }
  }, [])

  if (!backendReady) return <KnowledgeEmptyState status="loading" title="等待后端就绪" description="应用请求会在桌面 sidecar ready 后自动开始。" />
  if (state !== 'running') return <HostState state={state} detail={detail} error={error || run?.error?.message || undefined} onRetry={() => void start()} />
  if (!run || !detail?.ui?.entry) return <HostState state="failed" detail={detail} error="应用包缺少 UI 入口" onRetry={() => void start()} />
  const assetEntry = detail.ui.entry.split('/').map(encodeURIComponent).join('/')
  const applicationUrl = `/api/applications/${encodeURIComponent(applicationId)}/assets/${assetEntry}?app_id=${encodeURIComponent(applicationId)}&run_id=${encodeURIComponent(run.run_id)}`
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-border-subtle/70 bg-white px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-3"><span className="h-2 w-2 rounded-full bg-emerald-500" aria-label="运行中" /><div className="min-w-0"><div className="truncate text-sm font-semibold text-on-surface">{detail.name}</div><div className="truncate text-[11px] text-on-surface-variant">{detail.description}</div></div></div>
        <span className="shrink-0 text-[11px] font-medium text-emerald-700">Host 运行中</span>
      </div>
      <div className="min-h-0 flex-1"><iframe ref={applicationFrameRef} title={detail.name} src={applicationUrl} onLoad={() => applicationFrameRef.current?.contentWindow?.postMessage({ type: 'notemeld.application.host-ready', run_id: run.run_id }, '*')} className="h-full w-full border-0" sandbox="allow-scripts" /></div>
    </div>
  )
}

export const ApplicationHostLoading = ({ children }: { children?: ReactNode }) => (
  <div className="flex h-full items-center justify-center"><LoaderCircle className="mr-2 h-4 w-4 animate-spin text-primary" />{children || '正在读取应用…'}</div>
)
