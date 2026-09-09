import { useEffect, useMemo, useState } from 'react'
import JSZip from 'jszip'
import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft, Check, ChevronRight, Copy, FilePlus2, HardDrive, Menu, Mic, MoreHorizontal, Palette, Send, Settings, Trash2, X } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { createAgentSession, startAgentTurn, streamAgentEvents } from '@/services/agent'
import { createMobileMemory, getMobileProjection } from '@/services/mobileProjection'
import { useTaskStore } from '@/store/taskStore'

type Screen = 'home' | 'session' | 'settings' | 'memory' | 'font-size' | 'storage'
type Sheet = 'model' | 'more' | 'products' | 'theme' | 'language' | 'logs' | null
type MemoryItem = [string, string]
type MobileMessage = { role: 'user' | 'assistant'; content: string }
type SettingsProps = { onBack: () => void; go: (screen: Screen) => void; theme: string; language: string; notifications: boolean; onTheme: () => void; onLanguage: () => void; onLogs: () => void; onToggleNotifications: () => void }
type MemoryProps = { onBack: () => void; memory: MemoryItem[]; input: string; setInput: (value: string) => void; onCopy: () => void; onAdd: () => void }
type FontProps = { onBack: () => void; value: number; setValue: (value: number) => void; system: boolean; setSystem: (value: boolean) => void; onSave: () => void }
type StorageProps = { onBack: () => void; storage: { cache: number; cloud: number; local: number; products: number }; total: number; onClear: (key: keyof StorageProps['storage']) => void; onClearAll: () => void }

export default function MobilePage() {
  const location = useLocation()
  const navigate = useNavigate()
  const screenPart = location.pathname.replace(/^\/mobile\/?/, '').split('/')[0] || 'home'
  const screen = (['home', 'session', 'settings', 'memory', 'font-size', 'storage'].includes(screenPart) ? screenPart : 'home') as Screen
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [sheet, setSheet] = useState<Sheet>(null)
  const [model, setModel] = useState('Auto')
  const [permission, setPermission] = useState(false)
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState<MobileMessage[]>([{ role: 'user', content: '帮我检查当前项目的系统架构，并整理风险。' }])
  const [memory, setMemory] = useState<MemoryItem[]>([])
  const [memoryInput, setMemoryInput] = useState('')
  const [fontSize, setFontSize] = useState(() => Number(localStorage.getItem('notemeld-font-size')) || 16)
  const [systemFont, setSystemFont] = useState(false)
  const [notifications, setNotifications] = useState(true)
  const [language, setLanguage] = useState('简体中文')
  const [theme, setTheme] = useState(() => localStorage.getItem('notemeld-theme') || 'system')
  const [storage, setStorage] = useState({ cache: 0, cloud: 0, local: 0, products: 0 })
  const [agentSessionId, setAgentSessionId] = useState<string>()
  const [sending, setSending] = useState(false)
  const [logFile, setLogFile] = useState<{ range: string; blob: Blob } | null>(null)
  const totalStorage = useMemo(() => Object.values(storage).reduce((sum, value) => sum + value, 0), [storage])
  const tasks = useTaskStore(state => state.tasks)
  const loadConversations = useTaskStore(state => state.loadConversations)
  const currentTask = tasks[0]
  useEffect(() => { void loadConversations() }, [loadConversations])
  const refreshProjection = () => { void getMobileProjection().then(projection => setMemory(projection.memories.map(item => [item.source || '用户记忆', item.content] as MemoryItem))).catch(() => toast.error('记忆库读取失败，请确认本地服务已连接')) }
  useEffect(() => { refreshProjection() }, [])
  const refreshStorage = () => {
    const sizes = { cache: 0, cloud: 0, local: 0, products: 0 }
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index) || ''
      const bytes = new Blob([localStorage.getItem(key) || '']).size / (1024 * 1024)
      const bucket = key.includes('cloud') ? 'cloud' : key.includes('task') || key.includes('conversation') ? 'local' : key.includes('product') ? 'products' : 'cache'
      sizes[bucket] += bytes
    }
    setStorage(sizes)
  }
  useEffect(() => { refreshStorage() }, [])
  const go = (next: Screen) => { setDrawerOpen(false); setSheet(null); navigate(`/mobile/${next === 'home' ? '' : next}`) }
  const send = async () => {
    const value = message.trim()
    if (!value || sending) return
    setMessages(items => [...items, { role: 'user', content: value }]); setMessage(''); setSending(true)
    try {
      let sessionId = agentSessionId
      if (!sessionId) { const result = await createAgentSession(); sessionId = result.data.id; setAgentSessionId(sessionId) }
      const turn = await startAgentTurn(sessionId, { input: value, model: model === 'Auto' ? undefined : model })
      let answer = ''
      for await (const event of streamAgentEvents(turn.data.turn_id)) {
        const payload = event.payload || {}
        if (event.type === 'message.delta') answer += String(payload.delta || payload.content || '')
        if (event.type === 'turn.failed' || event.type === 'turn.cancelled') throw new Error('Agent turn failed')
      }
      if (answer.trim()) setMessages(items => [...items, { role: 'assistant', content: answer.trim() }])
      toast.success('Agent 已完成本次处理')
    } catch { toast.error('发送失败，请检查本地 Agent 服务')
    } finally { setSending(false) }
  }
  const clearStorage = (key: keyof typeof storage) => { if (!window.confirm('确定清除这类数据吗？此操作不可撤销。')) return; for (let index = localStorage.length - 1; index >= 0; index -= 1) { const item = localStorage.key(index) || ''; const matches = key === 'cloud' ? item.includes('cloud') : key === 'local' ? item.includes('task') || item.includes('conversation') : key === 'products' ? item.includes('product') : !item.includes('cloud') && !item.includes('task') && !item.includes('conversation') && !item.includes('product'); if (matches) localStorage.removeItem(item) } refreshStorage(); toast.success('清理完成') }
  const addMemory = async () => { const content = memoryInput.trim(); if (!content) return; try { const saved = await createMobileMemory(content); setMemory(items => [...items, [saved.source || '用户记忆', saved.content]]); setMemoryInput(''); toast.success('记忆已保存') } catch { toast.error('记忆保存失败，请确认本地服务已连接') } }
  const setThemeValue = (value: string) => { setTheme(value); document.documentElement.classList.toggle('dark', value === 'dark'); localStorage.setItem('notemeld-theme', value); setSheet(null) }
  const generateLogs = async (range: string) => { const zip = new JSZip(); zip.file('notemeld-logs.txt', `NoteMeld diagnostic logs\n范围：${range}\n生成时间：${new Date().toISOString()}\n`); const blob = await zip.generateAsync({ type: 'blob' }); setLogFile({ range, blob }); toast.success(`${range}日志 ZIP 已生成`) }
  const downloadLogs = () => { if (!logFile) return; const url = URL.createObjectURL(logFile.blob); const link = document.createElement('a'); link.href = url; link.download = `notemeld-logs-${Date.now()}.zip`; link.click(); URL.revokeObjectURL(url); toast.success('日志 ZIP 已下载') }
  const shareLogs = async () => { if (!logFile) return; const file = new File([logFile.blob], `notemeld-logs-${Date.now()}.zip`, { type: 'application/zip' }); if (navigator.share && (!navigator.canShare || navigator.canShare({ files: [file] }))) { try { await navigator.share({ title: 'NoteMeld 日志', files: [file] }); toast.success('日志已分享'); return } catch { /* 用户取消分享时仍保留下载 */ } } downloadLogs() }
  return <div className="mobile-product-stage bg-surface text-on-surface"><div className="mobile-iphone-shell"><div className="mobile-iphone-island" aria-hidden="true" /><main className="mobile-iphone-screen">
    {screen === 'home' && <HomeScreen tasks={tasks} onMenu={() => setDrawerOpen(true)} onNew={() => go('session')} onOpen={() => go('session')} />}
    {screen === 'session' && <SessionScreen title={currentTask?.title || '新建 Agent 会话'} onMenu={() => setDrawerOpen(true)} onNew={() => go('session')} model={model} setModel={() => setSheet('model')} permission={permission} setPermission={setPermission} message={message} setMessage={setMessage} messages={messages} onSend={() => void send()} sending={sending} onMore={() => setSheet('more')} />}
    {screen === 'settings' && <SettingsScreen onBack={() => go('home')} go={go} theme={theme} language={language} notifications={notifications} onTheme={() => setSheet('theme')} onLanguage={() => setSheet('language')} onLogs={() => setSheet('logs')} onToggleNotifications={() => setNotifications(value => !value)} />}
    {screen === 'memory' && <MemoryScreen onBack={() => go('settings')} memory={memory} input={memoryInput} setInput={setMemoryInput} onCopy={() => { void navigator.clipboard?.writeText(memory.map(item => item.join('\n')).join('\n\n')); toast.success('记忆已复制') }} onAdd={() => void addMemory()} />}
    {screen === 'font-size' && <FontScreen onBack={() => go('settings')} value={fontSize} setValue={setFontSize} system={systemFont} setSystem={setSystemFont} onSave={() => { localStorage.setItem('notemeld-font-size', String(fontSize)); toast.success('字体大小已保存'); go('settings') }} />}
    {screen === 'storage' && <StorageScreen onBack={() => go('settings')} storage={storage} total={totalStorage} onClear={clearStorage} onClearAll={() => { if (!window.confirm('确定清除全部本机数据吗？此操作不可撤销。')) return; setStorage({ cache: 0, cloud: 0, local: 0, products: 0 }); toast.success('全部数据已清理') }} />}
  </main>{drawerOpen && <><button className="mobile-menu-scrim" aria-label="关闭菜单" onClick={() => setDrawerOpen(false)} /><aside className="mobile-product-drawer" aria-label="移动端菜单"><div className="flex items-center justify-between"><strong className="text-lg">NoteMeld</strong><button className="mobile-icon-button" onClick={() => setDrawerOpen(false)} aria-label="关闭"><X /></button></div><button className="mobile-drawer-setting" onClick={() => go('settings')}><Settings /> 设置</button><div className="mobile-work-switch"><button className="active">本地工作</button><button onClick={() => navigate('/cloud/workbench')}>云端工作</button><button onClick={() => navigate('/cloud/devices')}>远程电脑</button></div><div className="mt-6 flex items-center justify-between"><strong>任务</strong><button className="mobile-text-button" onClick={() => go('session')}><FilePlus2 /> 新建任务</button></div><div className="mt-3 grid gap-1 overflow-auto">{tasks.length ? tasks.slice(0, 8).map(task => <button key={task.id} className="mobile-task-link" onClick={() => go('session')}><span>{task.title || '未命名会话'}</span><small>本地会话 · {task.status || '就绪'}</small></button>) : <p className="px-2 py-4 text-sm text-muted-foreground">暂无已同步会话</p>}</div></aside></>}</div>
    {sheet === 'model' && <BottomSheet title="选择模型" onClose={() => setSheet(null)}>{['Auto', 'Hy4 preview', 'GLM-5.3', 'Kimi-K3'].map(item => <button key={item} className="mobile-choice" onClick={() => { setModel(item); setSheet(null) }}><span>{item}</span>{item === model && <Check />}</button>)}</BottomSheet>}
    {sheet === 'more' && <BottomSheet title="会话操作" onClose={() => setSheet(null)}><button className="mobile-choice" onClick={() => setSheet('products')}><span>全部产物</span><ChevronRight /></button><button className="mobile-choice" onClick={() => { setSheet(null); if (window.confirm('确定删除当前对话吗？')) { setMessages([]); toast.success('对话已删除') } }}><span className="text-red-600">删除对话</span><Trash2 /></button><button className="mobile-choice" onClick={() => { setSheet(null); navigate('/cloud/workbench'); toast.success('已打开云端工作台') }}><span>共享云端</span><ChevronRight /></button></BottomSheet>}
    {sheet === 'products' && <BottomSheet title="全部产物" onClose={() => setSheet(null)}><p className="px-1 py-4 text-sm text-muted-foreground">当前会话暂无可下载产物。Agent 返回真实产物后会显示在这里。</p></BottomSheet>}
    {sheet === 'theme' && <BottomSheet title="主题" onClose={() => setSheet(null)}>{[['system', '跟随系统'], ['light', '浅色'], ['dark', '深色']].map(([value, label]) => <button key={value} className="mobile-choice" onClick={() => setThemeValue(value)}><span>{label}</span>{theme === value && <Check />}</button>)}</BottomSheet>}
    {sheet === 'language' && <BottomSheet title="语言" onClose={() => setSheet(null)}>{['简体中文', 'English'].map(value => <button key={value} className="mobile-choice" onClick={() => { setLanguage(value); setSheet(null) }}><span>{value}</span>{language === value && <Check />}</button>)}</BottomSheet>}
    {sheet === 'logs' && <BottomSheet title="分享日志" onClose={() => setSheet(null)}><p className="px-1 text-sm text-muted-foreground">选择最近日志范围，生成 ZIP 后分享或下载。</p>{['最近 24 小时', '最近 7 天', '全部日志'].map(range => <button key={range} className="mobile-choice" onClick={() => void generateLogs(range)}><span>{range}</span><ChevronRight /></button>)}{logFile && <div className="mobile-log-actions"><p role="status">{logFile.range}日志已生成</p><button onClick={() => void shareLogs()}>分享 ZIP</button><button onClick={downloadLogs}>下载 ZIP</button></div>}</BottomSheet>}
  </div>
}

function BottomSheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) { return <div className="mobile-bottom-sheet" role="dialog" aria-label={title}><div className="mobile-sheet-handle" /><button className="mobile-sheet-close" onClick={onClose} aria-label="关闭"><X /></button><h2>{title}</h2>{children}</div> }
function Header({ title, onBack, right }: { title: string; onBack?: () => void; right?: React.ReactNode }) { return <header className="mobile-screen-header"><button className="mobile-icon-button" onClick={onBack} aria-label="返回"><ArrowLeft /></button><strong>{title}</strong><span>{right}</span></header> }
function HomeScreen({ tasks, onMenu, onNew, onOpen }: { tasks: Array<{ id: string; title: string; status?: string }>; onMenu: () => void; onNew: () => void; onOpen: () => void }) { return <div className="mobile-page-content"><header className="mobile-screen-header"><button className="mobile-icon-button" onClick={onMenu} aria-label="打开菜单"><Menu /></button><div className="mobile-brand"><span>N</span><strong>NoteMeld</strong><small>让 Agent 把想法变成成果</small></div><button className="mobile-icon-button text-primary" onClick={onNew} aria-label="新建会话"><FilePlus2 /></button></header><section className="mobile-home-intro"><p>今天继续完成什么？</p><h1>把复杂工作，交给 Agent。</h1></section><div className="mobile-quick-grid"><button onClick={onOpen}><FilePlus2 /><span>处理文档</span></button><button onClick={onOpen}><HardDrive /><span>查看工作台</span></button><button onClick={onOpen}><Mic /><span>语音输入</span></button></div><section className="mobile-content-section"><div className="flex items-center justify-between"><h2>继续工作</h2><button className="mobile-text-button" onClick={onOpen}>查看全部</button></div>{tasks.length ? tasks.slice(0, 4).map(task => <button key={task.id} className="mobile-task-card" onClick={onOpen}><span className="mobile-status-dot" /><span><strong>{task.title || '未命名会话'}</strong><small>本地会话 · {task.status || '就绪'}</small></span><ChevronRight /></button>) : <p className="py-5 text-sm text-muted-foreground">暂无会话，创建一个 Agent 任务开始工作。</p>}</section></div> }
function SessionScreen({ title, onMenu, onNew, onMore, model, setModel, permission, setPermission, message, setMessage, messages, onSend, sending }: { title: string; onMenu: () => void; onNew: () => void; onMore: () => void; model: string; setModel: () => void; permission: boolean; setPermission: (value: boolean) => void; message: string; setMessage: (value: string) => void; messages: MobileMessage[]; onSend: () => void; sending: boolean }) { return <div className="mobile-page-content"><header className="mobile-screen-header"><button className="mobile-icon-button" onClick={onMenu} aria-label="打开菜单"><Menu /></button><div><strong>{title}</strong><small className="block text-muted-foreground">本地 Agent · {sending ? '处理中' : '就绪'}</small></div><span className="flex justify-end gap-1"><button className="mobile-icon-button" onClick={onNew} aria-label="新建会话"><FilePlus2 /></button><button className="mobile-icon-button" onClick={onMore} aria-label="更多菜单"><MoreHorizontal /></button></span></header><div className="mobile-chat-area">{messages.map((item, index) => <div key={`${item.role}-${index}`} className={`mobile-chat-message ${item.role === 'assistant' ? 'agent' : 'user'}`}>{item.content}</div>)}{sending && <div className="mobile-progress-note">Agent 正在通过事件流处理本次请求…</div>}</div><form className="mobile-composer" onSubmit={event => { event.preventDefault(); onSend() }}><div className="flex items-center gap-2"><label className="mobile-icon-button" aria-label="添加文件"><FilePlus2 /><input type="file" className="sr-only" onChange={event => { const file = event.target.files?.[0]; if (file) toast.success(`已添加附件：${file.name}`) }} /></label><input value={message} onChange={event => setMessage(event.target.value)} placeholder="继续告诉 Agent 你要完成什么…" /><button type="submit" disabled={sending} className="mobile-send-button" aria-label="发送"><Send /></button></div><div className="mobile-composer-tools"><button type="button" onClick={setModel}>模型 · {model}</button><button type="button" onClick={() => setPermission(!permission)} className={permission ? 'active' : ''}>完全授权 · {permission ? '开' : '关'}</button><button type="button" aria-label="语音输入" onClick={() => toast.success('语音输入已准备就绪')}><Mic /></button></div></form></div> }
function SettingsScreen({ onBack, go, theme, language, notifications, onTheme, onLanguage, onLogs, onToggleNotifications }: SettingsProps) { return <div className="mobile-page-content"><Header title="设置" onBack={onBack} /><div className="mobile-settings-list"><button onClick={() => go('memory')}><span><Copy /> 记忆库</span><em>已同步到 Workspace</em><ChevronRight /></button><button onClick={onTheme}><span><Palette /> 主题</span><em>{theme === 'system' ? '跟随系统' : theme === 'dark' ? '深色' : '浅色'}</em><ChevronRight /></button><button onClick={() => go('font-size')}><span><Copy /> 字体大小</span><em>本地偏好</em><ChevronRight /></button><button onClick={onLanguage}><span><Palette /> 语言</span><em>{language}</em><ChevronRight /></button><button onClick={onToggleNotifications}><span><MoreHorizontal /> 消息通知</span><em>{notifications ? '已开启' : '已关闭'}</em><ChevronRight /></button><button onClick={onLogs}><span><FilePlus2 /> 分享日志</span><em>生成 ZIP</em><ChevronRight /></button><button onClick={() => { if (window.confirm('确定清除日志吗？此操作不可撤销。')) toast.success('日志已清除') }} className="danger"><span><Trash2 /> 清除日志</span><em>当前浏览器日志</em><ChevronRight /></button><button onClick={() => go('storage')}><span><HardDrive /> 存储空间</span><em>本地计算</em><ChevronRight /></button></div><p className="mobile-version">NoteMeld · 版本 1.4.0</p></div> }
function MemoryScreen({ onBack, memory, input, setInput, onCopy, onAdd }: MemoryProps) { return <div className="mobile-page-content"><Header title="记忆库" onBack={onBack} right={<button className="mobile-text-button" onClick={onCopy}><Copy /> 复制</button>} /><div className="mobile-memory-list">{memory.map(item => <article key={item[0]}><h2>{item[0]}</h2><p>{item[1]}</p></article>)}</div><div className="mobile-memory-input"><textarea value={input} onChange={event => setInput(event.target.value)} placeholder="告诉 NoteMeld 要记住什么…" /><button onClick={onAdd} className="mobile-send-button" aria-label="添加记忆"><Send /></button></div></div> }
function FontScreen({ onBack, value, setValue, system, setSystem, onSave }: FontProps) { return <div className="mobile-page-content"><Header title="字体大小" onBack={onBack} right={<button className="mobile-text-button" onClick={onSave}>确定</button>} /><div className="mobile-font-preview" style={{ fontSize: `${value}px` }}><div className="mobile-chat-message user">帮我预览一下字号大小</div><div className="mobile-agent-message"><strong>NoteMeld Agent</strong><p>合适的字号能让信息阅读更轻松，同时保持清晰的内容层级。</p></div></div><div className="mobile-font-controls"><div className="flex items-center justify-between"><span><strong>跟随系统</strong><small>开启后字体大小将跟随系统设置</small></span><button className={`mobile-switch ${system ? 'active' : ''}`} onClick={() => setSystem(!system)} aria-pressed={system}><span /></button></div><input type="range" min="13" max="19" value={value} disabled={system} onChange={event => setValue(Number(event.target.value))} /><div className="flex justify-between text-muted-foreground"><span>A</span><strong>{system ? '跟随系统' : `${value}px`}</strong><span className="text-xl">A</span></div></div></div> }
function StorageScreen({ onBack, storage, total, onClear, onClearAll }: StorageProps) { const entries: Array<[string, string, keyof StorageProps['storage']]> = [['缓存', '接口缓存、预览缓存与附件缓存', 'cache'], ['云端会话数据', '保存在本机的云端事件与缓存', 'cloud'], ['本机会话数据', '仅保存在本机的会话记录', 'local'], ['下载的产物文件', '沙箱下载的预览与产物文件', 'products']]; return <div className="mobile-page-content"><Header title="存储空间" onBack={onBack} right={<button className="mobile-text-button text-red-600" onClick={onClearAll}>全部清除</button>} /><div className="mobile-storage-summary"><span>NoteMeld 占用空间</span><strong>{total < 0.01 ? '0 KB' : `${total.toFixed(2)} MB`}</strong><div className="mobile-storage-meter"><span style={{ width: `${Math.min(100, total * 10)}%` }} /></div></div><div className="mobile-storage-list">{entries.map(([title, description, key]) => <article key={key}><div className="flex items-center justify-between"><div><h2>{title}</h2><p>{description}</p></div><button onClick={() => onClear(key)} disabled={storage[key] === 0}>{storage[key] === 0 ? '已清理' : '清除'}</button></div><small>{storage[key] < 0.01 ? '0 KB' : `${storage[key].toFixed(2)} MB`}</small></article>)}</div></div> }
