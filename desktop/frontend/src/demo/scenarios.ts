export type DemoScenarioOutcome = 'success' | 'failed' | 'canceled'
export type DemoTaskStep =
  | 'PENDING'
  | 'PARSING'
  | 'DOWNLOADING'
  | 'TRANSCRIBING'
  | 'SUMMARIZING'
  | 'FORMATTING'
  | 'SAVING'
  | 'SUCCESS'
  | 'FAILED'
  | 'CANCELED'

export interface DemoScheduler {
  schedule(callback: () => void, delayMilliseconds: number): unknown
  cancel(handle: unknown): void
}

export interface DemoScenarioOptions {
  scheduler?: DemoScheduler
  onStatus: (status: DemoTaskStep) => void
  stepDelayMilliseconds?: number
}

export interface DemoScenarioHandle {
  cancel(): void
  dispose(): void
}

const browserScheduler: DemoScheduler = {
  schedule: (callback, delayMilliseconds) => window.setTimeout(callback, delayMilliseconds),
  cancel: handle => window.clearTimeout(handle as number),
}

const successfulSteps: DemoTaskStep[] = [
  'PENDING',
  'PARSING',
  'DOWNLOADING',
  'TRANSCRIBING',
  'SUMMARIZING',
  'FORMATTING',
  'SAVING',
  'SUCCESS',
]

export const startDemoNoteScenario = (
  outcome: DemoScenarioOutcome,
  options: DemoScenarioOptions,
): DemoScenarioHandle => {
  const scheduler = options.scheduler || browserScheduler
  const delay = options.stepDelayMilliseconds ?? 420
  let disposed = false
  let terminalOverride: DemoTaskStep | null = null
  const handles: unknown[] = []
  const steps = outcome === 'success'
    ? successfulSteps
    : [...successfulSteps.slice(0, 5), outcome === 'failed' ? 'FAILED' : 'CANCELED'] as DemoTaskStep[]

  options.onStatus('PENDING')
  steps.slice(1).forEach((status, index) => {
    const handle = scheduler.schedule(() => {
      if (disposed) return
      if (terminalOverride) {
        options.onStatus(terminalOverride)
        terminalOverride = null
        disposed = true
        return
      }
      options.onStatus(status)
      if (status === 'SUCCESS' || status === 'FAILED' || status === 'CANCELED') disposed = true
    }, delay * (index + 1))
    handles.push(handle)
  })

  const dispose = () => {
    disposed = true
    handles.forEach(handle => scheduler.cancel(handle))
  }

  return {
    cancel: () => {
      if (!disposed) terminalOverride = 'CANCELED'
    },
    dispose,
  }
}
