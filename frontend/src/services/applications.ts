import request from '@/utils/request'

export type ApplicationStatus =
  | 'installed'
  | 'disabled'
  | 'starting'
  | 'running'
  | 'stopped'
  | 'failed'
  | 'needs_attention'

export type ApplicationRunStatus =
  | 'queued'
  | 'running'
  | 'waiting_user'
  | 'cancelled'
  | 'failed'
  | 'completed'
  | 'interrupted'

export interface ApplicationPlatformSupport {
  desktop?: 'supported' | 'unsupported'
  web?: 'supported' | 'unsupported'
  mobile?: 'supported' | 'unsupported'
}

export interface ApplicationDiagnostic {
  code: string
  message: string
  capability?: string
}

export interface ApplicationSummary {
  id: string
  name: string
  version: string
  description?: string
  icon?: string
  status: ApplicationStatus
  enabled: boolean
  platforms?: ApplicationPlatformSupport
  capabilities?: string[]
  missing_capabilities?: string[]
  diagnostics?: ApplicationDiagnostic[]
}

export interface ApplicationDetail extends ApplicationSummary {
  protocol?: string
  permissions?: string[]
  runtime?: {
    kind?: string
    entry?: string
  }
  ui?: {
    entry?: string
  }
}

export interface ApplicationWorkspaceSetting {
  workspace_ref: string
  configured: boolean
  root: string
}

export interface ApplicationInstance {
  id: string
  app_id: string
  title: string
  status?: ApplicationStatus
  workspace?: string
}

export interface ApplicationRun {
  run_id: string
  app_id: string
  instance_id: string
  status: ApplicationRunStatus
  request_id?: string | null
  runtime_kind?: string
  cancel_requested?: boolean
  error?: { code?: string | null; message?: string | null } | null
}

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

export interface WikiArticleEntity {
  name: string
  entity_type?: string
  aliases?: string[]
  description?: string
  claims?: string[]
  confidence?: number
}

export interface WikiArticleConcept {
  name: string
  aliases?: string[]
  description?: string
  related?: string[]
  claims?: string[]
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

const applicationPath = (appId: string) => `/applications/${encodeURIComponent(appId)}`

export const getApplicationWorkspaceSetting = async (): Promise<ApplicationWorkspaceSetting> =>
  request.get<ApplicationWorkspaceSetting>('/applications/settings/workspace') as unknown as Promise<ApplicationWorkspaceSetting>

export const setApplicationWorkspaceSetting = async (root: string): Promise<ApplicationWorkspaceSetting> =>
  request.put<ApplicationWorkspaceSetting>('/applications/settings/workspace', { root }) as unknown as Promise<ApplicationWorkspaceSetting>

export const listApplications = async (): Promise<ApplicationSummary[]> =>
  request.get<ApplicationSummary[]>('/applications') as unknown as Promise<ApplicationSummary[]>

export const getApplication = async (appId: string): Promise<ApplicationDetail> =>
  request.get<ApplicationDetail>(applicationPath(appId)) as unknown as Promise<ApplicationDetail>

export const enableApplication = async (appId: string): Promise<ApplicationDetail> =>
  request.post<ApplicationDetail>(`${applicationPath(appId)}/enable`) as unknown as Promise<ApplicationDetail>

export const disableApplication = async (appId: string): Promise<ApplicationDetail> =>
  request.post<ApplicationDetail>(`${applicationPath(appId)}/disable`) as unknown as Promise<ApplicationDetail>

export const listApplicationInstances = async (appId: string): Promise<ApplicationInstance[]> =>
  request.get<ApplicationInstance[]>(`${applicationPath(appId)}/instances`) as unknown as Promise<ApplicationInstance[]>

export const createApplicationInstance = async (
  appId: string,
  payload: { title?: string },
): Promise<ApplicationInstance> =>
  request.post<ApplicationInstance>(`${applicationPath(appId)}/instances`, payload) as unknown as Promise<ApplicationInstance>

export const startApplicationRun = async (
  appId: string,
  instanceId: string,
): Promise<ApplicationRun> =>
  request.post<ApplicationRun>(`${applicationPath(appId)}/instances/${encodeURIComponent(instanceId)}/runs`, {}) as unknown as Promise<ApplicationRun>

export const getApplicationRun = async (runId: string): Promise<ApplicationRun> =>
  request.get<ApplicationRun>(`/applications/runs/${encodeURIComponent(runId)}`) as unknown as Promise<ApplicationRun>

export const invokeApplicationRun = async (
  runId: string,
  method: string,
  input: Record<string, unknown> = {},
): Promise<Record<string, unknown>> =>
  request.post<Record<string, unknown>>(`/applications/runs/${encodeURIComponent(runId)}/invoke`, { method, input }) as unknown as Promise<Record<string, unknown>>

export const invokeApplicationCapability = async <T>(
  runId: string,
  capability: string,
  method: string,
  input: Record<string, unknown> = {},
): Promise<T> =>
  request.post<T>(`/applications/runs/${encodeURIComponent(runId)}/capability`, { capability, method, input }) as unknown as Promise<T>

export const cancelApplicationRun = async (runId: string): Promise<ApplicationRun> =>
  request.post<ApplicationRun>(`/applications/runs/${encodeURIComponent(runId)}/cancel`) as unknown as Promise<ApplicationRun>
