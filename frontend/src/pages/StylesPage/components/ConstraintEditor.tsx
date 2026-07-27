import { FC, useEffect, useMemo, useState } from 'react'
import { Textarea } from '@/components/ui/textarea'
import type { StyleConstraints } from '@/services/noteStyle'

interface Props {
  value: StyleConstraints
  readonly?: boolean
  onChange: (value: StyleConstraints) => void
}

const ConstraintEditor: FC<Props> = ({ value, readonly, onChange }) => {
  const renderedValue = useMemo(() => JSON.stringify(value, null, 2), [value])
  const [draft, setDraft] = useState(renderedValue)

  useEffect(() => {
    setDraft(renderedValue)
  }, [renderedValue])

  return (
    <section className="space-y-2">
      <h3 className="text-[13px] font-semibold text-on-surface">风格约束</h3>
      <Textarea
        value={draft}
        readOnly={readonly}
        rows={8}
        className="min-h-[180px] resize-y border-border-subtle font-mono text-[12px]"
        onChange={event => {
          const next = event.target.value
          setDraft(next)
          try {
            onChange(JSON.parse(next) as StyleConstraints)
          } catch {
            // Keep invalid JSON in the draft so users can continue editing.
          }
        }}
        onBlur={() => setDraft(renderedValue)}
      />
    </section>
  )
}

export default ConstraintEditor
