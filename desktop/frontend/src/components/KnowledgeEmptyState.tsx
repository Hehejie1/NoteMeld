import { type ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface KnowledgeEmptyStateProps {
  title: string
  description: string
  status?: 'empty' | 'loading' | 'error'
  action?: ReactNode
  detail?: ReactNode
  className?: string
}

const statusCopy = {
  empty: ['Input', 'Extract', 'Link'],
  loading: ['Reading', 'Mapping', 'Writing'],
  error: ['Retry', 'Repair', 'Sync'],
}

const KnowledgeEmptyState = ({
  title,
  description,
  status = 'empty',
  action,
  detail,
  className,
}: KnowledgeEmptyStateProps) => {
  const labels = statusCopy[status]

  return (
    <section
      role={status === 'loading' ? 'status' : 'region'}
      aria-live={status === 'loading' ? 'polite' : undefined}
      className={cn('knowledge-empty-state', `knowledge-empty-state--${status}`, className)}
    >
      <div className="knowledge-empty-orbit" aria-hidden="true">
        <span className="knowledge-empty-halo knowledge-empty-halo--outer" />
        <span className="knowledge-empty-halo knowledge-empty-halo--inner" />
        <span className="knowledge-empty-core" />
        <span className="knowledge-empty-link knowledge-empty-link--a" />
        <span className="knowledge-empty-link knowledge-empty-link--b" />
        <span className="knowledge-empty-node knowledge-empty-node--a" />
        <span className="knowledge-empty-node knowledge-empty-node--b" />
        <span className="knowledge-empty-node knowledge-empty-node--c" />
      </div>

      <div className="knowledge-empty-copy">
        <div className="knowledge-empty-kicker">Knowledge Base</div>
        <h2>{title}</h2>
        <p>{description}</p>
        {detail && <div className="knowledge-empty-detail">{detail}</div>}
      </div>

      <div className="knowledge-empty-steps" aria-hidden="true">
        {labels.map(label => (
          <span key={label}>{label}</span>
        ))}
      </div>

      {action && <div className="knowledge-empty-action">{action}</div>}
    </section>
  )
}

export default KnowledgeEmptyState
