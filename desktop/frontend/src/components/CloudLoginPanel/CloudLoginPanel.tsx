import { FormEvent, useEffect, useState } from 'react'
import { ArrowRight, Check, Cloud, CloudCog, Eye, EyeOff, FolderKanban, LockKeyhole, Mail, Moon, Shield, ShieldCheck, Sun } from 'lucide-react'
import CloudClient from '../../services/cloud'
import type { CloudLoginResult } from '../../hooks/useCloudAuth'
import logo from '../../assets/notemeld-cloud-logo.png'
import { useCloudLocale } from '../../pages/CloudPage/cloudLocale'

type LoginMode = 'password' | 'code' | 'reset'

export function CloudLoginPanel({ client, onLoggedIn, initialMode = 'login' }: { client: CloudClient; onLoggedIn?: (result: CloudLoginResult) => void; initialMode?: 'login' | 'request' }) {
  const { t } = useCloudLocale()
  const [mode, setMode] = useState<LoginMode>('password')
  const [requestMode, setRequestMode] = useState(initialMode === 'request')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [reason, setReason] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(() => localStorage.getItem('notemeld-cloud-remember') !== '0')
  const [busy, setBusy] = useState(false)
  const [codeBusy, setCodeBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [themeDark, setThemeDark] = useState(() => localStorage.getItem('notemeld-theme') === 'dark')

  useEffect(() => { setRequestMode(initialMode === 'request'); setError(null) }, [initialMode])

  function setTheme(next: boolean) {
    setThemeDark(next)
    localStorage.setItem('notemeld-theme', next ? 'dark' : 'light')
  }

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try {
      if (requestMode) {
        if (password !== code) throw new Error(t('login.password-mismatch', '两次输入的密码不一致'))
        await client.requestAccess(email.trim(), name.trim(), password, code, reason.trim())
        setError(t('login.request-submitted', '申请已提交，管理员审核通过后即可登录。'))
        return
      }
      if (mode === 'reset') {
        await client.resetPassword(email.trim(), code.trim(), password)
        setMode('password'); setCode(''); setPassword(''); setError(t('login.password-reset', '密码已重置，请使用新密码登录。'))
        return
      }
      const result = mode === 'code' ? await client.loginWithCode(email.trim(), code.trim()) : await client.login(password, email.trim())
      if (remember) localStorage.setItem('notemeld-cloud-remember', '1')
      else localStorage.removeItem('notemeld-cloud-remember')
      onLoggedIn?.(result)
    } catch (reason) { setError(reason instanceof Error ? reason.message : t('login.failed', '登录失败，请检查账号或网络连接。')) } finally { setBusy(false) }
  }

  async function sendCode() {
    if (!email.trim()) { setError(t('login.email-required', '请先输入邮箱。')); return }
    setCodeBusy(true); setError(null)
    try {
      const result = mode === 'reset' ? await client.sendPasswordResetCode(email.trim()) : await client.sendLoginCode(email.trim())
      setError(result.dev_code ? `${t('login.code-sent-dev', '验证码已发送（开发环境：')}${result.dev_code}${t('login.code-sent-close', '）')}` : t('login.code-sent', '验证码已发送，请检查邮箱。'))
    } catch (reason) { setError(reason instanceof Error ? reason.message : t('login.code-failed', '验证码发送失败。')) } finally { setCodeBusy(false) }
  }

  return <main className={`cloud-login-shell-react ${themeDark ? 'theme-dark' : ''}`}>
    <header className="cloud-login-brandbar">
      <a className="cloud-login-brand" href="/cloud/login" aria-label={t('login.brand-home', 'NoteMeld 云端首页')}><span className="cloud-login-brand-mark"><img src={logo} alt="" /></span><span><strong>NoteMeld</strong><small>{t('cloud', '云端')}</small></span></a>
      <button className="cloud-login-theme" type="button" onClick={() => setTheme(!themeDark)} aria-label={t('login.theme-toggle', '切换浅色或深色模式')}>{themeDark ? <Sun /> : <Moon />}</button>
    </header>
    <section className="cloud-login-layout-react">
      <div className="cloud-login-intro">
        <span className="cloud-login-kicker">NoteMeld Cloud</span>
        <h1>{t('login.hero-title', '让 Agent 在云端持续工作')}</h1>
        <p>{t('login.hero-description', '关闭浏览器后任务仍可继续运行。你可以回来查看会话状态、审批操作和 Agent 生成的产物。')}</p>
        <ul className="cloud-login-benefits">
          <li><CloudCog /><span><strong>{t('login.benefit-running', '持续运行')}</strong><small>{t('login.benefit-running-description', '云端 Agent 不依赖本地设备保持在线')}</small></span></li>
          <li><FolderKanban /><span><strong>{t('login.benefit-workspace', 'Workspace 上下文')}</strong><small>{t('login.benefit-workspace-description', '统一管理项目文件、会话上下文和产物')}</small></span></li>
          <li><ShieldCheck /><span><strong>{t('login.benefit-permissions', '权限自动识别')}</strong><small>{t('login.benefit-permissions-description', '登录后按账号权限显示用户或管理员菜单')}</small></span></li>
        </ul>
      </div>
      <section className="cloud-login-card" aria-labelledby="cloud-login-title">
        <div className="cloud-login-heading"><span className="cloud-login-mark"><Cloud /></span><div><h2 id="cloud-login-title">{requestMode ? t('login.request-title', '申请访问 NoteMeld 云端') : t('login.title', '登录 NoteMeld 云端')}</h2><p>{requestMode ? t('login.request-subtitle', '提交后由管理员审核') : t('login.subtitle', '使用你的组织账号继续')}</p></div></div>
        {!requestMode && mode !== 'reset' && <div className="cloud-login-tabs" role="tablist" aria-label={t('login.tabs', '登录方式')}><button className={mode === 'password' ? 'active' : ''} type="button" role="tab" aria-selected={mode === 'password'} onClick={() => { setMode('password'); setError(null) }}>{t('login.password-tab', '密码登录')}</button><button className={mode === 'code' ? 'active' : ''} type="button" role="tab" aria-selected={mode === 'code'} onClick={() => { setMode('code'); setError(null) }}>{t('login.code-tab', '验证码登录')}</button></div>}
        <form className="cloud-login-form" onSubmit={submit} noValidate>
          {requestMode && <label htmlFor="cloud-name">{t('login.name', '姓名或称呼')}</label>}
          {requestMode && <input id="cloud-name" autoComplete="name" required value={name} onChange={event => setName(event.target.value)} placeholder={t('login.name-placeholder', '请输入姓名或称呼')} />}
          <label htmlFor="cloud-email">{t('login.email', '邮箱或用户名')}</label>
          <div className="cloud-login-field"><Mail /><input id="cloud-email" autoComplete="username" required value={email} onChange={event => setEmail(event.target.value)} placeholder="name@example.com" /></div>
          {requestMode && <label htmlFor="cloud-password">{t('login.set-password', '设置登录密码')}</label>}
          {!requestMode && (mode === 'password' || mode === 'reset') && <label htmlFor="cloud-password">{mode === 'reset' ? t('profile.password', '新密码') : t('login.password', '密码')}</label>}
          {(requestMode || mode === 'password' || mode === 'reset') && <div className="cloud-login-field"><LockKeyhole /><input id="cloud-password" type={showPassword ? 'text' : 'password'} autoComplete={requestMode || mode === 'reset' ? 'new-password' : 'current-password'} required value={password} onChange={event => setPassword(event.target.value)} placeholder={requestMode || mode === 'reset' ? t('login.password-min', '至少 8 位') : t('login.password-placeholder', '输入密码')} /><button type="button" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? t('login.hide-password', '隐藏密码') : t('login.show-password', '显示密码')}>{showPassword ? <EyeOff /> : <Eye />}</button></div>}
          {requestMode && <><label htmlFor="cloud-confirm-password">{t('login.confirm-password', '确认密码')}</label><div className="cloud-login-field"><LockKeyhole /><input id="cloud-confirm-password" type="password" autoComplete="new-password" required value={code} onChange={event => setCode(event.target.value)} placeholder={t('login.confirm-password-placeholder', '再次输入密码')} /></div><label htmlFor="cloud-reason">{t('login.request-reason', '申请说明')} <small>{t('login.optional', '选填')}</small></label><textarea id="cloud-reason" value={reason} maxLength={100} onChange={event => setReason(event.target.value)} placeholder={t('login.reason-placeholder', '简要说明使用场景')} /></>}
          {!requestMode && (mode === 'code' || mode === 'reset') && <div className="cloud-login-field"><ShieldCheck /><input id="cloud-code" inputMode="numeric" autoComplete="one-time-code" required maxLength={6} value={code} onChange={event => setCode(event.target.value)} placeholder={t('login.code-placeholder', '输入 6 位验证码')} /><button type="button" onClick={() => void sendCode()} disabled={codeBusy}>{codeBusy ? t('login.sending-code', '发送中') : t('login.get-code', '获取验证码')}</button></div>}
          {!requestMode && mode === 'password' && <div className="cloud-login-options"><label><input type="checkbox" checked={remember} onChange={event => setRemember(event.target.checked)} /><span><Check />{t('login.remember', '记住登录状态')}</span></label><button type="button" onClick={() => { setMode('reset'); setCode(''); setError(null) }}>{t('login.forgot', '忘记密码？')}</button></div>}
          {error && <p className={`cloud-login-message ${error.includes('已发送') || error.includes('已提交') ? 'info' : ''}`} role="alert">{error}</p>}
          <button className="cloud-login-primary" type="submit" disabled={busy}>{busy ? t('login.processing', '处理中…') : requestMode ? t('login.request', '提交申请') : mode === 'reset' ? t('login.reset-password', '重置密码') : mode === 'code' ? t('login.code', '验证码登录') : t('login.submit', '登录')}<ArrowRight /></button>
        </form>
        {!requestMode && mode !== 'reset' && <><div className="cloud-login-divider"><span>{t('login.no-access', '还没有云端权限？')}</span></div><button className="cloud-login-secondary" type="button" onClick={() => { setRequestMode(true); setError(null) }}>{t('login.request', '申请访问')}</button></>}
        {!requestMode && mode === 'reset' && <button className="cloud-login-secondary" type="button" onClick={() => { setMode('password'); setError(null) }}>{t('login.back', '返回登录')}</button>}
        {requestMode && <button className="cloud-login-secondary" type="button" onClick={() => { setRequestMode(false); setError(null) }}>{t('login.back', '返回登录')}</button>}
        <p className="cloud-login-security"><Shield />{t('login.security', '登录会话受加密保护，过期后需要重新验证身份。')}</p>
      </section>
    </section>
    <footer className="cloud-login-footer-react"><span>© 2026 NoteMeld</span><span>{t('login.footer', '隐私 · 服务条款 · 安全')}</span></footer>
  </main>
}
