import request from '@/utils/request'

export interface WikiGraphNode {
  id: string
  label: string
  type: string
  size?: number
  weight?: number
  community_id?: number
  community_color?: string
  community_label?: string
  community_cohesion?: number
  community_is_weak?: boolean
}

export interface WikiGraphEdge {
  source: string
  target: string
  type: string
  weight?: number
}

export interface WikiGraphCluster {
  id: string
  label: string
  node_ids: string[]
  type?: string
  color?: string
  cohesion?: number
  is_weak?: boolean
}

export interface WikiGraph {
  nodes: WikiGraphNode[]
  edges: WikiGraphEdge[]
  clusters: WikiGraphCluster[]
}

export interface WikiPageSummary {
  id: string
  title: string
  source_type: string
  summary: string
  topics: string[]
}

export interface WikiPageDetail {
  id: string
  markdown: string
  contribution: {
    title?: string
    summary?: string
    topics?: string[]
    source_type?: string
    [key: string]: unknown
  }
}

export type WikiFilePageType = 'source' | 'entity' | 'concept'

export interface WikiFilePageSummary {
  type: WikiFilePageType
  id: string
  title: string
}

export interface WikiFilePageDetail {
  type: WikiFilePageType
  id: string
  title: string
  markdown: string
}

export interface WikiArticleEntity {
  name: string
  entity_type?: string
  aliases?: string[]
  description?: string
  semantic_related?: string[]
  claims?: string[]
  evidence?: WikiArticleEvidence[]
  confidence?: number
}

export interface WikiArticleConcept {
  name: string
  aliases?: string[]
  description?: string
  parent?: string | null
  related?: string[]
  semantic_related?: string[]
  claims?: string[]
  evidence?: WikiArticleEvidence[]
  confidence?: number
}

export interface WikiArticleClaim {
  claim: string
  target_name?: string
  target_type?: string
  evidence_ids?: string[]
  confidence?: number
}

export interface WikiArticleEvidence {
  evidence_id: string
  source_id?: string
  source_type?: string
  text: string
  timestamp?: number | null
  url?: string | null
}

export interface WikiArticleRelation {
  source: string
  target: string
  relation_type: string
  weight?: number
}

export interface WikiArticleDetail {
  id: string
  title: string
  source_type?: string
  summary?: string
  topics?: string[]
  entities: WikiArticleEntity[]
  concepts: WikiArticleConcept[]
  claims: WikiArticleClaim[]
  evidence: WikiArticleEvidence[]
  relations: WikiArticleRelation[]
  markdown?: string
}

export const getWikiGraph = async (): Promise<WikiGraph> => {
  return (await request.get<WikiGraph>('/wiki/graph')) as unknown as WikiGraph
}

export const getWikiPages = async (): Promise<WikiPageSummary[]> => {
  return (await request.get<WikiPageSummary[]>('/wiki/pages')) as unknown as WikiPageSummary[]
}

export const getWikiPageDetail = async (pageId: string): Promise<WikiPageDetail> => {
  return (await request.get<WikiPageDetail>(`/wiki/pages/${encodeURIComponent(pageId)}`)) as unknown as WikiPageDetail
}

export const getWikiFilePages = async (): Promise<WikiFilePageSummary[]> => {
  return (await request.get<WikiFilePageSummary[]>('/wiki/file-pages')) as unknown as WikiFilePageSummary[]
}

export const getWikiFilePageDetail = async (
  pageType: WikiFilePageType,
  pageId: string,
): Promise<WikiFilePageDetail> => {
  return (await request.get<WikiFilePageDetail>(
    `/wiki/file-pages/${encodeURIComponent(pageType)}/${encodeURIComponent(pageId)}`,
  )) as unknown as WikiFilePageDetail
}

export const getWikiArticleDetail = async (sourceId: string): Promise<WikiArticleDetail> => {
  return (await request.get<WikiArticleDetail>(`/wiki/articles/${encodeURIComponent(sourceId)}`)) as unknown as WikiArticleDetail
}

export const cancelWikiExtraction = async (taskId: string): Promise<unknown> => {
  return request.post(`/wiki/cancel/${encodeURIComponent(taskId)}`)
}
