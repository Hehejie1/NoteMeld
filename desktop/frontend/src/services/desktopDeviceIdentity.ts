import { invoke } from '@tauri-apps/api/core'

/** Read the OS-backed desktop identity without importing desktop-only services. */
export async function get_desktop_device_id(): Promise<string> {
  return await invoke<string>('desktop_device_id')
}
