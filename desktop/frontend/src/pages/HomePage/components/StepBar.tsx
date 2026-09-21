import { FC } from 'react'
import { CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getCollectorSubStatuses, type CollectorTimings } from '@/pages/HomePage/progressSteps'

interface Step {
  label: string
  key: string
  Icon?: React.ReactNode // 加一个可选的 Lottie 动画
}

interface StepBarProps {
  steps: Step[]
  currentStep: string
  collectorTimings?: CollectorTimings
}

const StepBar: FC<StepBarProps> = ({ steps, currentStep, collectorTimings }) => {
  const currentIndex = steps.findIndex(step => step.key === currentStep)
  const collectorSubStatuses = getCollectorSubStatuses(collectorTimings)

  return (
    <div className="flex w-full flex-col items-center gap-4">
      <div className="flex w-full items-center justify-between">
        {steps.map((step, index) => {
          const isActive = index <= currentIndex
          const isCurrent = index === currentIndex
          return (
            <div key={step.key} className="relative flex flex-1 flex-col items-center">
              {/* 圆圈或者Lottie */}
              <div className="relative flex flex-col items-center justify-center">
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold ${
                    isActive ? 'bg-primary text-white' : 'bg-gray-300 text-gray-600'
                  }`}
                >
                  {index + 1}
                </div>
                {/* 当前步骤显示动画 */}
                {isCurrent && step.Icon && (
                  <div className="absolute top-10 h-16 w-16">{step.Icon}</div>
                )}
              </div>

              {/* 步骤名称 */}
              <div className="mt-4 text-center text-xs text-gray-700">{step.label}</div>

              {/* 连接线 */}

              <div className={`h-1 w-full ${isActive ? 'bg-primary' : 'bg-gray-300'}`}></div>
            </div>
          )
        })}
      </div>
      {collectorSubStatuses.length > 0 && (
        <div className="flex max-w-full flex-wrap justify-center gap-2">
          {collectorSubStatuses.map(item => {
            const running = item.state === 'running'
            const done = item.state === 'done'
            const failed = item.state === 'failed'
            return (
              <div
                key={item.key}
                className={cn(
                  'inline-flex max-w-[220px] items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs',
                  done
                    ? 'border-status-success/30 bg-status-success/10 text-status-success'
                    : failed
                    ? 'border-destructive/30 bg-destructive/10 text-destructive'
                    : running
                    ? 'border-primary/30 bg-primary-light text-primary'
                    : 'border-border-subtle bg-surface-container text-on-surface-variant',
                )}
              >
                {done ? (
                  <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                ) : failed ? (
                  <XCircle className="h-3.5 w-3.5 shrink-0" />
                ) : running ? (
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                ) : (
                  <Circle className="h-3.5 w-3.5 shrink-0" />
                )}
                <span className="shrink-0 font-medium">{item.label}</span>
                {item.detail && <span className="truncate opacity-80">{item.detail}</span>}
                {item.timingLabel && <span className="shrink-0 font-mono opacity-70">{item.timingLabel}</span>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default StepBar
