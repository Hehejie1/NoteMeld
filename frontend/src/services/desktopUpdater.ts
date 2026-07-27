import { isDesktopEmbedded } from '@/utils/runtime'

export type DesktopUpdateCheckResult =
  | {
      status: 'unavailable'
      message: string
    }
  | {
      status: 'latest'
      message: string
    }
  | {
      status: 'available'
      version: string
      date?: string
      body?: string
    }

export interface DesktopUpdateProgress {
  phase: 'started' | 'progress' | 'finished'
  downloaded?: number
  total?: number
}

type ProgressListener = (progress: DesktopUpdateProgress) => void

let pendingUpdate: Awaited<ReturnType<typeof import('@tauri-apps/plugin-updater').check>> | null = null

export async function checkDesktopUpdate(): Promise<DesktopUpdateCheckResult> {
  if (!isDesktopEmbedded()) {
    pendingUpdate = null
    return {
      status: 'unavailable',
      message: '当前不是桌面端运行环境，无法使用应用内更新。',
    }
  }

  const { check } = await import('@tauri-apps/plugin-updater')
  const update = await check()
  pendingUpdate = update

  if (!update?.available) {
    return {
      status: 'latest',
      message: '当前已经是最新版本。',
    }
  }

  return {
    status: 'available',
    version: update.version,
    date: update.date,
    body: update.body,
  }
}

export async function installPendingDesktopUpdate(onProgress?: ProgressListener): Promise<void> {
  if (!pendingUpdate?.available) {
    const result = await checkDesktopUpdate()
    if (result.status !== 'available' || !pendingUpdate?.available) {
      throw new Error(result.message || '没有可安装的新版本。')
    }
  }

  let downloaded = 0
  await pendingUpdate.downloadAndInstall((event: any) => {
    if (event.event === 'Started') {
      downloaded = 0
      onProgress?.({
        phase: 'started',
        total: event.data?.contentLength,
      })
      return
    }

    if (event.event === 'Progress') {
      downloaded += event.data?.chunkLength || 0
      onProgress?.({
        phase: 'progress',
        downloaded,
      })
      return
    }

    if (event.event === 'Finished') {
      onProgress?.({
        phase: 'finished',
      })
    }
  })

  const { relaunch } = await import('@tauri-apps/plugin-process')
  await relaunch()
}
