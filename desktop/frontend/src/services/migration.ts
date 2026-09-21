import request from '@/utils/request'
import { getRuntimeApiBaseUrl } from '@/utils/runtime'

export interface MigrationJobEvent {
  stage: string
  progress: number
  message: string
  created_at: string
}

export interface MigrationJobSummary {
  [key: string]: unknown
}

export interface MigrationJobPayload {
  schema_version?: string
  job_id: string
  status: string
  stage?: string
  progress?: number
  events?: MigrationJobEvent[]
  warnings?: string[]
  error?: string
  summary?: MigrationJobSummary
  completed_at?: string
  updated_at?: string
}

export interface StartMigrationExportPayload {
  package_name?: string
  job_id?: string
  app_version?: string
  target_path?: string
}

export interface StartMigrationImportPayload {
  package_path: string
  job_id?: string
  rebuild_indexes?: boolean
}

export interface RebuildMigrationIndexesPayload {
  task_ids?: string[]
}

export interface UploadMigrationPackageResult {
  package_path: string
}

export const startMigrationExport = async (payload: StartMigrationExportPayload) => {
  return (await request.post('/migration/export', payload)) as MigrationJobPayload
}

export const startMigrationImport = async (payload: StartMigrationImportPayload) => {
  return (await request.post('/migration/import', payload)) as MigrationJobPayload
}

export const uploadMigrationPackage = async (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return (await request.post('/migration/import/upload', formData, { timeout: 0 })) as UploadMigrationPackageResult
}

export const getMigrationJob = async (jobId: string) => {
  return (await request.get(`/migration/${jobId}/job`)) as MigrationJobPayload
}

export const getMigrationPackageDownloadUrl = (jobId: string) => {
  const baseUrl = getRuntimeApiBaseUrl() || import.meta.env.VITE_API_BASE_URL || '/api'
  return `${baseUrl.replace(/\/$/, '')}/migration/${encodeURIComponent(jobId)}/download`
}

export const rebuildMigrationIndexes = async (payload: RebuildMigrationIndexesPayload) => {
  return (await request.post('/migration/reindex', payload)) as MigrationJobPayload | Record<string, unknown>
}
