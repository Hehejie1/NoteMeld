import request from '@/utils/request'
import { seedWhiteboardFromLearningCanvas } from '@/services/whiteboard'
import type { WhiteboardSnapshot } from '@/pages/HomePage/whiteboard/types'

export type MasteryStatus = 'unknown' | 'exposed' | 'learning' | 'provisional' | 'mastered'
export type LearningSourceType = 'local_wiki' | 'local_note' | 'web' | 'academic' | 'github'

export interface LearningSource {
  id: string
  source_type: LearningSourceType
  provider: string
  title: string
  url?: string | null
  snippet: string
  published_at?: string | null
  authors: string[]
  repository?: string | null
  default_branch?: string | null
  stars?: number | null
  license?: string | null
  compile_status: string
}

export interface LearningNode {
  id: string
  label: string
  type: string
  summary: string
  priority: 'low' | 'medium' | 'high'
  mastery: MasteryStatus
  status: string
  prerequisites: string[]
  source_ids: string[]
  next_review_at?: string | null
  user_label?: string | null
  user_summary?: string | null
}

export interface LearningEdge {
  source: string
  target: string
  type: string
  weight: number
}

export interface LearningPathStep {
  step: number
  node_ids: string[]
  label: string
  difficulty: string
  minutes_estimate: number
  depends_on: number[]
}

export interface ReviewItem {
  node_id: string
  next_review_at: string
}

export interface LearningCanvas {
  version: number
  canvas_id: string
  conversation_id: string
  goal: string
  status: string
  diagnostic_status: string
  nodes: LearningNode[]
  edges: LearningEdge[]
  clusters: Array<Record<string, unknown>>
  path: LearningPathStep[]
  sources: LearningSource[]
  review_queue: ReviewItem[]
  current_node_id?: string | null
  external_errors: Array<{ provider?: string; code?: string; message?: string }>
  document_task_id?: string | null
  overview?: string
  clarification?: {
    question: string
    options: Array<{ id: string; label: string; description?: string }>
    allow_supplement?: boolean
  } | null
  suggested_actions?: Array<{
    id: string
    kind: 'focus' | 'research'
    label: string
    node_id?: string | null
    prompt?: string | null
  }>
}

export const listLearningCanvases = async (limit = 50): Promise<LearningCanvas[]> =>
  request.get('/learning-canvases', { params: { limit } }) as unknown as Promise<LearningCanvas[]>

export interface AggregatedReviewItem {
  conversation_id: string
  canvas_id: string
  goal: string
  node_id: string
  node_label: string
  mastery: MasteryStatus
  next_review_at: string
}

export const listDueLearningReviews = async (limit = 100): Promise<AggregatedReviewItem[]> =>
  request.get('/learning-reviews/due', { params: { limit } }) as unknown as Promise<AggregatedReviewItem[]>

export interface LearningUnit {
  node_id: string
  stage: string
  explanation: string
  recall_question: string
  application_question: string
}

export interface ResearchSearchConfig {
  web_provider: string
  searxng_endpoint: string
  timeout_seconds: number
  tavily_api_key_set: boolean
  github_token_set: boolean
}

export const createLearningCanvas = async (
  conversationId: string,
  payload: { goal: string; external_limit?: number; research_space_id?: string; provider_id?: string; model_name?: string; context_refs?: import('./chat').ConversationContextRef[] },
): Promise<LearningCanvas> =>
  request.post(
    `/conversations/${encodeURIComponent(conversationId)}/learning-canvases`,
    payload,
    { timeout: 0 },
  ) as unknown as Promise<LearningCanvas>

export const getLearningCanvas = async (
  conversationId: string,
  canvasId: string,
): Promise<LearningCanvas> =>
  request.get(
    `/conversations/${encodeURIComponent(conversationId)}/learning-canvases/${encodeURIComponent(canvasId)}`,
  ) as unknown as Promise<LearningCanvas>

export const seedLearningCanvasWhiteboard = async (
  conversationId: string,
  canvasId: string,
): Promise<WhiteboardSnapshot> => seedWhiteboardFromLearningCanvas(conversationId, canvasId)

export const updateLearningNode = async (
  conversationId: string,
  canvasId: string,
  payload: { node_id: string; user_label?: string | null; user_summary?: string | null },
): Promise<LearningCanvas> =>
  request.patch(
    `/conversations/${encodeURIComponent(conversationId)}/learning-canvases/${encodeURIComponent(canvasId)}`,
    payload,
  ) as unknown as Promise<LearningCanvas>

export const startLearningUnit = async (
  conversationId: string,
  canvasId: string,
  nodeId: string,
): Promise<{ unit: LearningUnit; canvas: LearningCanvas }> =>
  request.post(
    `/conversations/${encodeURIComponent(conversationId)}/learning-canvases/${encodeURIComponent(canvasId)}/units/${encodeURIComponent(nodeId)}/start`,
  ) as unknown as Promise<{ unit: LearningUnit; canvas: LearningCanvas }>

export const submitLearningEvidence = async (
  conversationId: string,
  canvasId: string,
  nodeId: string,
  payload: Record<string, unknown>,
): Promise<{ canvas: LearningCanvas }> =>
  request.post(
    `/conversations/${encodeURIComponent(conversationId)}/learning-canvases/${encodeURIComponent(canvasId)}/units/${encodeURIComponent(nodeId)}/evidence`,
    payload,
  ) as unknown as Promise<{ canvas: LearningCanvas }>

export const getResearchSearchConfig = async (): Promise<ResearchSearchConfig> =>
  request.get('/research-search/config') as unknown as Promise<ResearchSearchConfig>

export const updateResearchSearchConfig = async (
  payload: Record<string, unknown>,
): Promise<ResearchSearchConfig> =>
  request.put('/research-search/config', payload) as unknown as Promise<ResearchSearchConfig>
