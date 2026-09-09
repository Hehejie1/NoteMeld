import {
  getCollectorSubStatuses,
  getLoadingProgressCopy,
  getProgressSteps,
  type CollectorTimings,
} from '../src/pages/HomePage/progressSteps'
import type { TaskStatusMeta } from '../src/store/taskStore'
import type { TaskStatusResponse } from '../src/services/note'

const timings: CollectorTimings = {
  web_search: { status: 'done', duration_ms: 1200, message: '网页搜索中' },
  transcript: { status: 'running', elapsed_ms: 3456, message: '音频转文字中' },
  frames: { status: 'skipped', message: '未开启截图' },
}

const response: TaskStatusResponse = {
  status: 'TRANSCRIBING',
  collector_timings: timings,
}

const meta: TaskStatusMeta = {
  taskId: 'task-1',
  collectorTimings: response.collector_timings,
}

const subStatuses = getCollectorSubStatuses(meta.collectorTimings)

if (subStatuses.map(item => item.label).join(',') !== '网页搜索,音频转写,视频分帧') {
  throw new Error('collector sub status labels should follow the collector order')
}

if (subStatuses[1]?.state !== 'running' || subStatuses[1]?.detail !== '音频转文字中') {
  throw new Error('collector sub status should expose running state and detail')
}

if (getLoadingProgressCopy(timings).title !== '正在采集素材，请稍候…') {
  throw new Error('loading copy should mention material collection when collector timings exist')
}

if (!getProgressSteps('youtube').some(step => step.label === '采集素材')) {
  throw new Error('video progress steps should use material collection copy')
}
