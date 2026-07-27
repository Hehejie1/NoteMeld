import { FC, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import TemplateRenderPreviewDialog from './TemplateRenderPreviewDialog'

interface Props {
  value: string
  readonly?: boolean
  onChange: (value: string) => void
}

const SkeletonEditor: FC<Props> = ({ value, readonly, onChange }) => {
  const [previewOpen, setPreviewOpen] = useState(false)

  return (
    <>
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-[13px] font-semibold text-on-surface">骨架模板</h3>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!value}
            onClick={() => setPreviewOpen(true)}
          >
            预览
          </Button>
        </div>
        <Textarea
          value={value}
          readOnly={readonly}
          rows={8}
          className="min-h-[180px] resize-y border-border-subtle font-mono text-[12px]"
          placeholder="<article class=&quot;note-template&quot;>...</article>"
          onChange={event => onChange(event.target.value)}
        />
      </section>

      <TemplateRenderPreviewDialog
        open={previewOpen}
        title="骨架模板预览"
        mode="html"
        content={value}
        htmlVariant="skeleton"
        description="通过占位内容预览骨架结构，不会回写真实模板。"
        onOpenChange={setPreviewOpen}
      />
    </>
  )
}

export default SkeletonEditor
