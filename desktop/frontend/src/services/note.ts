import request from '@/utils/request'
import toast from 'react-hot-toast'
import type { CollectorTimings, ProgressTiming } from '@/types/progress'

export type { CollectorTimings, ProgressTiming } from '@/types/progress'

export type GenerateNotePayload = {
  video_url?: string
  platform: string
  quality: string
  model_name: string
  provider_id: string
  conversation_id?: string
  task_id?: string
  retry_attempt_id?: string
  format: Array<string>
  style: string
  output_type?: 'note_markdown' | 'export_outline'
  extras?: string
  screenshot?: boolean
  link?: boolean
  video_understanding?: boolean
  video_interval?: number
  vision_mode?: 'fixed_interval' | 'smart_sampling'
  max_sampling_points?: number
  enable_refine_engine?: boolean
  grid_size?: Array<number>
  force_web_fallback?: boolean
}

export type GenerateNoteResponse = {
  task_id: string
  message?: string
}

export type TaskStatusResponse = {
  status: string
  message?: string
  task_id?: string
  attempt_id?: string
  attempt?: number
  source_url?: string
  extras?: string
  wiki_status?: string
  stage_timings?: Record<string, ProgressTiming>
  collector_timings?: CollectorTimings
  stage_started_at?: string
  updated_at?: string
  result?: {
    markdown?: string
    transcript?: unknown
    audio_meta?: unknown
  }
}

export type GenerateNoteOptions = {
  suppressSuccessToast?: boolean
}

export const generateNote = async (
  data: GenerateNotePayload,
  options: GenerateNoteOptions = {},
): Promise<GenerateNoteResponse | null> => {
  try {
    const response = await request.post<unknown, GenerateNoteResponse>('/generate_note', data)

    if (!response) {
      toast.error('笔记生成任务提交失败')
      return null
    }
    if (!options.suppressSuccessToast) {
      toast.success(response.message || '笔记生成任务已提交！')
    }
    // 成功提示
    return response
  } catch (e: unknown) {
    console.error('❌ 请求出错', e)
    throw e // 抛出错误以便调用方处理
  }
}

export const delete_task = async ({
  video_id,
  platform,
}: {
  video_id: string
  platform: string
}) => {
  try {
    const data = {
      video_id,
      platform,
    }
    const res = await request.post('/delete_task', data)


      toast.success('任务已成功删除')
      return res
  } catch (e: unknown) {
    toast.error('请求异常，删除任务失败')
    console.error('❌ 删除任务失败:', e)
    throw e
  }
}

export const get_task_status = async (task_id: string): Promise<TaskStatusResponse> => {
  try {
    // 成功提示

    return await request.get<unknown, TaskStatusResponse>('/task_status/' + task_id)
  } catch (e: unknown) {
    console.error('❌ 请求出错', e)

    // 错误提示
    toast.error('笔记生成失败，请稍后重试')

    throw e // 抛出错误以便调用方处理
  }
}

export interface NoteLibraryItem {
  taskId: string
  title: string
  sourceUrl: string
  platform: string
  modelName: string
  style: string
  status: string
  wikiStatus: string
  createdAt: string
  updatedAt: string
}

export interface NoteLibraryPage {
  items: NoteLibraryItem[]
  pagination: { offset: number; limit: number; total: number }
}

export const listNoteLibrary = async (params: {
  q?: string
  offset?: number
  limit?: number
  wiki_status?: string
  status?: string
  signal?: AbortSignal
} = {}): Promise<NoteLibraryPage> => {
  const { signal, ...query } = params
  return request.get('/notes/library', { params: query, signal })
}

export interface NoteReadResult {
  title: string
  content: string
  source_url?: string
  metadata?: Record<string, unknown>
}

export const readNoteByTitle = async (title: string): Promise<NoteReadResult> =>
  request.get('/notes/read', { params: { title } })
