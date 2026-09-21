import * as React from 'react'
import { cn } from './cn'

type FeedbackProps = { title?: React.ReactNode; description?: React.ReactNode; action?: React.ReactNode; className?: string }
type FeedbackSectionProps = FeedbackProps & Omit<React.ComponentProps<'section'>, 'title'>

function Feedback({ title, description, action, className, role = 'status', ...props }: FeedbackSectionProps) {
  return <section role={role} className={cn('flex min-h-32 flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center', className)} {...props}>{title ? <h2 className="text-sm font-semibold">{title}</h2> : null}{description ? <p className="text-muted-foreground max-w-prose text-sm">{description}</p> : null}{action ? <div className="mt-2">{action}</div> : null}</section>
}
function EmptyState(props: FeedbackSectionProps) { return <Feedback {...props} role="status" /> }
function ErrorState(props: FeedbackSectionProps) { return <Feedback {...props} role="alert" /> }
function OfflineState(props: FeedbackSectionProps) { return <Feedback {...props} role="status" /> }
function LoadingState({ title = 'Loading', ...props }: FeedbackSectionProps) { return <Feedback title={title} {...props} aria-live="polite" /> }

export { Feedback, EmptyState, ErrorState, OfflineState, LoadingState }
