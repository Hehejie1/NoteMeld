export type ProgressTimingState = 'running' | 'done' | 'failed' | 'skipped'

export interface ProgressTiming {
  status?: ProgressTimingState | string
  duration_ms?: number
  elapsed_ms?: number
  message?: string
  error?: string
}

export type CollectorTimings = Record<string, ProgressTiming>

export interface CollectorSubStatus {
  key: string
  label: string
  state: ProgressTimingState | 'pending'
  detail: string
  timingLabel: string
}
