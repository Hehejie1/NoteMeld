import { FC, SVGProps, useState, useRef, useEffect, ReactNode, type MouseEvent } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  PanelLeftClose,
  PanelLeftOpen,
  FilePlus2,
  LayoutTemplate,
  Network,
  Settings,
  GithubIcon,
  Trash2,
  Menu as MenuIcon,
} from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useTaskStore } from '@/store/taskStore'
import { getTaskDisplayTitle } from '@/store/taskTitle'
import { cn } from '@/lib/utils'
import { shouldHighlightTaskInSidebar } from './appLayoutNavigation'
import { openExternalUrl } from '@/utils/runtime'
import { useBackendInitContext } from '@/contexts/BackendInitContext.tsx'

const logo = '/notemeld-logo.png'
const githubUrl = 'https://github.com/Hehejie1/NoteMeld'

interface IProps {
  children: ReactNode
}

interface NavItem {
  to: string
  label: string
  icon: ReactNode
  exact?: boolean
}

const AboutIcon = (props: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 1024 1024" fill="none" aria-hidden="true" {...props}>
    <path
      fill="currentColor"
      d="M300.931 453.164c11.498-2.588 18.741-14.015 16.153-25.533-5.442-24.163-6.26-48.98-2.435-73.715C331.334 245.86 432.802 171.54 540.95 188.287c25.503 3.939 49.542 12.593 71.424 25.697 10.158 6.066 23.241 2.772 29.297-7.345 6.046-10.127 2.752-23.242-7.355-29.297-26.658-15.949-55.885-26.475-86.84-31.262-131.267-20.316-254.739 69.98-275.065 201.33-4.624 30.055-3.621 60.201 2.987 89.591 2.23 9.954 11.048 16.695 20.817 16.695 1.566-0.01 3.14-0.205 4.716-0.532zM895.377 612.43c0-30.536-11.989-57.46-32.141-76.089 20.224-46.708 31.579-98.082 31.579-152.104C894.815 172.37 722.455 0 510.609 0 298.752 0 126.382 172.37 126.382 384.237c0 126.888 61.982 239.394 157.128 309.396a106.695 106.695 0 0 0 2.64 11.396c3.62 12.367 8.623 23.446 14.945 33.052 34.453 52.54 73.5 112.045 112.24 170.058 39.24 58.739 96.036 95.269 168.8 108.557 9.165 1.606 17.543 2.71 25.625 3.744 3.887 0.522 7.785 1.033 11.641 1.575 3.049 0.45 6.138 0.655 9.217 0.655h43.394c3.407 0 6.834-0.235 10.21-0.818 3.815-0.624 7.631-1.207 11.488-1.8a2627.417 2627.417 0 0 0 19.702-3.151c91.924-15.867 161.291-84.999 176.84-176.217 3.182-18.229 4.829-36.714 4.9-54.77 0.215-68.456 0.215-77.039 0.205-104.73 0-14.2 0-33.523 0.02-68.754zM190.451 384.226c0-176.85 143.348-320.168 320.158-320.168s320.158 143.318 320.158 320.168c0 44.878-9.401 87.495-26.086 126.265-2.997-0.286-5.995-0.49-9.002-0.49a99.295 99.295 0 0 0-26.955 3.712c-9.984-9.442-21.922-16.827-35.323-21.43-2.23-0.727-4.45-1.371-6.65-1.955 10.537-21.318 18.179-44.509 21.984-69.265 8.255-53.245-1.146-106.255-27.18-153.332-5.698-10.312-18.69-14.066-29.022-8.358-10.311 5.708-14.045 18.7-8.347 29.022 21.41 38.709 29.144 82.338 22.352 126.132-4.297 27.64-14.22 52.918-28.337 75.096-1.268 0.296-2.598 0.43-3.846 0.777-8.777-8.071-19.314-14.72-31.374-19.784-9.197-4.9-19.498-7.447-29.994-7.447h-2.158c0-27.508 0-53.604-0.03-74.534 0-52.007-34.526-92.425-85.95-100.506a92.302 92.302 0 0 0-14.373-1.146c-50.269 0-94.471 40.418-98.512 90.093-0.48 6.383-0.48 11.743-0.48 16.05v162.58c-19.938-11.447-37.932-26.28-52.95-44.223-7.549-9.043-21.001-10.25-30.085-2.68-9.033 7.57-10.23 21.043-2.68 30.096 10.424 12.44 22.096 23.59 34.627 33.574-25.952 6.618-48.703 23.19-62.881 46.412-0.553 0.9-0.972 1.841-1.494 2.751-64.795-58.595-105.57-143.194-105.57-237.41zM831.094 785.7c-0.072 14.72-1.463 29.645-3.99 44.213-10.976 64.426-59.792 112.68-124.433 123.82-10.158 1.718-20.44 3.242-30.648 4.9h-43.395c-11.63-1.72-23.374-2.936-34.965-5.003-53.337-9.728-96.64-35.579-127.021-81.08-37.666-56.366-74.81-112.956-111.964-169.598-3.14-4.777-5.38-10.332-7.007-15.825-6.946-23.927 7.16-48.663 30.71-53.215 3.416-0.644 6.74-0.992 9.891-0.992 14.311 0 26.515 6.465 35.855 18.567 15.57 20.132 30.29 40.918 45.358 61.419a369.923 369.923 0 0 0 4.84 6.516c0.388-0.174 0.818-0.297 1.216-0.491v-5.75-320.065c0-3.642 0-7.243 0.277-10.874 1.38-16.89 17.86-31.19 34.658-31.19 1.452 0 2.956 0.122 4.43 0.358 19.875 3.13 31.844 16.94 31.844 37.266 0.051 56.97 0 152.32 0.082 209.34 0 2.957 0.194 6.056 1.064 8.86 1.463 4.613 4.94 7.078 9.882 7.456h1.053c4.716 0 8.205-2.363 10.056-6.587 1.187-2.62 1.258-5.831 1.258-8.818 0-19.61-0.05-25.79-0.05-25.79l-0.072 18.23c0-0.061 0-6.302 0.05-25.8 0-12.878 4.318-24.08 15.274-31.69 4.03-2.753 8.828-4.471 13.257-6.64h14.394c0.511 0.368 0.92 0.839 1.473 1.044 18.72 6.444 27.425 18.577 27.425 38.258-0.061 19.314-0.061 25.462-0.061 25.462l-0.02-18.792v25.493c0 1.84-0.062 3.62 0.132 5.4 0.778 6.149 5.514 10.23 11.478 10.23 0.389 0 0.737 0 1.115-0.02 6.312-0.573 9.923-4.88 10.363-12.675v-0.194c0.03-0.47 0.03-0.961 0.03-1.432v-12.122c0.277-8.389 2.343-16.296 7.744-23.13 7.09-8.991 17.411-13.881 28.183-13.881 3.908 0 7.877 0.655 11.734 1.954 14.792 5.104 24.254 19.446 24.254 36.591-0.02 19.314-0.051 25.482-0.051 25.482-0.01 0-0.051-18.812-0.072-18.812 0 0-0.01 6.148-0.01 25.503 0 2.199 0 4.429 0.235 6.608 0.706 5.8 4.47 8.797 9.862 9.861a7.59 7.59 0 0 0 1.677 0.164c4.256 0 8.788-2.967 10.23-7.243 0.92-2.772 1.177-5.861 1.177-8.859 0-2.618 0-4.88 0.01-6.772v12.982c0.071 0 0.112-3.887 0.153-15.16 0.072-6.25 1.197-12.92 3.673-18.629 5.636-12.787 18.597-20.52 31.957-20.52 2.466 0 4.9 0.286 7.355 0.818 17.32 3.785 28.265 18.485 28.265 37.522-0.062 103.545 0.102 69.777-0.215 173.332z"
    />
  </svg>
)

const navItems: NavItem[] = [
  { to: '/new', label: '新建笔记', icon: <FilePlus2 className="h-[18px] w-[18px]" />, exact: true },
  { to: '/styles', label: '风格模板', icon: <LayoutTemplate className="h-[18px] w-[18px]" /> },
  { to: '/wiki', label: '知识库', icon: <Network className="h-[18px] w-[18px]" /> },
  { to: '/settings', label: '设置', icon: <Settings className="h-[18px] w-[18px]" /> },
  { to: '/about', label: '关于', icon: <AboutIcon className="h-[18px] w-[18px]" /> },
]

const hasMarkdown = (markdown: any): boolean => {
  if (Array.isArray(markdown)) return markdown.length > 0
  return !!markdown
}

const getConversationDotClass = (task: any): string => {
  if (task.noteState === 'failed' || task.status === 'FAILED') return 'bg-destructive'
  if (task.noteState === 'ready' || task.linkedNoteTaskId || hasMarkdown(task.markdown)) return 'bg-primary'
  return 'bg-on-surface-variant/40'
}

const AppLayout: FC<IProps> = ({ children }) => {
  const [collapsed, setCollapsed] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(260)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const draggingRef = useRef(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { backendReady } = useBackendInitContext()

  useEffect(() => {
    const media = window.matchMedia('(max-width: 767px)')
    const sync = () => setIsMobile(media.matches)
    sync()
    media.addEventListener('change', sync)
    return () => media.removeEventListener('change', sync)
  }, [])

  // 拖拽侧边栏宽度
  useEffect(() => {
    const onMove = (e: globalThis.MouseEvent) => {
      if (!draggingRef.current) return
      const next = Math.min(420, Math.max(200, e.clientX))
      setSidebarWidth(next)
    }
    const onUp = () => {
      if (draggingRef.current) {
        draggingRef.current = false
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  const startSidebarDrag = (e: React.MouseEvent) => {
    if (collapsed) return
    e.preventDefault()
    draggingRef.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  const tasks = useTaskStore(state => state.tasks)
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const hasLoadedConversations = useTaskStore(state => state.hasLoadedConversations)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const removeTask = useTaskStore(state => state.removeTask)
  const loadConversations = useTaskStore(state => state.loadConversations)
  const shouldDeferConversations = !backendReady

  // 删除确认目标（null 表示弹窗关闭）
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; title: string } | null>(null)
  const openGithub = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault()
    openExternalUrl(githubUrl).catch(error => {
      console.warn('failed to open github link', error)
    })
  }

  // "新建笔记" 仅在 /new 高亮，不在 /notes/:taskId
  const onNewRoot = location.pathname === '/new'

  useEffect(() => {
    if (backendReady) {
      loadConversations().catch(err => {
        console.error('加载会话列表失败', err)
      })
    }
  }, [backendReady, loadConversations])

  const handleSelectTask = (taskId: string) => {
    setCurrentTask(taskId)
    navigate(`/notes/${taskId}`)
  }

  const handleNewNote = () => {
    setCurrentTask(null)
    navigate('/new')
  }

  if (isMobile) {
    const mobileNavItems = [
      { to: '/new', label: '新建', icon: <FilePlus2 className="h-5 w-5" /> },
      { to: '/wiki', label: '知识库', icon: <Network className="h-5 w-5" /> },
      { to: '/styles', label: '风格', icon: <LayoutTemplate className="h-5 w-5" /> },
      { to: '/settings', label: '设置', icon: <Settings className="h-5 w-5" /> },
    ]

    return (
      <div className="flex h-app w-full flex-col overflow-hidden bg-surface">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border-subtle/70 bg-white/95 px-3 backdrop-blur-xl">
          <button
            type="button"
            onClick={() => setMobileMenuOpen(true)}
            className="flex h-10 w-10 items-center justify-center rounded-xl text-on-surface-variant active:bg-surface-container"
            aria-label="打开笔记列表"
          >
            <MenuIcon className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={() => navigate('/')}
            className="flex min-w-0 flex-1 items-center justify-center gap-2 px-2"
            aria-label="返回首页"
          >
            <img src={logo} alt="" className="h-8 w-8 shrink-0 rounded-lg bg-[#0e0d2a]" />
            <span className="grid min-w-0 gap-0.5 text-left leading-none">
              <span className="font-display truncate text-[15px] font-bold text-on-surface">
                NoteMeld
              </span>
              <span className="truncate text-[10px] font-medium text-on-surface-variant">
                源知库 · 你的专属知识库
              </span>
            </span>
          </button>
          <button
            type="button"
            onClick={handleNewNote}
            className="flex h-10 w-10 items-center justify-center rounded-xl text-primary active:bg-primary-light"
            aria-label="新建笔记"
          >
            <FilePlus2 className="h-5 w-5" />
          </button>
        </header>

        <main className="min-h-0 flex-1 overflow-hidden pb-mobile-nav">{children}</main>

        <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-border-subtle/70 bg-white/95 px-2 pt-1 backdrop-blur-xl">
          <div className="grid h-[var(--mobile-bottom-nav-height)] grid-cols-4">
            {mobileNavItems.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex flex-col items-center justify-center gap-1 rounded-xl text-[11px] font-medium transition-colors',
                    isActive ? 'text-primary' : 'text-on-surface-variant',
                  )
                }
              >
                {item.icon}
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </nav>

        {mobileMenuOpen && (
          <div
            className="fixed inset-0 z-50 bg-black/30"
            onClick={() => setMobileMenuOpen(false)}
          >
            <aside
              className="h-full w-[84vw] max-w-[340px] overflow-hidden bg-sidebar shadow-2xl"
              onClick={event => event.stopPropagation()}
            >
              <div className="flex h-14 items-center justify-between border-b border-border-subtle/70 px-4">
                <span className="font-display text-[16px] font-bold text-on-surface">笔记列表</span>
                <button
                  type="button"
                  onClick={() => setMobileMenuOpen(false)}
                  className="rounded-lg px-3 py-2 text-[13px] text-on-surface-variant active:bg-surface-container"
                >
                  关闭
                </button>
              </div>
              <ScrollArea className="h-[calc(100%-56px)] px-2 py-3">
                {shouldDeferConversations ? (
                  <div className="px-4 py-10 text-center text-[13px] text-sidebar-muted">
                    后端尚未就绪，笔记列表将在连接成功后自动加载
                  </div>
                ) : hasLoadedConversations && tasks.length === 0 ? (
                  <div className="px-4 py-10 text-center text-[13px] text-sidebar-muted">
                    还没有沉淀内容
                  </div>
                ) : (
                  <ul className="space-y-1">
                    {tasks.map(task => {
                      const title = getTaskDisplayTitle(task)
                      const active = shouldHighlightTaskInSidebar(
                        location.pathname,
                        task.id,
                        currentTaskId,
                      )
                      return (
                        <li key={task.id}>
                          <button
                            type="button"
                            onClick={() => {
                              handleSelectTask(task.id)
                              setMobileMenuOpen(false)
                            }}
                            className={cn(
                              'flex min-h-11 w-full items-center gap-2 rounded-xl px-3 text-left text-[14px]',
                              active
                                ? 'bg-sidebar-active-bg font-medium text-sidebar-active-fg'
                                : 'text-sidebar-fg active:bg-surface-container',
                            )}
                            title={title}
                          >
                            <span
                              className={cn(
                                'h-2 w-2 shrink-0 rounded-full',
                                getConversationDotClass(task),
                              )}
                            />
                            <span className="min-w-0 flex-1 truncate">{title}</span>
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </ScrollArea>
            </aside>
          </div>
        )}

        <Dialog
          open={!!deleteTarget}
          onOpenChange={(open: boolean) => !open && setDeleteTarget(null)}
        >
          <DialogContent className="max-w-[calc(100vw-32px)]">
            <DialogHeader>
              <DialogTitle>删除这条对话？</DialogTitle>
              <DialogDescription className="break-all text-on-surface-variant">
                将永久删除「{deleteTarget?.title}」，此操作不可撤销。
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDeleteTarget(null)}>
                取消
              </Button>
              <Button
                variant="destructive"
                onClick={() => {
                  if (deleteTarget) {
                    removeTask(deleteTarget.id)
                    if (deleteTarget.id === currentTaskId) {
                      setCurrentTask(null)
                      navigate('/new')
                    }
                    setDeleteTarget(null)
                  }
                }}
              >
                确定删除
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    )
  }

  return (
    <div className="flex h-app w-full overflow-hidden bg-surface">
      <aside
        style={collapsed ? undefined : { width: sidebarWidth }}
        className={cn(
          'flex shrink-0 flex-col border-r border-border-subtle bg-sidebar',
          collapsed ? 'w-[64px] transition-[width] duration-200 ease-out' : '',
        )}
      >
        {/* Header */}
        <div
          className={cn(
            'flex h-16 items-center border-b border-border-subtle/60',
            collapsed ? 'justify-center px-2' : 'justify-between px-4',
          )}
        >
          <button
            type="button"
            onClick={() => navigate('/')}
            className={cn(
              'flex min-w-0 items-center gap-2.5 rounded-md text-left transition-colors hover:text-primary',
              collapsed ? 'justify-center' : '',
            )}
            aria-label="返回首页"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-[#0e0d2a]">
              <img src={logo} alt="NoteMeld" className="h-full w-full object-contain" />
            </div>
            {!collapsed && (
              <div className="min-w-0">
                <div className="font-display text-[18px] font-bold leading-tight text-primary">
                  NoteMeld
                </div>
                <div className="truncate text-[11px] leading-tight text-sidebar-muted">
                  源知库 · 你的专属知识库
                </div>
              </div>
            )}
          </button>

          {!collapsed && (
            <TooltipProvider delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setCollapsed(true)}
                    className="rounded-md p-1.5 text-sidebar-muted transition-colors hover:bg-surface-container hover:text-on-surface"
                  >
                    <PanelLeftClose className="h-4 w-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">收起侧边栏</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>

        {collapsed && (
          <div className="flex justify-center pt-2">
            <TooltipProvider delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setCollapsed(false)}
                    className="rounded-md p-1.5 text-sidebar-muted transition-colors hover:bg-surface-container hover:text-on-surface"
                  >
                    <PanelLeftOpen className="h-4 w-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">展开侧边栏</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        )}

        {/* 一级导航 */}
        <nav className={cn('mt-4 space-y-0.5', collapsed ? 'px-2' : 'px-2.5')}>
          {/* 新建笔记 - 按钮形式，仅 /new 高亮 */}
          {(() => {
            const item = navItems[0]
            const isActive = onNewRoot
            const baseCls = cn(
              'group relative flex h-9 w-full items-center gap-2.5 rounded-md text-[14px] font-medium transition-colors',
              collapsed ? 'justify-center px-0' : 'px-3',
              isActive
                ? 'bg-sidebar-active-bg text-sidebar-active-fg sidebar-active-rail'
                : 'text-sidebar-fg hover:bg-surface-container',
            )
            if (collapsed) {
              return (
                <TooltipProvider delayDuration={200}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button onClick={handleNewNote} className={baseCls}>
                        <span className="flex h-9 w-9 items-center justify-center">
                          {item.icon}
                        </span>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="right">{item.label}</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )
            }
            return (
              <button onClick={handleNewNote} className={baseCls}>
                {item.icon}
                <span>{item.label}</span>
              </button>
            )
          })()}

          {navItems.slice(1).map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.exact}
              className={({ isActive }) =>
                cn(
                  'group relative flex h-9 items-center gap-2.5 rounded-md text-[14px] font-medium transition-colors',
                  collapsed ? 'justify-center px-0' : 'px-3',
                  isActive
                    ? 'bg-sidebar-active-bg text-sidebar-active-fg sidebar-active-rail'
                    : 'text-sidebar-fg hover:bg-surface-container',
                )
              }
            >
              {collapsed ? (
                <TooltipProvider delayDuration={200}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="flex h-9 w-9 items-center justify-center">
                        {item.icon}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="right">{item.label}</TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              ) : (
                <>
                  {item.icon}
                  <span>{item.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* 笔记列表 */}
        {!collapsed && (
          <div className="mt-6 flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="shrink-0 px-4 pb-2.5">
              <div className="text-[13px] font-semibold tracking-tight text-on-surface">
                笔记列表
              </div>
            </div>
            <ScrollArea className="min-h-0 flex-1 overflow-hidden px-2">
              {shouldDeferConversations ? (
                <div className="px-3 py-6 text-center text-[12px] text-sidebar-muted">
                  后端尚未就绪，笔记列表将在连接成功后自动加载
                </div>
              ) : hasLoadedConversations && tasks.length === 0 ? (
                <div className="px-3 py-6 text-center text-[12px] text-sidebar-muted">
                  还没有沉淀内容
                  <br />
                  <span className="text-[11px]">从 /new 开始整理第一条资料</span>
                </div>
              ) : (
                <ul className="min-w-0 max-w-full space-y-0.5 pb-3">
                  {tasks.map(task => {
                    const active = shouldHighlightTaskInSidebar(location.pathname, task.id, currentTaskId)
                    const title = getTaskDisplayTitle(task)
                    return (
                      <li key={task.id} className="group/item relative min-w-0 max-w-full overflow-hidden">
                        <button
                          onClick={() => handleSelectTask(task.id)}
                          title={title}
                          className={cn(
                            'relative flex h-8 min-w-0 w-full max-w-full items-center gap-2 overflow-hidden rounded-md pl-3 pr-8 text-left text-[13px] transition-all',
                            active
                              ? 'bg-sidebar-active-bg text-sidebar-active-fg sidebar-active-rail font-medium'
                              : 'text-sidebar-fg hover:bg-surface-container',
                          )}
                        >
                          <span
                            className={cn(
                              'h-1.5 w-1.5 shrink-0 rounded-full',
                              getConversationDotClass(task),
                            )}
                          />
                          <span className="block w-0 min-w-0 flex-1 truncate">
                            {title}
                          </span>
                        </button>
                        <button
                          onClick={e => {
                            e.stopPropagation()
                            setDeleteTarget({ id: task.id, title })
                          }}
                          title="删除对话"
                          className="absolute right-1.5 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-sidebar-muted opacity-0 transition-all hover:bg-destructive/10 hover:text-destructive group-hover/item:opacity-100"
                          aria-label="删除"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </ScrollArea>
          </div>
        )}

        {collapsed && <div className="flex-1" />}

        {/* 底部 GitHub */}
        <div
          className={cn(
            'shrink-0 border-t border-border-subtle/60 bg-white py-3',
            collapsed ? 'px-2' : 'px-2.5',
          )}
        >
          <a
            href={githubUrl}
            onClick={openGithub}
            rel="noopener noreferrer"
            className={cn(
              'flex h-8 items-center gap-2 rounded-md text-[13px] text-sidebar-fg transition-colors hover:bg-surface-container',
              collapsed ? 'justify-center px-0' : 'px-3',
            )}
          >
            {collapsed ? (
              <TooltipProvider delayDuration={200}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <GithubIcon className="h-4 w-4" />
                  </TooltipTrigger>
                  <TooltipContent side="right">GitHub</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            ) : (
              <>
                <GithubIcon className="h-4 w-4" />
                <span>GitHub</span>
              </>
            )}
          </a>
        </div>
      </aside>

      {/* 侧边栏拖拽手柄 */}
      {!collapsed && (
        <div
          onMouseDown={startSidebarDrag}
          className="group/resizer relative w-1 shrink-0 cursor-col-resize"
          aria-label="拖拽调整侧边栏宽度"
        >
          <div className="absolute inset-y-0 left-0 w-px bg-border-subtle" />
          <div className="absolute inset-y-0 left-0 w-1 transition-colors group-hover/resizer:bg-primary/40" />
        </div>
      )}

      {/* 主内容 */}
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">{children}</main>

      {/* 删除笔记确认弹窗 */}
      <Dialog
        open={!!deleteTarget}
        onOpenChange={(open: boolean) => !open && setDeleteTarget(null)}
      >
        <DialogContent className="max-w-[420px]">
          <DialogHeader>
            <DialogTitle>删除这条对话？</DialogTitle>
            <DialogDescription className="break-all text-on-surface-variant">
              将永久删除「{deleteTarget?.title}」，此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (deleteTarget) {
                  removeTask(deleteTarget.id)
                  // 若删除的是当前打开的笔记，回到 /new
                  if (deleteTarget.id === currentTaskId) {
                    setCurrentTask(null)
                    navigate('/new')
                  }
                  setDeleteTarget(null)
                }
              }}
            >
              确定删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default AppLayout
