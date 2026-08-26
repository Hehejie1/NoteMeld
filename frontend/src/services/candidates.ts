import request from '@/utils/request'

export type Candidate = {
  id: string
  kind: 'application' | 'plugin'
  title: string
  status: string
  scope: Record<string, unknown>
  evidence: unknown[]
  trace: unknown[]
  artifact: Record<string, unknown>
  patch: Record<string, unknown>
  tests: Array<Record<string, unknown>>
  risks: unknown[]
  permissions: string[]
  rollback: Record<string, unknown>
  validation: { errors?: string[]; model_safety_claim_used?: boolean }
  next_step: string
}

export const listCandidates = () => request.get<any, { candidates: Candidate[] }>('/candidates')
export const validateCandidate = (id: string) => request.post<any, Candidate>(`/candidates/${encodeURIComponent(id)}/validate`)
export const decideCandidate = (id: string, approved: boolean) => request.post<any, Candidate>(`/candidates/${encodeURIComponent(id)}/decision`, { approved })
