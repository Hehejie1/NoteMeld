import { type FC, type JSX } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  XCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'

export type TaskCardStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'CANCELED'

export interface TaskCardState {
  card_id: string
  kind: string
  task_id?: string
  status: TaskCardStatus
  title: string
  progress: number | null
  details?: string
}

interface TaskCardProps {
  card: TaskCardState
  onCancel?: (cardId: string) => void
}

interface StatusStyle {
  label: string
  icon: JSX.Element
  barClass: string
  badgeClass: string
  iconClass: string
}

const useStatusStyle = (status: TaskCardStatus): StatusStyle => {
  switch (status) {
    case 'PENDING':
      return {
        label: '等待中',
        icon: <Loader2 className="h-4 w-4 animate-spin" />,
        barClass: 'bg-on-surface-variant/40',
        badgeClass: 'bg-surface-container text-on-surface-variant',
        iconClass: 'text-on-surface-variant',
      }
    case 'RUNNING':
      return {
        label: '进行中',
        icon: <Loader2 className="h-4 w-4 animate-spin" />,
        barClass: 'bg-primary',
        badgeClass: 'bg-primary/10 text-primary',
        iconClass: 'text-primary',
      }
    case 'SUCCESS':
      return {
        label: '已完成',
        icon: <CheckCircle2 className="h-4 w-4" />,
        barClass: 'bg-status-success',
        badgeClass: 'bg-status-success/10 text-status-success',
        iconClass: 'text-status-success',
      }
    case 'FAILED':
      return {
        label: '已失败',
        icon: <AlertCircle className="h-4 w-4" />,
        barClass: 'bg-destructive',
        badgeClass: 'bg-destructive/10 text-destructive',
        iconClass: 'text-destructive',
      }
    case 'CANCELED':
      return {
        label: '已取消',
        icon: <XCircle className="h-4 w-4" />,
        barClass: 'bg-on-surface-variant/40',
        badgeClass: 'bg-surface-container text-on-surface-variant',
        iconClass: 'text-on-surface-variant',
      }
    default:
      return {
        label: status,
        icon: <Loader2 className="h-4 w-4" />,
        barClass: 'bg-on-surface-variant/40',
        badgeClass: 'bg-surface-container text-on-surface-variant',
        iconClass: 'text-on-surface-variant',
      }
  }
}

const formatProgress = (progress: number | null): number => {
  if (typeof progress !== 'number' || !Number.isFinite(progress)) return 0
  return Math.min(100, Math.max(0, Math.round(progress)))
}

const TaskCard: FC<TaskCardProps> = ({ card, onCancel }) => {
  const style = useStatusStyle(card.status)
  const showProgress = card.status === 'RUNNING' && card.progress !== null
  const showCancel = card.status === 'PENDING' || card.status === 'RUNNING'
  const progressValue = formatProgress(card.progress ?? null)

  return (
    <div className="flex w-full min-w-0 items-start gap-2 md:gap-3">
      <div className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary md:flex">
        <span className={cn('inline-flex items-center justify-center', style.iconClass)}>
          {style.icon}
        </span>
      </div>
      <div className="relative min-w-0 flex-1 overflow-hidden rounded-xl rounded-tl-sm border border-border-subtle bg-white px-4 py-3 shadow-[0_2px_12px_rgba(15,23,42,0.04)] max-w-[600px]">
        {/* 左侧状态色条 */}
        <span
          aria-hidden
          className={cn('absolute inset-y-0 left-0 w-1', style.barClass)}
        />
        <div className="flex items-start justify-between gap-3 pl-1">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className={cn('inline-flex md:hidden', style.iconClass)}>
                {style.icon}
              </span>
              <span className="truncate text-[14px] font-semibold text-on-surface">
                {card.title || '长任务'}
              </span>
              <span
                className={cn(
                  'shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium',
                  style.badgeClass,
                )}
              >
                {style.label}
              </span>
            </div>
            {showProgress && (
              <div className="mt-2">
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-container">
                  <div
                    className={cn('h-full rounded-full transition-all', style.barClass)}
                    style={{ width: `${progressValue}%` }}
                  />
                </div>
                <div className="mt-1 text-[11px] text-on-surface-variant">
                  {progressValue}%
                </div>
              </div>
            )}
            {card.status === 'FAILED' && card.details && (
              <div className="mt-2 break-words text-[12px] leading-relaxed text-destructive">
                {card.details}
              </div>
            )}
            {card.status !== 'FAILED' && card.details && (
              <div className="mt-2 break-words text-[12px] leading-relaxed text-on-surface-variant">
                {card.details}
              </div>
            )}
          </div>
          {showCancel && onCancel && (
            <button
              type="button"
              onClick={() => onCancel(card.card_id)}
              className="inline-flex h-7 shrink-0 items-center rounded-md border border-border-subtle bg-white px-2 text-[12px] text-on-surface-variant transition-colors hover:border-destructive/40 hover:text-destructive"
            >
              取消
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default TaskCard
