import { KeyboardEvent, useMemo, useState } from 'react'
import { Input } from '@/components/ui/input'
import { ProviderTemplate } from '@/components/Form/modelForm/providerTemplates'

interface ProviderNameComboboxProps {
  value: string
  disabled?: boolean
  templates: ProviderTemplate[]
  onChange: (value: string) => void
  onSelectTemplate: (template: ProviderTemplate) => void
  onEnter: () => void
}

const ProviderNameCombobox = ({
  value,
  disabled,
  templates,
  onChange,
  onSelectTemplate,
  onEnter,
}: ProviderNameComboboxProps) => {
  const [open, setOpen] = useState(false)
  const normalizedValue = value.trim().toLowerCase()
  const visibleTemplates = useMemo(() => {
    if (!normalizedValue) return templates
    return templates.filter(template => template.name.toLowerCase().includes(normalizedValue))
  }, [normalizedValue, templates])

  const handleNameKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return
    event.preventDefault()
    setOpen(false)
    onEnter()
  }

  return (
    <div className="relative flex-1">
      <Input
        value={value}
        disabled={disabled}
        onChange={event => {
          onChange(event.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          window.setTimeout(() => setOpen(false), 120)
        }}
        onKeyDown={handleNameKeyDown}
        placeholder="输入名称或选择供应商模板"
        className="w-full"
      />
      {open && visibleTemplates.length > 0 && !disabled && (
        <div className="absolute left-0 right-0 top-[42px] z-30 max-h-56 overflow-auto rounded-lg border border-border-subtle bg-white p-1 shadow-lg">
          {visibleTemplates.map(template => (
            <button
              key={template.key || template.name}
              type="button"
              className="flex w-full flex-col rounded-md px-3 py-2 text-left hover:bg-primary/5"
              onMouseDown={event => {
                event.preventDefault()
                onSelectTemplate(template)
                setOpen(false)
              }}
            >
              <span className="text-sm font-medium text-on-surface">{template.name}</span>
              <span className="truncate text-xs text-on-surface-variant">{template.baseUrl}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default ProviderNameCombobox
