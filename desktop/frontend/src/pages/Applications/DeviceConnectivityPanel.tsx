import { useCallback, useEffect, useMemo, useState } from 'react'
import { CheckCircle2, RefreshCw, ShieldCheck, Wifi, WifiOff } from 'lucide-react'
import CloudClient, { type CloudDevice } from '@/services/cloud'
import { makeDeviceId } from '@/services/deviceIdentity'
import { openDeviceKeyMaterial } from '@/services/deviceKeyStore'
import { openIndexedDbTokenStore } from '@/services/tokenStore'
import { bootstrap_cloud_host, get_desktop_device_id } from '@/services/desktopRuntime'
import { isDemoMode } from '@/demo/mode'

const cloudBaseUrl = import.meta.env.VITE_CLOUD_BASE_URL || 'http://127.0.0.1:8583'

export default function DeviceConnectivityPanel() {
  const [deviceId, setDeviceId] = useState('读取中…')
  const [client, setClient] = useState<CloudClient | null>(null)
  const [device, setDevice] = useState<CloudDevice | null>(null)
  const [lanEndpoints, setLanEndpoints] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const id = isDemoMode() ? makeDeviceId('desktop') : await get_desktop_device_id()
        const tokenStore = await openIndexedDbTokenStore()
        if (active) { setDeviceId(id); setClient(new CloudClient(cloudBaseUrl, undefined, id, tokenStore)) }
      } catch (cause) { if (active) setError(cause instanceof Error ? cause.message : '本机设备身份读取失败') }
    })()
    return () => { active = false }
  }, [])

  const refresh = useCallback(async () => {
    if (!client || deviceId === '读取中…') return
    setLoading(true); setError('')
    try {
      const devices = await client.listDevices()
      const current = devices.find(item => item.id === deviceId) ?? null
      setDevice(current); setLanEndpoints(current?.connectivity?.lan_endpoints?.join(', ') ?? '')
      if (!current) setMessage('本机尚未注册到 Cloud，可使用下方按钮注册。')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '设备状态读取失败，请先登录 Cloud') }
    finally { setLoading(false) }
  }, [client, deviceId])

  useEffect(() => { void refresh() }, [refresh])

  const saveConnection = async () => {
    if (!client || !deviceId || deviceId === '读取中…') return
    setBusy(true); setError(''); setMessage('')
    try {
      const keys = await openDeviceKeyMaterial()
      const endpoints = lanEndpoints.split(',').map(item => item.trim()).filter(Boolean).slice(0, 8)
      if (device) await client.heartbeat(deviceId, endpoints)
      else await client.registerDevice(deviceId, 'desktop', 'NoteMeld Desktop', keys.publicKey, endpoints)
      const token = await client.getAccessToken()
      if (token) await bootstrap_cloud_host({ baseUrl: cloudBaseUrl, token, deviceId, displayName: 'NoteMeld Desktop', lanEndpoints: endpoints })
      setMessage('设备身份、LAN 候选和远程 Host 状态已同步。'); await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : '设备同步失败，请确认 Cloud 登录状态') }
    finally { setBusy(false) }
  }

  const transport = useMemo(() => device?.online ? (device.connectivity?.lan_endpoints?.length ? 'LAN 优先，Relay 回退' : 'Relay') : '未连接', [device])
  return <div className="space-y-5 p-5">
    <div className="grid gap-3 md:grid-cols-3">
      <div className="rounded-xl border border-border-subtle bg-surface p-4"><div className="text-xs text-on-surface-variant">本机设备身份</div><div className="mt-2 break-all font-mono text-xs text-on-surface">{deviceId}</div><div className="mt-2 text-xs text-on-surface-variant">私钥只保存在本机安全存储。</div></div>
      <div className="rounded-xl border border-border-subtle bg-surface p-4"><div className="text-xs text-on-surface-variant">连接策略</div><div className="mt-2 flex items-center gap-2 text-sm text-on-surface">{device?.online ? <Wifi className="h-4 w-4 text-emerald-600" /> : <WifiOff className="h-4 w-4 text-amber-600" />}{transport}</div><div className="mt-2 text-xs text-on-surface-variant">Relay 只转发加密帧，不读取消息正文。</div></div>
      <div className="rounded-xl border border-border-subtle bg-surface p-4"><div className="text-xs text-on-surface-variant">远程 Host</div><div className="mt-2 flex items-center gap-2 text-sm text-on-surface">{device?.online ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <ShieldCheck className="h-4 w-4 text-on-surface-variant" />}{device?.online ? '在线并可接收授权命令' : '未完成 Cloud 注册/心跳'}</div><div className="mt-2 text-xs text-on-surface-variant">{device?.public_key ? '已登记签名公钥' : '等待登记签名公钥'}</div></div>
    </div>
    <div className="rounded-xl border border-border-subtle bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-sm font-medium text-on-surface">LAN / Relay 连接</h2><p className="mt-1 text-xs text-on-surface-variant">LAN endpoint 只接受本地网络地址；不可达时自动回退到 Cloud Relay。</p></div><button type="button" onClick={() => void refresh()} disabled={loading || !client} className="inline-flex items-center gap-1 rounded-lg border border-border-subtle px-3 py-2 text-xs text-on-surface"><RefreshCw className={loading ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />刷新</button></div>
      <label className="mt-4 block text-xs text-on-surface-variant" htmlFor="runtime-lan-endpoints">LAN 地址（逗号分隔）</label><input id="runtime-lan-endpoints" value={lanEndpoints} onChange={event => setLanEndpoints(event.target.value)} placeholder="192.168.1.20:8784" className="mt-1 w-full rounded-lg border border-border-subtle bg-surface-container-low px-3 py-2 font-mono text-sm outline-none focus:border-primary" />
      <button type="button" onClick={() => void saveConnection()} disabled={busy || !client} className="mt-3 rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50">{busy ? '同步中…' : device ? '发送心跳并同步 Host' : '注册设备并启动 Host'}</button>
      {message && <p role="status" className="mt-3 text-xs text-emerald-700">{message}</p>}{error && <p role="alert" className="mt-3 text-xs text-error">{error}</p>}
    </div>
  </div>
}
