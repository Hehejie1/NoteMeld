import { useEffect, useState } from 'react'
import { ChevronRight, CircleAlert, PackageOpen, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'

import KnowledgeEmptyState from '@/components/KnowledgeEmptyState'
import { Button } from '@/components/ui/button'
import { listApplications, type ApplicationSummary } from '@/services/applications'
import { useBackendInitContext } from '@/contexts/BackendInitContext'

const statusLabel: Record<ApplicationSummary['status'], string> = {
  installed: '已安装',
  disabled: '已禁用',
  starting: '启动中',
  running: '运行中',
  stopped: '已停止',
  failed: '启动失败',
  needs_attention: '需要处理',
}

const ApplicationList = () => {
  const { backendReady } = useBackendInitContext()
  const [applications, setApplications] = useState<ApplicationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      setApplications(await listApplications())
    } catch {
      setError('应用列表加载失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (backendReady) void load()
  }, [backendReady])

  if (!backendReady || loading) return <KnowledgeEmptyState status="loading" title="正在读取应用" description="Application Host 正在读取可用的内建应用。" />
  if (error) return <div className="flex h-full items-center justify-center px-6"><KnowledgeEmptyState status="error" title="应用列表暂时无法打开" description="宿主应用清单读取失败，可以刷新后重试。" detail={error} action={<Button variant="outline" size="sm" onClick={() => void load()}><RefreshCw className="mr-2 h-3.5 w-3.5" />重新加载</Button>} /></div>

  return (
    <div className="h-full overflow-auto bg-surface px-5 py-6 md:px-8">
      <div className="mx-auto max-w-4xl">
        <div className="flex items-start justify-between gap-4"><div><div className="text-[11px] font-medium tracking-[0.16em] text-on-surface-variant">APPLICATION HOST</div><h1 className="mt-2 font-display text-2xl font-bold text-on-surface">应用</h1><p className="mt-2 text-sm text-on-surface-variant">由 NoteMeld Host 管理的内建应用及其运行状态。</p></div><Button variant="ghost" size="sm" onClick={() => void load()} disabled={loading} aria-label="刷新应用列表"><RefreshCw className={loading ? 'animate-spin' : ''} /></Button></div>
        {applications.length === 0 ? <div className="mt-10"><KnowledgeEmptyState title="还没有可用应用" description="应用包安装后会出现在这里。" /></div> : <div className="mt-7 grid gap-3 md:grid-cols-2">{applications.map(application => <ApplicationCard key={application.id} application={application} />)}</div>}
      </div>
    </div>
  )
}

const ApplicationCard = ({ application }: { application: ApplicationSummary }) => {
  const blocked = !application.enabled || application.status === 'disabled' || (application.missing_capabilities?.length || 0) > 0
  return <Link to={`/applications/${encodeURIComponent(application.id)}`} className="group rounded-xl border border-border-subtle bg-white p-5 shadow-sm transition-colors hover:border-primary/40 hover:bg-primary/[0.02] focus:outline-none focus:ring-2 focus:ring-primary/40"><div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-center gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-surface-container text-primary"><PackageOpen className="h-5 w-5" /></div><div className="min-w-0"><h2 className="truncate font-semibold text-on-surface">{application.name}</h2><p className="mt-0.5 text-xs text-on-surface-variant">v{application.version}</p></div></div><ChevronRight className="h-4 w-4 shrink-0 text-on-surface-variant transition-transform group-hover:translate-x-0.5" /></div><p className="mt-4 min-h-10 text-sm leading-5 text-on-surface-variant">{application.description || '内建 NoteMeld 应用'}</p><div className="mt-4 flex flex-wrap items-center gap-2 text-xs"><span className={application.status === 'running' ? 'rounded-full bg-emerald-50 px-2 py-1 text-emerald-700' : 'rounded-full bg-surface-container px-2 py-1 text-on-surface-variant'}>{statusLabel[application.status]}</span>{blocked && <span className="inline-flex items-center gap-1 text-amber-700"><CircleAlert className="h-3.5 w-3.5" />{application.missing_capabilities?.length ? '能力缺失' : '不可用'}</span>}</div></Link>
}

export default ApplicationList
