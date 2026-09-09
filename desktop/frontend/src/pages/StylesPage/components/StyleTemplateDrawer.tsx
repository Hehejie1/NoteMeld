import { FC, useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import type { NoteStylePayload, OutputFormat } from '@/services/noteStyle'
import ConstraintEditor from './ConstraintEditor'
import ExamplePreview from './ExamplePreview'
import RuleConfigEditor from './RuleConfigEditor'
import SkeletonEditor from './SkeletonEditor'
import StyleImportChat, {
  type StyleImportConversationItem,
  type StyleImportDraft,
  type StyleImportSubmitPayload,
} from './StyleImportChat'

const MIN_DRAWER_WIDTH = 960
const DEFAULT_DRAWER_WIDTH = 960
const RIGHT_PANEL_WIDTH = 560
const LEFT_PANEL_MIN_WIDTH = MIN_DRAWER_WIDTH - RIGHT_PANEL_WIDTH

interface Props {
  open: boolean
  title: string
  value: NoteStylePayload
  readonly?: boolean
  submitting?: boolean
  importing?: boolean
  importConversation?: StyleImportConversationItem[]
  importDraft: StyleImportDraft
  onChange: (value: NoteStylePayload) => void
  onClose: () => void
  onSubmit: () => void
  onImportDraftChange: (draft: StyleImportDraft) => void
  onImportSubmit: (payload: StyleImportSubmitPayload) => void
  onImportRetry: (taskId: string) => void
  onImportCancel: (taskId: string) => void
  onImportRestoreDraft: (requestId: string) => void
  onImportUsePrompt: (prompt: string) => void
  onImportViewVersion: (version: NoteStylePayload) => void
}

const toggleFormat = (formats: OutputFormat[], format: OutputFormat): OutputFormat[] => {
  const next = formats.includes(format)
    ? formats.filter(item => item !== format)
    : [...formats, format]
  return next.length ? next : ['markdown']
}

const StyleTemplateDrawer: FC<Props> = ({
  open,
  title,
  value,
  readonly,
  submitting,
  importing,
  importConversation,
  importDraft,
  onChange,
  onClose,
  onSubmit,
  onImportDraftChange,
  onImportSubmit,
  onImportRetry,
  onImportCancel,
  onImportRestoreDraft,
  onImportUsePrompt,
  onImportViewVersion,
}) => {
  const draggingRef = useRef(false)
  const [drawerWidth, setDrawerWidth] = useState(DEFAULT_DRAWER_WIDTH)

  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      if (!draggingRef.current) return
      const viewportWidth = window.innerWidth
      const maxWidth = Math.max(MIN_DRAWER_WIDTH, Math.floor(viewportWidth * 0.85))
      const nextWidth = viewportWidth - event.clientX
      setDrawerWidth(Math.min(maxWidth, Math.max(MIN_DRAWER_WIDTH, nextWidth)))
    }
    const onUp = () => {
      if (!draggingRef.current) return
      draggingRef.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  useEffect(() => {
    if (!open) {
      setDrawerWidth(DEFAULT_DRAWER_WIDTH)
      return
    }
    const maxWidth = Math.max(MIN_DRAWER_WIDTH, Math.floor(window.innerWidth * 0.85))
    setDrawerWidth(width => Math.min(maxWidth, Math.max(MIN_DRAWER_WIDTH, width)))
  }, [open])

  const startDrawerResize = (event: React.MouseEvent) => {
    event.preventDefault()
    draggingRef.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  const leftPanelWidth = Math.max(LEFT_PANEL_MIN_WIDTH, drawerWidth - RIGHT_PANEL_WIDTH)

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30">
      <div
        className="relative flex h-full bg-white shadow-2xl"
        style={{ width: `${drawerWidth}px`, minWidth: `${MIN_DRAWER_WIDTH}px`, maxWidth: '85vw' }}
      >
        <button
          type="button"
          aria-label="调整模板抽屉宽度"
          onMouseDown={startDrawerResize}
          className="group/resizer absolute inset-y-0 left-0 z-20 w-2 -translate-x-1/2 cursor-col-resize bg-transparent"
        >
          <span
            className={cn(
              'absolute inset-y-0 left-1/2 w-1 -translate-x-1/2 transition-colors',
              draggingRef.current ? 'bg-primary/50' : 'group-hover/resizer:bg-primary/40',
            )}
          />
        </button>
        <StyleImportChat
          leftPanelWidth={leftPanelWidth}
          conversation={importConversation || []}
          draft={importDraft}
          submitting={importing}
          onDraftChange={onImportDraftChange}
          onSubmit={onImportSubmit}
          onRetry={onImportRetry}
          onCancelTask={onImportCancel}
          onRestoreDraft={onImportRestoreDraft}
          onUsePrompt={onImportUsePrompt}
          onViewVersion={onImportViewVersion}
        />
        <div className="flex min-w-0 shrink-0 flex-col border-l border-border-subtle" style={{ width: `${RIGHT_PANEL_WIDTH}px` }}>
          <header className="flex h-14 items-center justify-between border-b border-border-subtle px-5">
            <h2 className="font-display text-[17px] font-bold text-on-surface">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-on-surface-variant hover:bg-surface-container"
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          <ScrollArea className="min-h-0 flex-1">
            <div className="space-y-5 p-5">
              <section className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-[12px] font-medium text-on-surface">
                    模板标题
                  </label>
                  <Input
                    value={value.name}
                    maxLength={20}
                    readOnly={readonly}
                    onChange={event => onChange({ ...value, name: event.target.value })}
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-[12px] font-medium text-on-surface">
                    简介
                  </label>
                  <Input
                    value={value.description}
                    readOnly={readonly}
                    onChange={event => onChange({ ...value, description: event.target.value })}
                  />
                </div>
              </section>

              <section className="flex gap-4">
                {(['html', 'markdown'] as OutputFormat[]).map(format => (
                  <label key={format} className="flex items-center gap-2 text-[13px] text-on-surface">
                    <Checkbox
                      checked={value.output_formats.includes(format)}
                      disabled={readonly}
                      onCheckedChange={() =>
                        onChange({ ...value, output_formats: toggleFormat(value.output_formats, format) })
                      }
                    />
                    {format.toUpperCase()}
                  </label>
                ))}
              </section>

              <SkeletonEditor
                value={value.skeleton_html}
                readonly={readonly}
                onChange={next => onChange({ ...value, skeleton_html: next })}
              />
              <ConstraintEditor
                value={value.style_constraints}
                readonly={readonly}
                onChange={next => onChange({ ...value, style_constraints: next })}
              />
              <RuleConfigEditor
                value={value.rule_config}
                readonly={readonly}
                onChange={next => onChange({ ...value, rule_config: next })}
              />
              <ExamplePreview
                value={value.example_content}
                outputFormats={value.output_formats}
              />
            </div>
          </ScrollArea>

          {!readonly && (
            <footer className="flex justify-end gap-2 border-t border-border-subtle px-5 py-3">
              <Button type="button" variant="outline" onClick={onClose}>
                取消
              </Button>
              <Button
                type="button"
                disabled={submitting}
                className="bg-primary text-white hover:bg-primary/90"
                onClick={onSubmit}
              >
                {submitting ? '保存中...' : '保存'}
              </Button>
            </footer>
          )}
        </div>
      </div>
    </div>
  )
}

export default StyleTemplateDrawer
