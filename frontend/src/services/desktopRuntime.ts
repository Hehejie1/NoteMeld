import { invoke } from '@tauri-apps/api/core'
import { isDemoMode } from '@/demo/mode'
import { demoDesktopAction } from '@/demo/transport'

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
