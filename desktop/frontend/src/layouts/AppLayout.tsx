import { type FC, type ReactNode, useEffect, useRef, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { Activity, Bell, BookOpen, FilePlus2, Github, LayoutGrid, Moon, PanelLeftClose, PanelLeftOpen, Search, Settings, Settings2, Sun, Trash2, Wrench, X } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useTaskStore } from '@/store/taskStore'
import { getTaskDisplayTitle } from '@/store/taskTitle'
import { cn } from '@/lib/utils'
import { shouldHighlightTaskInSidebar } from './appLayoutNavigation'
import { openExternalUrl } from '@/utils/runtime'
import { useBackendInitContext } from '@/contexts/BackendInitContext.tsx'
import HostApprovalInbox from '@/components/HostApprovalInbox'
import logo from '@/assets/logo.png'

const githubUrl = 'https://github.com/Hehejie1/NoteMeld'
const buildCommit = (import.meta.env.VITE_NOTEMELD_BUILD_COMMIT || 'development').toLowerCase()
interface Props { children: ReactNode }
const navItems = [{ to: '/new', label: '新对话', icon: FilePlus2 }, { to: '/apps', label: '应用', icon: LayoutGrid }, { to: '/applications', label: '能力中心', icon: Wrench }, { to: '/settings', label: '设置', icon: Settings }]
const appItems = [{ to: '/apps/notes', label: '笔记', icon: FilePlus2 }, { to: '/apps/learning', label: '学习', icon: BookOpen }, { to: '/apps/monitoring', label: '监控', icon: Activity }, { to: '/apps/runtime', label: '运行', icon: Settings2 }]

const AppLayout: FC<Props> = ({ children }) => {
  const [collapsed, setCollapsed] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(238)
  const [searchOpen, setSearchOpen] = useState(false)
  const [noticeOpen, setNoticeOpen] = useState(false)
  const [approvalCount, setApprovalCount] = useState(0)
  const [dark, setDark] = useState(() => localStorage.getItem('notemeld-theme') === 'dark')
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null)
  const [query, setQuery] = useState('')
  const draggingRef = useRef(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { backendReady } = useBackendInitContext()
  const shouldDeferConversations = !backendReady
  const tasks = useTaskStore(state => state.tasks)
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const hasLoadedConversations = useTaskStore(state => state.hasLoadedConversations)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const removeTask = useTaskStore(state => state.removeTask)
  const loadConversations = useTaskStore(state => state.loadConversations)

  useEffect(() => { document.documentElement.classList.toggle('dark', dark); localStorage.setItem('notemeld-theme', dark ? 'dark' : 'light') }, [dark])
  useEffect(() => {
    if (backendReady) {
      void loadConversations().catch(error => console.error('加载会话列表失败', error))
    }
  }, [backendReady, loadConversations])
  useEffect(() => {
    const move = (event: MouseEvent) => { if (draggingRef.current && !collapsed) setSidebarWidth(Math.min(360, Math.max(210, event.clientX))) }
    const up = () => { draggingRef.current = false; document.body.style.cursor = ''; document.body.style.userSelect = '' }
    window.addEventListener('mousemove', move); window.addEventListener('mouseup', up)
    return () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up) }
  }, [collapsed])
  const newConversation = () => { setCurrentTask(null); navigate('/new') }
  const selectTask = (id: string) => { setCurrentTask(id); navigate(`/notes/${id}`) }
  const visibleTasks = tasks.filter(task => getTaskDisplayTitle(task).toLowerCase().includes(query.toLowerCase()))
  return <div className="nm-desktop-shell">
    <span className="sr-only" role="note" aria-label={`notemeld-build-commit:${buildCommit}`}>Build commit {buildCommit}</span>
    <aside style={collapsed ? undefined : { width: sidebarWidth }} className={cn('nm-sidebar', collapsed && 'nm-sidebar-collapsed')}>
      <div className="nm-sidebar-header"><button type="button" className="nm-brand" onClick={() => navigate('/new')} aria-label="打开 NoteMeld 新对话"><span className="nm-brand-mark"><img src={logo} alt="" /></span>{!collapsed && <span><strong>NoteMeld</strong><small>本地 Agent 工作台</small></span>}</button>{!collapsed && <button type="button" className="nm-icon-button" onClick={() => setCollapsed(true)} aria-label="收起侧边栏"><PanelLeftClose /></button>}</div>
      {collapsed && <button type="button" className="nm-icon-button nm-expand" onClick={() => setCollapsed(false)} aria-label="展开侧边栏"><PanelLeftOpen /></button>}
      {!collapsed && <div className="nm-sidebar-tools"><button type="button" className={cn('nm-icon-button', noticeOpen && 'is-active')} onClick={() => setNoticeOpen(value => !value)} aria-label={`通知，${approvalCount} 个待审批`}><Bell />{approvalCount > 0 && <i aria-label={`notemeld-host-approval-count:${approvalCount}`} />}</button><button type="button" className={cn('nm-icon-button', searchOpen && 'is-active')} onClick={() => setSearchOpen(value => !value)} aria-label="搜索会话"><Search /></button><span>工作区导航</span></div>}
      {searchOpen && !collapsed && <div className="nm-search-box"><Search /><input autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索会话" aria-label="搜索会话" /><button type="button" onClick={() => { setQuery(''); setSearchOpen(false) }} aria-label="关闭搜索"><X /></button></div>}
      <HostApprovalInbox backendReady={backendReady} visible={noticeOpen && !collapsed} onCountChange={setApprovalCount} />
      <nav className="nm-primary-nav" aria-label="桌面主导航">{navItems.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} end={to === '/new'} className={({ isActive }) => cn('nm-nav-link', isActive && 'is-active')}><Icon /><span>{!collapsed && label}</span></NavLink>)}</nav>
      {!collapsed && location.pathname.startsWith('/apps') && <nav className="nm-app-nav" aria-label="应用导航"><div className="nm-app-nav-label">应用工作区</div>{appItems.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} className={({ isActive }) => cn('nm-nav-link nm-nav-link-sub', isActive && 'is-active')}><Icon /><span>{label}</span></NavLink>)}</nav>}
      {!collapsed && <section className="nm-session-section"><div className="nm-section-heading"><span>会话</span><button type="button" onClick={newConversation} aria-label="新建会话"><FilePlus2 /></button></div><ScrollArea className="nm-session-scroll">{shouldDeferConversations ? <p className="nm-sidebar-empty">后端尚未就绪，笔记列表将在连接成功后自动加载</p> : hasLoadedConversations && visibleTasks.length === 0 ? <p className="nm-sidebar-empty">还没有会话<br /><small>从新对话开始</small></p> : <div className="nm-session-list">{visibleTasks.map(task => { const active = shouldHighlightTaskInSidebar(location.pathname, task.id, currentTaskId); const title = getTaskDisplayTitle(task); return <div className={cn('nm-session-row', active && 'is-active')} key={task.id}><button type="button" onClick={() => selectTask(task.id)} title={title}><i className={task.noteState === 'failed' || task.status === 'FAILED' ? 'is-error' : task.noteState === 'ready' || task.linkedNoteTaskId ? 'is-ready' : ''} /><span>{title}</span></button><button type="button" className="nm-session-delete" onClick={() => setDeleteTarget({ id: task.id, title })} aria-label={`删除 ${title}`}><Trash2 /></button></div> })}</div>}</ScrollArea></section>}
      <div className="nm-sidebar-footer">{!collapsed && <div className="nm-connection"><i />{backendReady ? '本地 Agent 已连接' : '正在连接本地 Agent'}</div>}<button type="button" className="nm-theme-toggle" onClick={() => setDark(value => !value)} aria-label="切换浅色或深色模式">{dark ? <Moon /> : <Sun />}{!collapsed && <span>{dark ? '深色' : '浅色'}</span>}</button>{!collapsed && <a href={githubUrl} onClick={event => { event.preventDefault(); void openExternalUrl(githubUrl) }}><Github />GitHub</a>}</div>
    </aside>
    {!collapsed && <div className="nm-sidebar-resizer" onMouseDown={event => { event.preventDefault(); draggingRef.current = true; document.body.style.cursor = 'col-resize'; document.body.style.userSelect = 'none' }} aria-label="调整侧边栏宽度" />}
    <main className="nm-desktop-main">{children}</main>
    <Dialog open={!!deleteTarget} onOpenChange={open => !open && setDeleteTarget(null)}><DialogContent><DialogHeader><DialogTitle>删除这条会话？</DialogTitle><DialogDescription>将永久删除「{deleteTarget?.title}」，此操作不可撤销。</DialogDescription></DialogHeader><DialogFooter><Button variant="outline" onClick={() => setDeleteTarget(null)}>取消</Button><Button variant="destructive" onClick={() => { if (deleteTarget) { removeTask(deleteTarget.id); if (deleteTarget.id === currentTaskId) newConversation(); setDeleteTarget(null) } }}>确定删除</Button></DialogFooter></DialogContent></Dialog>
  </div>
}
export default AppLayout
