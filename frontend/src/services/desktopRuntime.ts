import { invoke } from '@tauri-apps/api/core'

export async function get_autostart_enabled(): Promise<boolean> {
  return await invoke<boolean>('get_autostart_enabled')
}

export async function set_autostart_enabled(enabled: boolean): Promise<void> {
  await invoke('set_autostart_enabled', { enabled })
}
