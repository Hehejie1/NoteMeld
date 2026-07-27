import { FC, useState } from 'react'
import { Button } from '@/components/ui/button'
import type { ExampleContent, OutputFormat } from '@/services/noteStyle'
import TemplateRenderPreviewDialog, {
  type TemplatePreviewMode,
} from './TemplateRenderPreviewDialog'

interface Props {
  value: ExampleContent
  outputFormats: OutputFormat[]
}

const ExamplePreview: FC<Props> = ({ value, outputFormats }) => {
  const [mode, setMode] = useState<TemplatePreviewMode | null>(null)

  const markdownEnabled = outputFormats.includes('markdown')
  const htmlEnabled = outputFormats.includes('html')
  const currentContent = mode === 'markdown' ? value.markdown : value.html

  return (
    <>
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-[13px] font-semibold text-on-surface">笔记案例</h3>
          <div className="flex gap-2">
            {markdownEnabled && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!value.markdown}
                onClick={() => setMode('markdown')}
              >
                预览 MD
              </Button>
            )}
            {htmlEnabled && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!value.html}
                onClick={() => setMode('html')}
              >
                预览 HTML
              </Button>
            )}
          </div>
        </div>
        <div className="rounded-lg border border-border-subtle bg-surface-container-low px-3 py-3 text-[12px] leading-relaxed text-on-surface-variant">
          案例内容由模型生成，不在这里直接编辑。请使用上方按钮在弹窗中查看渲染结果。
        </div>
      </section>

      <TemplateRenderPreviewDialog
        open={!!mode}
        title={mode === 'markdown' ? 'Markdown 案例预览' : 'HTML 案例预览'}
        mode={mode || 'markdown'}
        content={currentContent || ''}
        htmlVariant="raw"
        onOpenChange={open => !open && setMode(null)}
      />
    </>
  )
}

export default ExamplePreview
