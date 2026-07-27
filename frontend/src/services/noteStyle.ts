import request from '@/utils/request'

export type OutputFormat = 'html' | 'markdown'

export interface StyleConstraintNode {
  tone?: string
  sentence?: string
  visual?: string
  forbidden?: string[]
}

export type StyleConstraints = Record<string, StyleConstraintNode>
export type RuleConfig = Record<string, Record<string, string | number | boolean | string[]>>

export interface ExampleContent {
  html: string
  markdown: string
}

export interface NoteStyleItem {
  id: string
  name: string
  description: string
  skeleton_html: string
  style_constraints: StyleConstraints
  rule_config: RuleConfig
  example_content: ExampleContent
  output_formats: OutputFormat[]
  builtin: boolean
  created_at?: string | null
  updated_at?: string | null
  selector_warnings?: string[]
}

export interface NoteStylePayload {
  name: string
  description: string
  skeleton_html: string
  style_constraints: StyleConstraints
  rule_config: RuleConfig
  example_content: ExampleContent
  output_formats: OutputFormat[]
}

export interface TemplateImportAnalysisSummary {
  router?: {
    doc_type: string
    strategy: string
    complexity_level: string
    needs_specialized_path?: boolean
    expected_risk?: string
    recommended_renderer_profile?: string
    confidence?: number
    warnings?: string[]
  }
  replication_score?: {
    overall_score: number
    layout_score: number
    style_score: number
    structure_score: number
    content_block_score: number
    grade: string
    warnings?: string[]
  }
  recommended_followup_prompts?: Array<{
    label: string
    prompt: string
  }>
}

export interface StyleExtractionTask {
  task_id: string
  status: StyleExtractionTaskStatus
  stage: string
  messages: string[]
  chunks?: Array<Record<string, unknown>>
  progress?: number
  provider_id?: string
  model_name?: string
  file_name?: string
  request_type?: 'text' | 'file' | ''
  user_message?: {
    content?: string
    source_name?: string
    file_name?: string
    model_name?: string
    provider_id?: string
  }
  analysis_summary?: TemplateImportAnalysisSummary | null
  request_payload?: {
    analysis_summary?: TemplateImportAnalysisSummary
    [key: string]: unknown
  }
  result?: NoteStylePayload | null
  error?: string | null
  created_at: number
  updated_at: number
}

export type StyleExtractionTaskStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'retrying'
  | 'canceled'

export interface StyleExtractionTaskListResponse {
  items: StyleExtractionTask[]
  has_more: boolean
  next_offset?: number | null
}

export type StyleGenerationMode = 'create' | 'edit'

export const emptyNoteStylePayload = (): NoteStylePayload => ({
  name: '',
  description: '',
  skeleton_html:
    '<article class="custom-note-template"><section class="note-body" data-slot="body"></section></article>',
  style_constraints: {
    global: {
      tone: '',
      sentence: '',
      visual: '',
      forbidden: [],
    },
  },
  rule_config: {
    global: {},
  },
  example_content: {
    html: '',
    markdown: '',
  },
  output_formats: ['markdown'],
})

export const fetchNoteStyles = async (): Promise<NoteStyleItem[]> => {
  return (await request.get<NoteStyleItem[]>('/note_styles')) as unknown as NoteStyleItem[]
}

export const createNoteStyle = async (payload: NoteStylePayload): Promise<NoteStyleItem> => {
  return (await request.post<NoteStyleItem>('/note_styles', payload)) as unknown as NoteStyleItem
}

export const updateNoteStyle = async (id: string, payload: NoteStylePayload): Promise<NoteStyleItem> => {
  return (await request.put<NoteStyleItem>(`/note_styles/${id}`, payload)) as unknown as NoteStyleItem
}

export const deleteNoteStyle = async (id: string): Promise<void> => {
  await request.delete(`/note_styles/${id}`)
}

export const extractNoteStyleFromText = async (payload: {
  content: string
  source_name: string
  provider_id?: string
  model_name?: string
  user_instruction?: string
  current_template?: NoteStylePayload | null
  generation_mode?: StyleGenerationMode
}): Promise<StyleExtractionTask> => {
  return (await request.post<StyleExtractionTask>(
    '/note_styles/extract_text',
    payload,
  )) as unknown as StyleExtractionTask
}

export const extractNoteStyleFromFile = async (payload: {
  file_url: string
  file_name: string
  content_type?: string
  provider_id: string
  model_name: string
  user_instruction?: string
  current_template?: NoteStylePayload | null
  generation_mode?: StyleGenerationMode
}): Promise<StyleExtractionTask> => {
  return (await request.post<StyleExtractionTask>(
    '/note_styles/extract_file',
    payload,
  )) as unknown as StyleExtractionTask
}

export const fetchNoteStyleExtractionTask = async (taskId: string): Promise<StyleExtractionTask> => {
  return (await request.get<StyleExtractionTask>(
    `/note_styles/extraction_tasks/${taskId}`,
  )) as unknown as StyleExtractionTask
}

export const fetchLatestNoteStyleExtractionTask = async (): Promise<StyleExtractionTask | null> => {
  return (await request.get<StyleExtractionTask | null>(
    '/note_styles/extraction_tasks/latest',
  )) as unknown as StyleExtractionTask | null
}

export const fetchNoteStyleExtractionTasks = async (params?: {
  limit?: number
  offset?: number
  status?: StyleExtractionTaskStatus | 'all'
}): Promise<StyleExtractionTaskListResponse> => {
  const search = new URLSearchParams()
  search.set('limit', String(params?.limit ?? 20))
  search.set('offset', String(params?.offset ?? 0))
  if (params?.status && params.status !== 'all') {
    search.set('status', params.status)
  }
  return (await request.get<StyleExtractionTaskListResponse>(
    `/note_styles/extraction_tasks?${search.toString()}`,
  )) as unknown as StyleExtractionTaskListResponse
}

export const retryNoteStyleExtractionTask = async (taskId: string): Promise<StyleExtractionTask> => {
  return (await request.post<StyleExtractionTask>(
    `/note_styles/extraction_tasks/${taskId}/retry`,
  )) as unknown as StyleExtractionTask
}

export const cancelNoteStyleExtractionTask = async (taskId: string): Promise<StyleExtractionTask> => {
  return (await request.post<StyleExtractionTask>(
    `/note_styles/extraction_tasks/${taskId}/cancel`,
  )) as unknown as StyleExtractionTask
}

export const cleanupNoteStyleExtractionTasks = async (payload?: {
  keep_latest?: number
  max_age_days?: number
}): Promise<{ deleted: number }> => {
  return (await request.post<{ deleted: number }>(
    '/note_styles/extraction_tasks/cleanup',
    payload || {},
  )) as unknown as { deleted: number }
}
