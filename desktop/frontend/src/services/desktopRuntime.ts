import { invoke } from '@tauri-apps/api/core'
import { isDemoMode } from '@/demo/mode'
import { demoDesktopAction } from '@/demo/transport'
import { getRuntimeApiBaseUrl, getRuntimeSessionToken, shouldUseDesktopRuntime } from '@/utils/runtime'

export interface CloudProbeResult { statusCode: number; ready: boolean }

export async function get_desktop_device_id(): Promise<string> {
  if (isDemoMode()) return 'desktop-demo-device'
  return await invoke<string>('desktop_device_id')
}

export async function get_autostart_enabled(): Promise<boolean> {
  if (isDemoMode()) return Boolean(await demoDesktopAction('get_autostart_enabled'))
  return await invoke<boolean>('get_autostart_enabled')
}

export async function set_autostart_enabled(enabled: boolean): Promise<void> {
  if (isDemoMode()) {
    await demoDesktopAction('set_autostart_enabled', enabled)
    return
  }
  await invoke('set_autostart_enabled', { enabled })
}

export async function probe_cloud(baseUrl: string): Promise<CloudProbeResult> {
  if (isDemoMode()) return { statusCode: 200, ready: true }
  return await invoke<CloudProbeResult>('probe_cloud', { baseUrl })
}

export interface CloudHostBootstrapResult { status: 'started' | 'already_running'; device_id: string; public_key?: string }

/** Connect the desktop process to Cloud using its OS-backed Host identity. */
export async function bootstrap_cloud_host(payload: {
  baseUrl: string
  token: string
  deviceId: string
  displayName?: string
  lanEndpoints?: string[]
}): Promise<CloudHostBootstrapResult | null> {
  if (!shouldUseDesktopRuntime() || isDemoMode()) return null
  const apiBaseUrl = getRuntimeApiBaseUrl()
  const sessionToken = getRuntimeSessionToken()
  if (!apiBaseUrl || !sessionToken) throw new Error('desktop runtime authentication is unavailable')
  const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/cloud-sync/host/bootstrap`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-NoteMeld-Session': sessionToken },
    body: JSON.stringify({ base_url: payload.baseUrl, token: payload.token, device_id: payload.deviceId, display_name: payload.displayName ?? 'NoteMeld Desktop', lan_endpoints: payload.lanEndpoints ?? [] }),
  })
  const data = await response.json() as CloudHostBootstrapResult & { detail?: string }
  if (!response.ok) throw new Error(data.detail || `desktop Cloud Host bootstrap failed (${response.status})`)
  return data
}
