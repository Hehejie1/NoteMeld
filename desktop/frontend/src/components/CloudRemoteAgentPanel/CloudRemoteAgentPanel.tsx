import { useEffect, useMemo, useRef, useState } from 'react'
import CloudClient, { type CloudDevice, type CloudGrant } from '../../services/cloud'
import type { DeviceKeyMaterial } from '../../services/deviceKeyStore'
import { connectLanRemoteClient, type LanRemoteClient } from '../../services/lanRemoteClient'
import { useCloudLocale } from '../../pages/CloudPage/cloudLocale'

interface CloudRemoteAgentPanelProps {
  client: CloudClient
  cloudBaseUrl: string
  controllerDeviceId: string
  localHostDeviceId?: string
  keyMaterial: DeviceKeyMaterial | null
}

interface RemoteEvent {
  id: string
  type: string
  output: string
  approvalRequired: boolean
}

const STANDARD_REMOTE_SCOPES = ['message.send', 'event.receive', 'context.select', 'model.select', 'tool.invoke']

export function CloudRemoteAgentPanel({ client, cloudBaseUrl, controllerDeviceId, localHostDeviceId, keyMaterial }: CloudRemoteAgentPanelProps) {
  const { t } = useCloudLocale()
  const [devices, setDevices] = useState<CloudDevice[]>([])
  const [grants, setGrants] = useState<CloudGrant[]>([])
  const [selectedHostId, setSelectedHostId] = useState('')
  const [input, setInput] = useState('')
  const [events, setEvents] = useState<RemoteEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [transport, setTransport] = useState<'lan' | 'relay' | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const connectionRef = useRef<LanRemoteClient | null>(null)

  const hosts = useMemo(() => devices.filter(device => device.id !== controllerDeviceId && device.id !== localHostDeviceId), [controllerDeviceId, devices, localHostDeviceId])
  const selectedHost = hosts.find(device => device.id === selectedHostId)
  const activeGrant = grants.find(grant => grant.controller_device_id === controllerDeviceId && grant.host_device_id === selectedHostId && !grant.revoked_at && (!grant.expires_at || grant.expires_at * 1000 > Date.now()) && grant.scopes.includes('message.send') && grant.scopes.includes('event.receive'))

  useEffect(() => {
    let active = true
    Promise.all([client.listDevices(), client.listGrants()]).then(([nextDevices, nextGrants]) => {
      if (!active) return
      setDevices(nextDevices)
      setGrants(nextGrants)
      const eligible = nextDevices.find(device => device.id !== controllerDeviceId && device.id !== localHostDeviceId && device.online && device.public_key)
      setSelectedHostId(current => current && nextDevices.some(device => device.id === current) ? current : eligible?.id ?? '')
      setError(null)
    }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : t('remote.load-error', '无法加载远程设备'))
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false; connectionRef.current?.close(); connectionRef.current = null }
  }, [client, controllerDeviceId, localHostDeviceId, t])

  function appendRemoteEvent(raw: Record<string, unknown>) {
    const event = raw.event && typeof raw.event === 'object' ? raw.event as Record<string, unknown> : raw
    const payload = event.payload && typeof event.payload === 'object' ? event.payload as Record<string, unknown> : event
    const type = String(event.type ?? event.event_type ?? payload.type ?? 'remote.event')
    const output = [payload.output, payload.delta, payload.content].find(value => typeof value === 'string' && value.trim())
    const approvalRequired = type === 'approval.required'
    setEvents(current => [...current, {
      id: String(event.event_id ?? raw.frame_id ?? crypto.randomUUID()),
      type,
      output: typeof output === 'string' ? output : approvalRequired ? t('remote.approval-output', '危险操作正在等待远程 Host 本机审批；控制端不能代为批准。') : '',
      approvalRequired,
    }].slice(-200))
    if (type === 'turn.succeeded' || type === 'turn.failed' || type === 'turn.cancelled' || type === 'turn.interrupted' || ['completed', 'failed', 'cancelled', 'interrupted'].includes(String(payload.status ?? ''))) setBusy(false)
  }

  async function connect() {
    if (!selectedHost || !keyMaterial || busy) return
    setBusy(true); setError(null); setEvents([])
    try {
      if (!selectedHost.online) throw new Error(t('remote.offline-error', '远程 Host 当前离线'))
      if (!selectedHost.public_key) throw new Error(t('remote.key-error', '远程 Host 缺少设备公钥，请重新绑定'))
      if (!activeGrant) {
        await client.createGrant(controllerDeviceId, selectedHost.id, STANDARD_REMOTE_SCOPES)
        setGrants(await client.listGrants())
      }
      const challenge = await client.requestDeviceChallenge(controllerDeviceId)
      const signature = await keyMaterial.sign(`notemeld-device-proof-v1\0${controllerDeviceId}\0${challenge.challenge}`)
      await client.verifyDeviceChallenge(controllerDeviceId, challenge.challenge, signature)
      const deviceToken = await client.createDeviceToken(controllerDeviceId, ['device.read', 'device.write', 'grant.read', 'session.read'], 86_400, false, false)
      const session = await client.createSession('device_remote', `Remote · ${selectedHost.display_name}`)
      const connection = await connectLanRemoteClient({
        cloudBaseUrl,
        relayToken: deviceToken.token,
        sessionId: session.id,
        controllerDeviceId,
        hostDeviceId: selectedHost.id,
        hostConnectivity: selectedHost.connectivity ?? {},
        keyMaterial,
        hostPublicKey: selectedHost.public_key,
        authorityEpoch: 1,
        onEvent: appendRemoteEvent,
      })
      connectionRef.current?.close()
      connectionRef.current = connection
      setSessionId(session.id)
      setTransport(connection.transport)
    } catch (reason) {
      connectionRef.current?.close(); connectionRef.current = null
      setSessionId(null); setTransport(null)
      setError(reason instanceof Error ? reason.message : t('remote.connect-error', '远程连接失败'))
    } finally {
      setBusy(false)
    }
  }

  async function send() {
    const connection = connectionRef.current
    if (!connection || !input.trim() || busy) return
    setBusy(true); setError(null)
    try {
      const text = input.trim()
      await connection.send(text, crypto.randomUUID())
      setEvents(current => [...current, { id: crypto.randomUUID(), type: 'message.sent', output: text, approvalRequired: false }].slice(-200))
      setInput('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('remote.send-error', '远程消息发送失败'))
      setBusy(false)
    }
  }

  function disconnect() {
    connectionRef.current?.close(); connectionRef.current = null
    setSessionId(null); setTransport(null); setBusy(false)
  }

  return <section aria-labelledby="remote-agent-title" className="border-t border-[var(--border-subtle)] p-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 id="remote-agent-title" className="text-sm font-semibold text-[var(--on-surface)]">{t('remote.title', '远程 Agent')}</h2><p className="mt-1 text-xs text-[var(--on-surface-variant)]">{t('remote.description', '优先连接局域网；不可达时回退到端到端加密的 Cloud Relay。')}</p></div>
      {transport ? <span role="status" aria-label={`notemeld-remote-transport-${transport}`} className="rounded-full bg-[var(--surface-container)] px-2 py-1 text-xs font-medium text-[var(--primary)]">{transport === 'lan' ? t('remote.lan', 'LAN 直连') : 'Cloud Relay'}</span> : null}
    </div>
    {loading ? <div aria-busy="true" className="mt-4 h-20 animate-pulse rounded-lg bg-[var(--surface-container)]" /> : hosts.length ? <div className="mt-4 space-y-3">
      <label htmlFor="remote-host" className="block text-xs font-medium text-[var(--on-surface-variant)]">{t('remote.host', '远程机器')}</label>
      <select id="remote-host" aria-label={`notemeld-remote-host:${selectedHostId}`} value={selectedHostId} disabled={Boolean(sessionId) || busy} onChange={event => setSelectedHostId(event.target.value)} className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-container-lowest)] px-3 py-2 text-sm">
        <option value="">{t('remote.choose-host', '选择远程 Host')}</option>{hosts.map(device => <option key={device.id} value={device.id} aria-label={`notemeld-remote-host-option:${device.id}`} disabled={!device.online || !device.public_key}>{device.display_name} · {device.online ? t('remote.online', '在线') : t('remote.offline', '离线')}{device.connectivity?.lan_endpoints?.length ? ' · LAN' : ' · Relay'}</option>)}
      </select>
      {!sessionId ? <button type="button" aria-label="notemeld-remote-connect" disabled={busy || !selectedHost || !keyMaterial || !selectedHost.online || !selectedHost.public_key} onClick={() => void connect()} className="w-full rounded-lg bg-[var(--primary)] px-3 py-2 text-sm font-medium text-white disabled:opacity-40">{busy ? t('remote.connecting', '正在连接…') : activeGrant ? t('remote.connect', '连接远程 Agent') : t('remote.authorize-connect', '授权并连接')}</button> : <button type="button" aria-label="notemeld-remote-disconnect" onClick={disconnect} className="w-full rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm">{t('remote.disconnect', '断开远程连接')}</button>}
      {sessionId ? <form onSubmit={event => { event.preventDefault(); void send() }} className="space-y-2"><label htmlFor="remote-message" className="sr-only">{t('remote.input', '发送给远程 Agent')}</label><textarea id="remote-message" aria-label="notemeld-remote-input" value={input} onChange={event => setInput(event.target.value)} rows={2} maxLength={4000} placeholder={t('remote.placeholder', '发送给远程机器上的 Agent…')} className="w-full resize-y rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-container-lowest)] px-3 py-2 text-sm" /><button type="submit" aria-label={busy ? 'notemeld-remote-send-busy' : 'notemeld-remote-send-idle'} disabled={busy || !input.trim()} className="w-full rounded-lg bg-[var(--primary)] px-3 py-2 text-sm font-medium text-white disabled:opacity-40">{busy ? t('remote.waiting', '等待远程 Agent…') : t('remote.send', '发送')}</button></form> : null}
      {events.length ? <ol role="log" aria-live="polite" aria-label="notemeld-remote-event-log" className="max-h-64 space-y-2 overflow-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-container-lowest)] p-3">{events.map(event => <li key={event.id} role={event.approvalRequired ? 'alert' : undefined} aria-label={event.approvalRequired ? 'notemeld-remote-approval-required' : event.type.startsWith('turn.') ? `notemeld-remote-terminal-${event.type}` : undefined} className="text-xs"><span className="font-medium text-[var(--on-surface)]">{event.type}</span>{event.output ? <p aria-label={event.type === 'message.sent' ? `notemeld-remote-user:${event.output}` : `notemeld-remote-assistant:${event.output}`} className="mt-1 whitespace-pre-wrap text-[var(--on-surface-variant)]">{event.output}</p> : null}</li>)}</ol> : null}
    </div> : <p role="status" className="mt-4 text-sm text-[var(--on-surface-variant)]">{t('remote.empty', '没有可连接的远程 Host。请先在另一台 x64 客户端登录同一 Cloud 账号并启用 Host。')}</p>}
    {!keyMaterial ? <p role="alert" className="mt-3 text-sm text-[var(--error)]">{t('remote.key-unavailable', '安全设备密钥不可用，远程控制已禁用。')}</p> : null}
    {error ? <p role="alert" className="mt-3 text-sm text-[var(--error)]">{error}</p> : null}
    {sessionId ? <p className="mt-2 truncate font-mono text-[11px] text-[var(--on-surface-variant)]">Session {sessionId}</p> : null}
  </section>
}
