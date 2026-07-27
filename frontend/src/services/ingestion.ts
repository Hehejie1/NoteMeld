import request from '@/utils/request'

export type IngestionParserInfo = {
  name?: string
  backend?: string
  version?: string
  fallback_used?: boolean
}

export type IngestionParseReport = {
  task_id: string
  title: string
  resource_type: string
  parser: IngestionParserInfo
  page_count: number
  evidence_count: number
  chunk_count: number
  vector_indexed: boolean
  vector_error?: string
  quality: Record<string, unknown>
  artifacts: Record<string, string>
  warnings: string[]
}

export type EvidenceAnchor = {
  id: string
  job_id?: string
  source_type?: string
  source_asset_id?: string | null
  page_number?: number | null
  bbox?: number[] | null
  timestamp_start?: number | null
  timestamp_end?: number | null
  web_selector?: string | null
  text_quote: string
  screenshot_asset_id?: string | null
  confidence?: number
  granularity?: string
}

export type KnowledgeChunk = {
  id: string
  job_id?: string
  document_id?: string
  chunk_index?: number
  content: string
  summary?: string | null
  anchor_ids?: string[]
  source_weight?: number
  confidence?: number
  embedding_status?: string
  metadata?: Record<string, unknown>
}

export type IngestionSourceAsset = {
  task_id: string
  file_url: string
  file_name: string
  content_type: string
  resource_type: string
}

export const getIngestionReport = (taskId: string): Promise<IngestionParseReport> =>
  request.get<any, IngestionParseReport>(`/ingestion/${taskId}/report`)

export const getIngestionEvidence = (taskId: string): Promise<EvidenceAnchor[]> =>
  request.get<any, EvidenceAnchor[]>(`/ingestion/${taskId}/evidence`)

export const getIngestionChunks = (taskId: string): Promise<KnowledgeChunk[]> =>
  request.get<any, KnowledgeChunk[]>(`/ingestion/${taskId}/chunks`)

export const getIngestionSource = (taskId: string): Promise<IngestionSourceAsset> =>
  request.get<any, IngestionSourceAsset>(`/ingestion/${taskId}/source`)
