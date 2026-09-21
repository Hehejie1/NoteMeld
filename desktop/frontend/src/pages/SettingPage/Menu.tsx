import {
  BotMessageSquare,
  Captions,
  HardDriveDownload,
  Activity,
  BarChart3,
  Database,
  Plug,
  Search,
  Puzzle,
  ListChecks,
  ShieldCheck,
} from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { JSX } from 'react'

interface MenuItem {
  id: string
  name: string
  icon: JSX.Element
  path: string
}

const menuList: MenuItem[] = [
  { id: 'model', name: 'AI 模型设置', icon: <BotMessageSquare className="h-4 w-4" />, path: '/settings/model' },
  { id: 'transcriber', name: '音频转写配置', icon: <Captions className="h-4 w-4" />, path: '/settings/transcriber' },
  { id: 'download', name: '下载配置', icon: <HardDriveDownload className="h-4 w-4" />, path: '/settings/download' },
  { id: 'data-migration', name: '数据与迁移', icon: <Database className="h-4 w-4" />, path: '/settings/data-migration' },
  { id: 'usage', name: 'Token 消耗', icon: <BarChart3 className="h-4 w-4" />, path: '/settings/usage' },
  { id: 'monitor', name: '部署监控', icon: <Activity className="h-4 w-4" />, path: '/settings/monitor' },
  { id: 'mcp-servers', name: 'MCP 服务器', icon: <Plug className="h-4 w-4" />, path: '/settings/mcp-servers' },
  { id: 'research-search', name: '研究搜索', icon: <Search className="h-4 w-4" />, path: '/settings/research-search' },
  { id: 'plugins', name: '插件运行', icon: <Puzzle className="h-4 w-4" />, path: '/settings/plugins' },
  { id: 'applications', name: '应用设置', icon: <Puzzle className="h-4 w-4" />, path: '/settings/applications' },
  { id: 'agent-diagnostics', name: 'Agent 任务诊断', icon: <ListChecks className="h-4 w-4" />, path: '/settings/agent-diagnostics' },
  { id: 'candidates', name: '候选审批', icon: <ShieldCheck className="h-4 w-4" />, path: '/settings/candidates' },
]

const menuGroups: Array<[string, string[]]> = [
  ['模型与输入', ['model', 'transcriber', 'download']],
  ['数据与连接', ['data-migration', 'mcp-servers', 'research-search']],
  ['运行与诊断', ['plugins', 'applications', 'usage', 'monitor', 'agent-diagnostics', 'candidates']],
]

const Menu = () => {
  const location = useLocation()

  return (
    <nav role="tablist" className="grid gap-5 overflow-visible">
      {menuGroups.map(([groupName, ids]) => <section key={groupName} className="grid gap-1">
        <h2 className="px-2 text-[10px] font-semibold tracking-[0.12em] text-on-surface-variant/70">{groupName}</h2>
        {ids.map(id => {
          const item = menuList.find(candidate => candidate.id === id)
          if (!item) return null
        const isActive =
          location.pathname === item.path || location.pathname.startsWith(item.path + '/')
        return (
          <Link
            key={item.id}
            to={item.path}
            role="tab"
            aria-selected={isActive}
            className={[
              'group relative flex min-h-11 items-center gap-1.5 px-3 py-3 text-sm whitespace-nowrap transition-colors md:gap-2 md:px-4',
              isActive
                ? 'font-semibold text-primary'
                : 'font-medium text-on-surface-variant hover:text-on-surface',
            ].join(' ')}
          >
            <span
              className={isActive ? 'text-primary' : 'text-on-surface-variant group-hover:text-on-surface'}
            >
              {item.icon}
            </span>
            <span>{item.name}</span>
            <span
              aria-hidden
              className={[
                'absolute inset-x-2 -bottom-px h-[2px] rounded-full transition-all',
                isActive ? 'bg-primary opacity-100' : 'bg-transparent opacity-0',
              ].join(' ')}
            />
          </Link>
        )
        })}
      </section>)}
    </nav>
  )
}
export default Menu
