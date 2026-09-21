import * as React from 'react'
import { cn } from './cn'

function Progress({ className, value = 0, ...props }: React.ComponentProps<'div'> & { value?: number | null }) {
  const normalized = Math.min(100, Math.max(0, Number.isFinite(value) ? Number(value) : 0))
  return <div data-slot="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={normalized} className={cn('bg-secondary relative h-2 w-full overflow-hidden rounded-full', className)} {...props}><div data-slot="progress-indicator" className="bg-primary h-full w-full flex-1 transition-all" style={{ transform: `translateX(-${100 - normalized}%)` }} /></div>
}

export { Progress }
