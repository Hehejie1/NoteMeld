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
  model_safety_claim?: string | null
  next_step: string
}

export const listCandidates = () => request.get<unknown, { candidates: Candidate[] }>('/candidates')
export const validateCandidate = (id: string) => request.post<unknown, Candidate>(`/candidates/${encodeURIComponent(id)}/validate`)
export const approveCandidate = (id: string, reason?: string) => request.post<unknown, Candidate>(`/candidates/${encodeURIComponent(id)}/approve`, reason?.trim() ? { approved: true, reason: reason.trim() } : undefined)
export const declineCandidate = (id: string, reason?: string) => request.post<unknown, Candidate>(`/candidates/${encodeURIComponent(id)}/decline`, reason?.trim() ? { approved: false, reason: reason.trim() } : undefined)
export const activateApplicationCandidate = (id: string) => request.post<unknown, unknown>(`/applications/candidates/${encodeURIComponent(id)}/activate`)
