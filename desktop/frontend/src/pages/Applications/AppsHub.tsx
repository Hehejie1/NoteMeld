import { Activity, BookOpen, FileText, LayoutGrid, Settings2 } from 'lucide-react'
import { Link } from 'react-router-dom'

const apps = [
  { to: '/apps/notes', title: '笔记应用', description: '笔记库、样式模板、Wiki 图谱和 Markdown 导入。', icon: FileText },
  { to: '/apps/learning', title: '学习应用', description: '学习空间、语义画布、掌握验证和复习。', icon: BookOpen },
  { to: '/apps/monitoring', title: '监控应用', description: 'Token、任务、部署、GPU、MCP 和插件健康。', icon: Activity },
  { to: '/apps/runtime', title: '系统运行', description: 'Agent 诊断、Application、审批、更新和设备连接。', icon: Settings2 },
]

export default function AppsHub() {
  return (
    <div className="h-full overflow-auto bg-surface px-5 py-6 md:px-8">
      <div className="mx-auto max-w-5xl">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary"><LayoutGrid className="h-5 w-5" /></div>
          <div><div className="text-[11px] font-medium tracking-[0.16em] text-on-surface-variant">APPLICATIONS</div><h1 className="mt-1 font-display text-2xl font-bold text-on-surface">应用</h1><p className="mt-2 text-sm text-on-surface-variant">把知识工作、学习和系统运行拆成清晰的业务工作区。</p></div>
        </div>
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          {apps.map(({ to, title, description, icon: Icon }) => <Link key={to} to={to} className="group rounded-2xl border border-border-subtle bg-surface-container-low p-5 transition hover:border-primary/40 hover:bg-primary/[0.03] focus:outline-none focus:ring-2 focus:ring-primary/40"><div className="flex items-center justify-between"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary"><Icon className="h-5 w-5" /></div><span className="text-sm text-on-surface-variant transition group-hover:translate-x-1">打开 →</span></div><h2 className="mt-5 text-lg font-semibold text-on-surface">{title}</h2><p className="mt-2 text-sm leading-6 text-on-surface-variant">{description}</p></Link>)}
        </div>
      </div>
    </div>
  )
}
