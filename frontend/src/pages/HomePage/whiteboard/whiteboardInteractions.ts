import type { UploadFileResponse } from '@/services/upload'
import type { WhiteboardViewport } from './types'

export interface WhiteboardTimerScheduler {
  setTimeout: (callback: () => void, delayMs: number) => unknown
  clearTimeout: (handle: unknown) => void
}

const defaultScheduler: WhiteboardTimerScheduler = {
  setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
  clearTimeout: handle => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
}

export function createViewportCommitter(
  commit: (viewport: WhiteboardViewport) => void | Promise<unknown>,
  delayMs = 500,
  scheduler: WhiteboardTimerScheduler = defaultScheduler,
  onError: (error: unknown) => void = () => undefined,
) {
  let timer: unknown = null
  let latest: WhiteboardViewport | null = null

  const clear = () => {
    if (timer === null) return
    scheduler.clearTimeout(timer)
    timer = null
  }

  const commitLatest = () => {
    const pending = latest
    latest = null
    if (!pending) return
    try {
      void Promise.resolve(commit(pending)).catch(onError)
    } catch (error) {
      onError(error)
    }
  }

  return {
    schedule(viewport: WhiteboardViewport) {
      latest = { ...viewport }
      clear()
      timer = scheduler.setTimeout(() => {
        timer = null
        commitLatest()
      }, delayMs)
    },
    dispose() {
      clear()
      commitLatest()
    },
  }
}

export interface WhiteboardUploadMetadata {
  fileName: string
  contentType: string
  fileKind: UploadFileResponse['file_kind']
}

export async function uploadFileForWhiteboardCard(
  file: File,
  currentUploadId: string,
  uploader: (formData: FormData) => Promise<UploadFileResponse>,
  registrar: (response: UploadFileResponse) => Promise<unknown>,
): Promise<{ uploadId: string; metadata: WhiteboardUploadMetadata | null; error: string | null }> {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const response = await uploader(formData)
    if (!response.upload_id?.trim()) throw new Error('上传完成但没有返回 upload id')
    await registrar(response)
    return {
      uploadId: response.upload_id.trim(),
      metadata: {
        fileName: response.file_name,
        contentType: response.content_type,
        fileKind: response.file_kind,
      },
      error: null,
    }
  } catch (error) {
    const candidate = error as { msg?: string; detail?: string } | null
    return {
      uploadId: currentUploadId,
      metadata: null,
      error: error instanceof Error
        ? error.message
        : candidate?.detail || candidate?.msg || '文件上传失败，请重试',
    }
  }
}

export async function resolveContextForCurrentTask<T>({
  initiatingTaskId,
  getCurrentTaskId,
  request,
  accept,
}: {
  initiatingTaskId: string | null
  getCurrentTaskId: () => string | null
  request: () => Promise<T>
  accept: (reference: T) => void
}): Promise<{ status: 'added' } | { status: 'stale' } | { status: 'error'; error: string }> {
  try {
    const reference = await request()
    if (!initiatingTaskId || getCurrentTaskId() !== initiatingTaskId) return { status: 'stale' }
    accept(reference)
    return { status: 'added' }
  } catch (error) {
    return {
      status: 'error',
      error: error instanceof Error ? error.message : '添加白板内容到对话失败，请重试',
    }
  }
}
