import type { TaskStatus } from '@/store/taskStore'
import type { CollectorSubStatus, CollectorTimings, ProgressTiming } from '@/types/progress'

export type { CollectorSubStatus, CollectorTimings, ProgressTiming, ProgressTimingState } from '@/types/progress'

export interface StepDef {
  label: string
  key: TaskStatus
  matches: TaskStatus[]
}

const allSteps: StepDef[] = [
  { label: '等待执行', key: 'PENDING', matches: ['PENDING'] },
  { label: '解析链接', key: 'PARSING', matches: ['PARSING'] },
  { label: '采集素材', key: 'DOWNLOADING', matches: ['DOWNLOADING'] },
  { label: '转写文字', key: 'TRANSCRIBING', matches: ['TRANSCRIBING'] },
  { label: '总结内容', key: 'SUMMARIZING', matches: ['SUMMARIZING'] },
  { label: '保存笔记', key: 'SAVING', matches: ['SAVING'] },
  { label: '保存完成', key: 'SUCCESS', matches: ['SUCCESS'] },
]

const normalizeVisibleStatus = (status: TaskStatus): TaskStatus =>
  status === 'FORMATTING' ? 'SUMMARIZING' : status

const collectorLabels: Record<string, string> = {
  web_search: '网页搜索',
  transcript: '音频转写',
  frames: '视频分帧',
}

const collectorOrder = ['web_search', 'transcript', 'frames']

const formatDuration = (durationMs: unknown): string => {
  if (typeof durationMs !== 'number' || !Number.isFinite(durationMs) || durationMs < 0) return ''
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`
  const seconds = durationMs / 1000
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  const minutes = Math.floor(seconds / 60)
  const restSeconds = Math.round(seconds % 60)
  return `${minutes}m${restSeconds}s`
}

const normalizeCollectorState = (status: unknown): CollectorSubStatus['state'] => {
  if (status === 'running' || status === 'done' || status === 'failed' || status === 'skipped') {
    return status
  }
  return 'pending'
}

export const hasCollectorTimings = (collectorTimings?: CollectorTimings | null): boolean =>
  Boolean(collectorTimings && Object.keys(collectorTimings).length > 0)

export const getCollectorSubStatuses = (
  collectorTimings?: CollectorTimings | null,
): CollectorSubStatus[] => {
  if (!collectorTimings) return []
  const keys = [
    ...collectorOrder.filter(key => collectorTimings[key]),
    ...Object.keys(collectorTimings).filter(key => !collectorOrder.includes(key)),
  ]

  return keys.map(key => {
    const timing: ProgressTiming = collectorTimings[key] || {}
    const state = normalizeCollectorState(timing.status)
    return {
      key,
      label: collectorLabels[key] || key,
      state,
      detail: timing.error || timing.message || '',
      timingLabel: formatDuration(timing.duration_ms ?? timing.elapsed_ms),
    }
  })
}

export const getLoadingProgressCopy = (collectorTimings?: CollectorTimings | null) =>
  hasCollectorTimings(collectorTimings)
    ? {
        title: '正在采集素材，请稍候…',
        description: '网页搜索、音频转写和视频分帧会并行推进',
      }
    : {
        title: '正在生成笔记，请稍候…',
        description: '这可能需要几秒钟时间，取决于视频长度',
      }

export const getProgressSteps = (platform?: string | null): StepDef[] =>
  platform === 'web_link'
    ? allSteps.filter(step => !['采集素材', '转写文字'].includes(step.label))
    : allSteps

export const getStepIndex = (status: TaskStatus, platform?: string | null): number => {
  if (status === 'FAILED' || status === 'CANCELED' || status === 'NOT_FOUND') return -1
  const visibleStatus = normalizeVisibleStatus(status)
  const steps = getProgressSteps(platform)
  return Math.max(
    0,
    steps.findIndex(step => step.matches.includes(visibleStatus)),
  )
}
