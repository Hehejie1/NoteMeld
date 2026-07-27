import request from '@/utils/request'

export interface UsageFilters {
  start_at?: string
  end_at?: string
  task_id?: string
  provider_id?: string
  model_name?: string
  status?: string
}

export interface UsageOverview {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  call_count: number
  task_count: number
}

export interface UsageRecord {
  id: number
  task_id: string
  provider_id: string
  provider_name: string
  model_name: string
  phase: string
  platform?: string
  video_id?: string
  video_title?: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  status: string
  error_message?: string
  request_started_at?: string
  request_finished_at?: string
  duration_ms: number
  request_meta_json?: string
  created_at?: string
}

export interface TaskUsageSummary {
  task_id: string
  platform?: string
  video_id?: string
  video_title?: string
  call_count: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  latest_call_at?: string
}

export const getUsageOverview = async (params: UsageFilters) => {
  return (await request.get('/usage/overview', { params })) as UsageOverview
}

export const getUsageRecords = async (params: UsageFilters) => {
  return (await request.get('/usage/records', { params })) as UsageRecord[]
}

export const getTaskUsageSummary = async (params: UsageFilters) => {
  return (await request.get('/usage/task_summary', { params })) as TaskUsageSummary[]
}

export const getTaskUsageCalls = async (taskId: string) => {
  return (await request.get(`/usage/task_calls/${taskId}`)) as UsageRecord[]
}
