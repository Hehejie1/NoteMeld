import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { ChevronDown, LogOut, Moon, Sun, UserRoundPen } from 'lucide-react'
import CloudClient, { type CloudConfigSyncSnapshot, type CloudDashboard, type CloudOrganizationMemory, type CloudWorkspace } from '../../services/cloud'
import { useCloudAuth } from '../../hooks/useCloudAuth'
import { openIndexedDbTokenStore } from '../../services/tokenStore'
import { CloudLoginPanel } from '../../components/CloudLoginPanel'
import { CloudSessionList } from '../../components/CloudSessionList'
import { CloudSessionPanel } from '../../components/CloudSessionPanel'
import { CloudDeviceList } from '../../components/CloudDeviceList'
import { CloudModelList } from '../../components/CloudModelList'
import { CloudWorkspaceBrowser } from '../../components/CloudWorkspaceBrowser'
import { CloudUserList } from '../../components/CloudUserList'
import { makeDeviceId } from '../../services/deviceIdentity'
import { openDeviceKeyMaterial, type DeviceKeyMaterial } from '../../services/deviceKeyStore'
import { get_desktop_device_id } from '../../services/desktopDeviceIdentity'
import { shouldUseDesktopRuntime } from '../../utils/runtime'
import { toast } from 'react-hot-toast'
import { EmptyState, ErrorState, LoadingState } from '../../components/ui/feedback'
import logo from '../../assets/notemeld-cloud-logo.png'
import { CloudLocaleProvider, localizeCloudError, useCloudLocale } from './cloudLocale'

export default function CloudPage() {
  return <CloudLocaleProvider><CloudPageContent /></CloudLocaleProvider>
}

function CloudPageContent() {
  const { t } = useCloudLocale()
  const location = useLocation()
  const navigate = useNavigate()
  const cloudSegments = location.pathname.replace(/^\/cloud\/?/, '').split('/').filter(Boolean)
  const view = cloudSegments[0]
  const deepSessionId = view === 'sessions' ? cloudSegments[1] : undefined
  const loginMode = view === 'access-request' ? 'request' : 'login'
  const requestedReturnTarget = new URLSearchParams(location.search).get('returnTo')
  const returnTarget = safeCloudReturnTarget(requestedReturnTarget)
  const baseUrl = import.meta.env.VITE_CLOUD_BASE_URL || (import.meta.env.VITE_CLOUD_WEB ? window.location.origin : 'http://127.0.0.1:8583')
  const [controllerDeviceId] = useState(() => makeDeviceId('desktop-controller'))
  const [hostDeviceId, setHostDeviceId] = useState<string | null>(null)
  const [deviceKeys, setDeviceKeys] = useState<DeviceKeyMaterial | null>(null)
  const [deviceReady, setDeviceReady] = useState(false)
  const [deviceRegistrationError, setDeviceRegistrationError] = useState<string | null>(null)
  const [deviceRegistrationVersion, setDeviceRegistrationVersion] = useState(0)
  // Do not send X-Device-Id until registration succeeds. Sending it during the
  // first render races the registration request and makes session reads return
  // 403 for a perfectly valid login.
  const [client, setClient] = useState(() => new CloudClient(baseUrl))
  const [secureStorageReady, setSecureStorageReady] = useState(false)
  const [secureStorageError, setSecureStorageError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string>()
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>()
  const [showArchived, setShowArchived] = useState(false)
  const [listVersion, setListVersion] = useState(0)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  useEffect(() => { if (deepSessionId) setSelectedId(deepSessionId) }, [deepSessionId])
  useEffect(() => { let active = true; void openCloudTokenStoreWithTimeout().then(store => { if (active) { const currentToken = client.getToken(); const nextClient = new CloudClient(baseUrl, currentToken ?? undefined, undefined, store); if (currentToken) void nextClient.persistCurrentToken(); setClient(nextClient); setSecureStorageReady(true); setSecureStorageError(null) } }).catch(reason => { if (active) setSecureStorageError(localizeCloudError(reason instanceof Error ? reason.message : 'secure storage unavailable', t)) }); return () => { active = false } }, [baseUrl, t])
  useEffect(() => { let active = true; void openDeviceKeyMaterial().then(value => { if (active) setDeviceKeys(value) }).catch(() => { if (active) setDeviceKeys(null) }); return () => { active = false } }, [])
  useEffect(() => { if (!shouldUseDesktopRuntime()) return; let active = true; void get_desktop_device_id().then(value => { if (active && value) setHostDeviceId(value) }).catch(() => undefined); return () => { active = false } }, [])
  const auth = useCloudAuth(client)
  useEffect(() => {
    if (auth.loading || auth.authenticated || view === 'login' || view === 'access-request') return
    const currentTarget = `${location.pathname}${location.search}`
    navigate(`/cloud/login?returnTo=${encodeURIComponent(safeCloudReturnTarget(currentTarget))}`, { replace: true })
  }, [auth.authenticated, auth.loading, location.pathname, location.search, navigate, view])
  useEffect(() => {
    if (!auth.authenticated) { setDeviceReady(false); setDeviceRegistrationError(null); return }
    let active = true
    setDeviceReady(false)
    setDeviceRegistrationError(null)
    const announce = () => { void client.heartbeat(controllerDeviceId).catch(() => undefined); if (hostDeviceId) void client.heartbeat(hostDeviceId).catch(() => undefined) }
    // Registration is required even when browser key material is unavailable.
    // The API accepts an optional public key; skipping registration but still
    // binding X-Device-Id leaves every session request tied to an inactive
    // device after a cold browser start or storage recovery.
    const register = deviceKeys
      ? client.registerDevice(controllerDeviceId, shouldUseDesktopRuntime() ? 'desktop-controller' : 'web', shouldUseDesktopRuntime() ? 'NoteMeld Desktop Controller' : 'Web browser', deviceKeys.publicKey)
      : client.registerDevice(controllerDeviceId, shouldUseDesktopRuntime() ? 'desktop-controller' : 'web', shouldUseDesktopRuntime() ? 'NoteMeld Desktop Controller' : 'Web browser')
    void register.then(() => { if (!active) return; client.setDeviceId(controllerDeviceId); announce(); setDeviceReady(true) }).catch(reason => { if (!active) return; setDeviceRegistrationError(localizeCloudError(reason instanceof Error ? reason.message : 'device registration failed', t)) })
    const timer = window.setInterval(announce, 30_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [auth.authenticated, client, controllerDeviceId, deviceKeys, hostDeviceId, t, deviceRegistrationVersion])
  if (secureStorageError) return <ErrorState title={t('cloud.secure-storage-unavailable', '安全云端存储不可用')} description={secureStorageError} className="m-6 min-h-40 text-red-700" />
  if (!secureStorageReady) return <LoadingState title={t('cloud.secure-storage-preparing', '正在准备安全云端存储…')} className="m-6 min-h-40" aria-busy="true" />
  async function createSession() {
    setCreating(true); setCreateError(null)
    try { const session = await client.createSession('cloud_native', t('session.new-title', '新建会话')); setSelectedId(session.id); setSelectedWorkspaceId(session.workspace_id); setListVersion(value => value + 1) } catch (reason) { setCreateError(localizeCloudError(reason instanceof Error ? reason.message : 'session creation failed', t)) } finally { setCreating(false) }
  }
  if (auth.loading) return <LoadingState title={t('cloud.connecting', '正在连接 NoteMeld Cloud…')} className="m-6 min-h-40" aria-busy="true" />
  if (!auth.authenticated) return <main className="flex min-h-app items-center justify-center"><CloudLoginPanel client={client} initialMode={loginMode} onLoggedIn={result => { auth.acceptLogin(result); navigate(returnTarget, { replace: true }) }} /></main>
  if (deviceRegistrationError) return <ErrorState title={t('devices.registration-failed', '设备注册失败')} description={deviceRegistrationError} className="m-6 min-h-40 text-red-700" />
  if (!deviceReady) return <LoadingState title={t('devices.registering', '正在连接当前设备…')} className="m-6 min-h-40" aria-busy="true" />
  const activeView = view && ['workbench', 'sessions', 'people', 'devices', 'settings'].includes(view) ? view : 'workbench'
  if (activeView !== 'sessions') return <div className="cloud-product-shell min-h-app bg-[var(--surface)] text-[var(--on-surface)]"><CloudHeader client={client} activeView={activeView} onLogout={() => void auth.logout()} /><div className="cloud-product-main"><CloudFocusedView view={activeView} client={client} role={auth.role ?? 'user'} onOpenSessions={() => navigate('/cloud/sessions')} /></div></div>
  return <div className="cloud-product-shell min-h-app bg-[var(--surface)] text-[var(--on-surface)]"><CloudHeader client={client} activeView="sessions" onLogout={() => void auth.logout()} /><main aria-label="Cloud workspace" className="cloud-product-main relative h-[calc(100dvh-4.5rem)] md:grid md:grid-cols-[minmax(14rem,17rem)_minmax(0,1fr)]">
    <aside className="flex h-full min-h-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--sidebar-bg)]">
      <header className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
        <h1 className="text-sm font-semibold">{showArchived ? t('sessions.archived', '已归档') : t('sessions.sidebar-title', '会话')}</h1>
        <div className="flex items-center gap-1">
          <button type="button" title={t('sessions.archived', '已归档')} className="rounded px-2 py-1 text-xs text-[var(--on-surface-variant)] hover:bg-[var(--surface-container)]" onClick={() => { setShowArchived(value => !value); setSelectedId(undefined) }}>{showArchived ? t('sessions.current', '当前') : t('sessions.archived', '已归档')}</button>
          {!showArchived ? <button type="button" aria-label={t('sessions.new', '新建会话')} title={t('sessions.new', '新建会话')} disabled={creating} className="cloud-session-new-button" onClick={() => void createSession()}>＋</button> : null}
        </div>
      </header>
      <div className="min-h-0 flex-1">
        <CloudSessionList
          client={client}
          archived={showArchived}
          selectedId={selectedId}
          reloadKey={listVersion}
          onSelect={session => { setSelectedId(session.id); setSelectedWorkspaceId(session.workspace_id) }}
          onChanged={() => setListVersion(value => value + 1)}
        />
      </div>
      {createError ? <p role="alert" className="border-t border-[var(--border-subtle)] px-4 py-2 text-xs text-[var(--error)]">{createError}</p> : null}
    </aside>
    <section className="relative h-full min-h-0 min-w-0 bg-[var(--surface-container-lowest)]">
      <CloudSessionPanel
        client={client}
        sessionId={selectedId}
        onSessionCreated={session => { setSelectedId(session.id); setSelectedWorkspaceId(session.workspace_id); setListVersion(value => value + 1) }}
      />
    </section>
  </main></div>
}

function formatBytes(value = 0) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

const cloudNavigation = [['workbench', 'AI 工作台', 'nav.workbench'], ['sessions', '云端会话', 'nav.sessions'], ['people', '人员管理', 'nav.people'], ['devices', '设备管理', 'nav.devices'], ['settings', '设置', 'nav.settings']] as const
function CloudHeader({ client, activeView, onLogout }: { client: CloudClient; activeView: string; onLogout: () => void }) {
  const { t } = useCloudLocale();
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'));
  const [open, setOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [name, setName] = useState('');
  const [avatar, setAvatar] = useState('');
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const navigate = useNavigate();
  // 用户名与头像从后端 /v1/auth/me 拉取，不再使用本地硬编码默认值。
  useEffect(() => {
    let active = true;
    void client.me().then(identity => {
      if (!active) return;
      const fallback = identity.display_name || identity.username;
      setName(fallback);
      setAvatar(identity.avatar || fallback.slice(0, 1));
    }).catch(() => undefined);
    return () => { active = false };
  }, [client]);
  const toggleTheme = () => { const next = !dark; setDark(next); document.documentElement.classList.toggle('dark', next); localStorage.setItem('notemeld-theme', next ? 'dark' : 'light') };
  const saveProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setProfileError(null);
    const nextName = name.trim();
    const nextAvatar = avatar.trim().slice(0, 2);
    const nextPassword = password.trim();
    try {
      await client.updateProfile({ display_name: nextName, avatar: nextAvatar, ...(nextPassword ? { password: nextPassword } : {}) });
      if (nextPassword) {
        // 改密码后后端会吊销该用户全部 token，需要重新登录。
        await onLogout();
        navigate('/cloud/login', { replace: true });
        return;
      }
      setName(nextName);
      setAvatar(nextAvatar);
      setPassword('');
      setEditOpen(false);
      toast.success(t('profile.saved', '用户信息已保存'));
    } catch (reason) {
      setProfileError(localizeCloudError(reason instanceof Error ? reason.message : '保存失败', t));
    } finally {
      setSaving(false);
    }
  }; return <><header className="cloud-product-header"><button className="cloud-product-brand" onClick={() => navigate('/cloud/workbench')} aria-label={t('cloud.home-label', 'NoteMeld 云端首页')}><span><img src={logo} alt="" /></span><strong>NoteMeld</strong><small>{t('cloud', '云端')}</small></button><nav className="cloud-product-tabs" aria-label={t('cloud.navigation', '云端主导航')}>{cloudNavigation.map(([id, label, key]) => <NavLink key={id} to={`/cloud/${id}`} className={activeView === id ? 'active' : ''}>{t(key, label)}</NavLink>)}</nav><div className="cloud-product-actions"><button className="cloud-header-icon" onClick={toggleTheme} aria-label={t('cloud.theme-toggle', '切换主题')}>{dark ? <Sun /> : <Moon />}</button><div className="cloud-user-menu"><button className="cloud-user-trigger" onClick={() => setOpen(value => !value)} aria-expanded={open}><span>{avatar}</span><strong>{name}</strong><ChevronDown /></button>{open && <div className="cloud-user-popover"><button onClick={() => { setOpen(false); setEditOpen(true) }}><UserRoundPen /> {t('edit-profile', '修改用户信息')}</button><button onClick={onLogout}><LogOut /> {t('logout', '退出登录')}</button></div>}</div></div></header>{editOpen && <div className="cloud-modal-scrim" role="presentation"><form className="cloud-profile-modal" role="dialog" aria-modal="true" aria-labelledby="cloud-profile-title" onSubmit={saveProfile}><button type="button" className="cloud-modal-close" onClick={() => setEditOpen(false)} aria-label={t('cancel', '关闭')}><span aria-hidden="true">×</span></button><h2 id="cloud-profile-title">{t('profile.title', '修改用户信息')}</h2><label>{t('profile.username', '用户名')}<input value={name} onChange={event => setName(event.target.value)} required /></label><label>{t('profile.avatar', '头像文字')}<input value={avatar} maxLength={2} onChange={event => setAvatar(event.target.value)} required /></label><label>{t('profile.password', '新密码')}<input type="password" autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} placeholder={t('profile.password-placeholder', '留空表示不修改')} /></label>{profileError ? <p role="alert" className="cloud-page-error">{profileError}</p> : null}<div className="cloud-modal-actions"><button type="button" onClick={() => setEditOpen(false)}>{t('cancel', '取消')}</button><button type="submit" disabled={saving}>{saving ? t('saving', '保存中…') : t('save', '保存')}</button></div></form></div>}</> }
function CloudFocusedView({ view, client, role, onOpenSessions }: { view: string; client: CloudClient; role: string; onOpenSessions: () => void }) {
  const { t } = useCloudLocale()
  if (view === 'people') return <main className="cloud-focused-view">{role === 'admin' ? <CloudUserList client={client} /> : <EmptyCloudState title={t('users.admin-only', '仅管理员可管理人员')} description={t('users.admin-only-description', '普通用户可以使用云端会话，但不能修改成员权限。')} />}</main>
  if (view === 'devices') return <main className="cloud-focused-view"><CloudDeviceList client={client} /></main>
  if (view === 'settings') return <CloudSettingsView client={client} />
  return <CloudWorkbenchView client={client} onOpenSessions={onOpenSessions} />
}

function CloudWorkbenchView({ client, onOpenSessions: _onOpenSessions }: { client: CloudClient; onOpenSessions: () => void }) {
  const { t } = useCloudLocale()
  const [dashboard, setDashboard] = useState<CloudDashboard | null>(null)
  const [usage, setUsage] = useState<Array<{ date: string; conversations: number; total_tokens: number }>>([])
  const [capacity, setCapacity] = useState<{ bytes_used?: number; quota_bytes?: number; quota_percent?: number; warning?: boolean } | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    Promise.all([client.listSessions(), client.dashboard(), client.usage(7), client.workspaceCapacity('default')])
      .then(([, nextDashboard, nextUsage, nextCapacity]) => {
        if (active) {
          setError(null)
          setDashboard(nextDashboard)
          setUsage(nextUsage.days)
          setCapacity(nextCapacity as typeof capacity)
        }
      })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : t('workbench.load-failed', '云端状态读取失败，请刷新后重试。')) })
    return () => { active = false }
  }, [client, t])
  const maxTokens = Math.max(1, ...usage.map(item => item.total_tokens))
  const capacityPercent = Math.min(100, Math.max(0, capacity?.quota_percent ?? 0))
  return <main className="cloud-focused-view cloud-workbench-page">
    {error ? <p role="alert" className="cloud-page-error">{t('workbench.load-failed', '云端状态读取失败，请刷新后重试。')}</p> : null}
    <section className="cloud-workbench-overview"><div className="cloud-workbench-lead">
      <h2>{t('workbench.lead-title', '让云端任务自动向前走。')}</h2>
    </div><div className="cloud-workbench-metrics">
      <article><strong>{capacity ? formatBytes(capacity.bytes_used ?? 0) : '—'}</strong><span>{t('workbench.storage', '存储总量')}</span><small>{t('workbench.all-workspaces', '所有 Workspace 汇总')}</small></article>
      <article><strong>{dashboard?.daily_agent_conversations ?? 0}</strong><span>{t('workbench.today', '今日 Agent 对话')}</span><small>{t('workbench.cloud-session-stat', '按 Cloud 会话统计')}</small></article>
      <article><strong>{dashboard?.running_count ?? 0}</strong><span>{t('workbench.running', '运行中任务')}</span><small>{t('workbench.active-tasks', '活动任务')}</small></article>
    </div></section>
    <div className="cloud-workbench-lower"><section className="cloud-dashboard-section cloud-token-card"><h2>{t('workbench.tokens', '累计 Token')}</h2><strong>{dashboard?.total_tokens ?? 0}</strong><span>{t('workbench.current-period', '当前统计周期')}</span><small>{dashboard?.device_count ?? 0} {t('workbench.devices', '已连接设备')} · {dashboard?.daily_agent_conversations ?? 0} {t('workbench.today', '今日对话')}</small></section><section className="cloud-dashboard-section cloud-usage-chart"><div className="cloud-section-heading"><div><h2>{t('workbench.usage', '近 7 日用量')}</h2><span>{t('workbench.usage-label', '近七日 Token 趋势')}</span></div></div>{usage.length ? <div className="cloud-usage-bars" aria-label={t('workbench.usage-label', '近七日 Token 趋势')}>{usage.map(item => <div key={item.date} className="cloud-usage-bar-row"><span>{item.date}</span><div><i style={{ width: Math.max(2, (item.total_tokens / maxTokens) * 100) + '%' }} /></div><b>{item.total_tokens}</b></div>)}</div> : <p role="status">{t('workbench.usage-empty', '暂无用量记录。')}</p>}</section></div>
    <section className="cloud-dashboard-section cloud-workspace-usage"><div className="cloud-section-heading"><div><h2>{t('workbench.workspace-usage', 'Workspace 用量')}</h2><span>{t('workbench.default-workspace', '默认 Workspace')}</span></div>{capacity?.warning ? <span role="status" className="cloud-status-warning">{t('workbench.capacity-warning', 'Workspace 接近容量上限。')}</span> : null}</div>{capacity ? <><p>{capacity.bytes_used ?? 0} / {capacity.quota_bytes ?? 0} bytes</p><div className="cloud-usage-track"><div className={capacity.warning ? 'warning' : ''} style={{ width: capacityPercent + '%' }} /></div></> : <p role="status">{t('workbench.capacity-unavailable', 'Workspace 容量暂不可用。')}</p>}</section>
  </main>
}

function CloudSettingsView({ client }: { client: CloudClient }) {
  const { t } = useCloudLocale()
  const [section, setSection] = useState<'general' | 'workspace' | 'models' | 'security' | 'logs'>('general')
  const [audits, setAudits] = useState<unknown[] | null>(null)
  const [modelRevision, setModelRevision] = useState(0)
  const loadAudits = () => { void client.listAudits().then(setAudits).catch(() => setAudits([])) }
  return <main className="cloud-focused-view cloud-settings-view"><div className="cloud-settings-layout"><nav className="cloud-settings-nav" aria-label={t('settings.title', '设置分类')}>{[['general', t('settings.general', '通用')], ['workspace', t('settings.workspace', '空间管理')], ['models', t('settings.models', '模型配置')], ['security', t('settings.security', '安全管理')], ['logs', t('settings.logs', '日志排查')]].map(([id, label]) => <button key={id} className={section === id ? 'active' : ''} onClick={() => setSection(id as typeof section)}>{label}</button>)}</nav><section className="cloud-settings-content"><div className="cloud-settings-scroll">{section === 'general' && <CloudPreferencePanel client={client} />}{section === 'workspace' && <><h2>{t('settings.workspace', '空间管理')}</h2><CloudWorkspaceBrowser client={client} workspaceId="default" manageBackups /></>}{section === 'models' && <CloudModelList client={client} refreshKey={modelRevision} onCreated={() => setModelRevision(value => value + 1)} />}{section === 'security' && <><h2>{t('settings.security', '安全管理')}</h2><SettingRow title={t('settings.security-approval', '高风险操作审批')} value={t('settings.security-host', '由宿主确认')} /><SettingRow title={t('settings.security-devices', '登录设备')} value={t('settings.security-devices-value', '在设备管理中查看')} /><SettingRow title={t('settings.security-grants', '授权管理')} value={t('settings.security-grants-value', '按会话与 Workspace 授权')} /><OrganizationMemoryPanel client={client} /></>}{section === 'logs' && <><h2>{t('settings.logs', '日志排查')}</h2><p className="text-muted-foreground">{t('settings.audit-description', '运行日志、登录日志和权限变更记录由云端审计接口提供。')}</p>{audits === null ? <button className="cloud-settings-action" onClick={loadAudits}>{t('settings.audit-load', '加载审计记录')}</button> : audits.length ? <pre className="cloud-audit-preview">{JSON.stringify(audits.slice(0, 20), null, 2)}</pre> : <p role="status" className="text-muted-foreground">{t('settings.audit-empty', '暂无审计记录或当前账号无权限。')}</p>}</>}</div></section></div></main>
}

function CloudPreferencePanel({ client }: { client: CloudClient }) {
  const { t, setLocale } = useCloudLocale()
  const [snapshot, setSnapshot] = useState<CloudConfigSyncSnapshot | null>(null)
  const [theme, setTheme] = useState(() => (document.documentElement.classList.contains('dark') ? 'dark' : 'light'))
  const [language, setLanguage] = useState('zh-CN')
  const [workspace, setWorkspace] = useState('')
  const [workspaces, setWorkspaces] = useState<CloudWorkspace[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const languageDirtyRef = useRef(false)

  // 主题与顶部切换按钮全局一致：立即生效并持久化到 localStorage。
  const applyTheme = (next: 'light' | 'dark') => {
    setTheme(next)
    document.documentElement.classList.toggle('dark', next === 'dark')
    localStorage.setItem('notemeld-theme', next)
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [next, availableWorkspaces] = await Promise.all([client.configSyncSnapshot('default', 0), client.listWorkspaces()])
      setSnapshot(next)
      setWorkspaces(availableWorkspaces)
      const nextLanguage = String(next.items.find(item => item.kind === 'user_preference' && item.key === 'language')?.value ?? 'zh-CN')
      const storedLanguage = localStorage.getItem('notemeld-cloud-locale')
      const effectiveLanguage = storedLanguage === 'en-US' || storedLanguage === 'zh-CN' ? storedLanguage : nextLanguage
      // 正在读取配置时不要覆盖用户已经选择的语言。
      if (!languageDirtyRef.current) {
        setLanguage(effectiveLanguage)
        setLocale(effectiveLanguage === 'en-US' ? 'en-US' : 'zh-CN')
      }
      const configuredWorkspace = String(next.items.find(item => item.kind === 'user_preference' && item.key === 'default_workspace')?.value ?? '')
      setWorkspace(availableWorkspaces.some(item => item.id === configuredWorkspace) ? configuredWorkspace : (availableWorkspaces[0]?.id ?? ''))
      setMessage(null)
    } catch (reason) {
      setMessage(localizeCloudError(reason instanceof Error ? reason.message : 'cloud configuration read failed', t))
    } finally {
      setLoading(false)
    }
  }, [client, setLocale])

  useEffect(() => { void load() }, [load])

  const save = async () => {
    if (!snapshot || (!language && !workspace)) return
    setSaving(true)
    setMessage(null)
    try {
      const changes = [
        { kind: 'user_preference' as const, key: 'language', operation: 'set' as const, value: language },
        { kind: 'user_preference' as const, key: 'default_workspace', operation: 'set' as const, value: workspace },
      ]
      const next = await client.configSyncChanges('default', snapshot.revision, crypto.randomUUID(), changes)
      setSnapshot(next)
      languageDirtyRef.current = false
      setMessage(`${t('settings.saved-prefix', '已保存到 Cloud revision')} ${next.revision}`)
    } catch (reason) {
      setMessage(localizeCloudError(reason instanceof Error ? reason.message : 'cloud configuration save failed', t))
      languageDirtyRef.current = false
      await load()
    } finally {
      setSaving(false)
    }
  }

  return loading ? <p role="status" className="text-muted-foreground">{t('settings.reading', '正在读取配置…')}</p> : <><div className="grid gap-3"><label className="grid gap-1 text-sm">{t('settings.language', '语言')}<select aria-label={t('settings.language', 'Cloud 语言')} value={language} onChange={event => { languageDirtyRef.current = true; setLanguage(event.target.value); setLocale(event.target.value === 'en-US' ? 'en-US' : 'zh-CN') }} className="rounded-lg border border-border-subtle bg-surface-container-low px-3 py-2"><option value="zh-CN">简体中文</option><option value="en-US">English</option></select></label><label className="grid gap-1 text-sm">{t('settings.theme', '主题')}<select aria-label={t('settings.theme', 'Cloud 主题')} value={theme} onChange={event => applyTheme(event.target.value as 'light' | 'dark')} className="rounded-lg border border-border-subtle bg-surface-container-low px-3 py-2"><option value="light">{t('settings.light', '浅色')}</option><option value="dark">{t('settings.dark', '深色')}</option></select></label><label className="grid gap-1 text-sm">{t('settings.default-workspace', '默认 Workspace')}<select aria-label={t('settings.default-workspace', '默认 Workspace')} value={workspace} onChange={event => setWorkspace(event.target.value)} className="rounded-lg border border-border-subtle bg-surface-container-low px-3 py-2" disabled={!workspaces.length}><option value="">{t('settings.workspace-unset', '未设置')}</option>{workspaces.map(item => <option key={item.id} value={item.id}>{item.id}</option>)}</select></label></div><button type="button" className="cloud-settings-action mt-4" disabled={saving || !snapshot} onClick={() => void save()}>{saving ? t('settings.saving', '保存中…') : t('settings.save-sync', '保存并同步')}</button><p role="alert" className="mt-3 text-muted-foreground">{message ?? t('settings.current-revision', `当前 revision ${snapshot?.revision ?? 0} · ${snapshot?.items.length ?? 0} 项非敏感配置`)}</p></>
}

function OrganizationMemoryPanel({ client }: { client: CloudClient }) {
  const { t } = useCloudLocale()
  const [items, setItems] = useState<CloudOrganizationMemory[]>([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const load = useCallback(async () => { setLoading(true); try { setItems(await client.listOrganizationMemories()); setMessage('') } catch { setMessage(t('settings.memory-read-failed', '当前账号无组织记忆管理权限，或 Cloud 尚未提供组织数据。')) } finally { setLoading(false) } }, [client, t])
  useEffect(() => { void load() }, [load])
  const add = async () => { if (!draft.trim()) return; setLoading(true); try { await client.createOrganizationMemory(draft.trim()); setDraft(''); await load() } catch { setMessage(t('settings.memory-save-failed', '组织记忆保存失败。')); setLoading(false) } }
  const remove = async (id: string) => { setLoading(true); try { await client.deleteOrganizationMemory(id); await load() } catch { setMessage(t('settings.memory-delete-failed', '组织记忆删除失败。')); setLoading(false) } }
  return <div className="mt-6 border-t border-border-subtle pt-5"><h3 className="text-base font-medium">{t('settings.memory-title', '组织长期记忆')}</h3><p className="mt-1 text-sm text-muted-foreground">{t('settings.memory-description', '仅管理员可修改，供组织授权范围内的 Workspace 使用，不会混入个人偏好。')}</p><div className="mt-3 flex gap-2"><input aria-label={t('settings.memory-label', '组织记忆内容')} value={draft} onChange={event => setDraft(event.target.value)} placeholder={t('settings.memory-placeholder', '例如：团队统一使用中文并要求高风险操作审批')} className="min-w-0 flex-1 rounded-lg border border-border-subtle bg-surface-container-low px-3 py-2 text-sm" /><button type="button" className="cloud-settings-action" onClick={() => void add()} disabled={loading || !draft.trim()}>{t('settings.memory-add', '添加')}</button></div>{message && <p role="alert" className="mt-2 text-xs text-error">{message}</p>}<div className="mt-3 space-y-2">{items.map(item => <div key={item.id} className="flex items-start justify-between gap-3 rounded-lg bg-surface-container-low px-3 py-2 text-sm"><span>{item.content}<small className="mt-1 block text-xs text-muted-foreground">{t('settings.memory-source', '来源')}：{item.source}</small></span><button type="button" className="text-xs text-error" onClick={() => void remove(item.id)} disabled={loading}>{t('settings.memory-delete', '删除')}</button></div>)}{!loading && !items.length && !message && <p className="text-xs text-muted-foreground">{t('settings.memory-empty', '暂无组织记忆。')}</p>}</div></div>
}
function SettingRow({ title, value }: { title: string; value: string }) { return <div className="cloud-setting-row"><span>{title}</span><strong>{value}</strong></div> }
function EmptyCloudState({ title, description }: { title: string; description: string }) { return <EmptyState title={title} description={description} className="cloud-empty-state" /> }

function openCloudTokenStoreWithTimeout(timeoutMs = 5000) {
  let timeoutId: number | undefined
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = window.setTimeout(() => reject(new Error('secure browser storage initialization timed out')), timeoutMs)
  })
  return Promise.race([openIndexedDbTokenStore(), timeout]).finally(() => {
    if (timeoutId !== undefined) window.clearTimeout(timeoutId)
  })
}

function safeCloudReturnTarget(value: string | null) {
  if (!value || !value.startsWith('/cloud') || value.startsWith('//') || value.includes('\n') || value.includes('\r')) return '/cloud/workbench'
  return value
}
