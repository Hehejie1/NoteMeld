import { invoke } from '@tauri-apps/api/core'
import { isDemoMode } from '@/demo/mode'
import { demoDesktopAction } from '@/demo/transport'

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
