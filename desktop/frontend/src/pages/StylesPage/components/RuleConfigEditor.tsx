import { FC, useEffect, useMemo, useState } from 'react'
import { Textarea } from '@/components/ui/textarea'
import type { RuleConfig } from '@/services/noteStyle'

interface Props {
  value: RuleConfig
  readonly?: boolean
  onChange: (value: RuleConfig) => void
}

const RuleConfigEditor: FC<Props> = ({ value, readonly, onChange }) => {
  const renderedValue = useMemo(() => JSON.stringify(value, null, 2), [value])
  const [draft, setDraft] = useState(renderedValue)

  useEffect(() => {
    setDraft(renderedValue)
  }, [renderedValue])

  return (
    <section className="space-y-2">
      <h3 className="text-[13px] font-semibold text-on-surface">规则配置</h3>
      <Textarea
        value={draft}
        readOnly={readonly}
        rows={7}
        className="min-h-[160px] resize-y border-border-subtle font-mono text-[12px]"
        onChange={event => {
          const next = event.target.value
          setDraft(next)
          try {
            onChange(JSON.parse(next) as RuleConfig)
          } catch {
            // Keep invalid JSON visible until the user fixes it.
          }
        }}
        onBlur={() => setDraft(renderedValue)}
      />
    </section>
  )
}

export default RuleConfigEditor
