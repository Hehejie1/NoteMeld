import { FC, useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { NoteStylePayload, OutputFormat } from '@/services/noteStyle'
import TemplateRenderPreviewDialog, {
  type TemplateHtmlVariant,
  type TemplatePreviewMode,
} from './TemplateRenderPreviewDialog'

interface Props {
  open: boolean
  version: NoteStylePayload | null
  onOpenChange: (open: boolean) => void
}

type PreviewState = {
  title: string
  mode: TemplatePreviewMode
  content: string
  htmlVariant?: TemplateHtmlVariant
} | null

const TemplateVersionDialog: FC<Props> = ({ open, version, onOpenChange }) => {
  const [previewState, setPreviewState] = useState<PreviewState>(null)

  const selectorWarnings = useMemo(
    () => JSON.stringify(version?.style_constraints || {}, null, 2),
    [version?.style_constraints],
  )
  const ruleConfig = useMemo(
    () => JSON.stringify(version?.rule_config || {}, null, 2),
    [version?.rule_config],
  )

  const supportsFormat = (format: OutputFormat) => version?.output_formats.includes(format)

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] max-w-[calc(100vw-32px)] overflow-hidden p-0 md:max-w-[960px]">
          <DialogHeader className="border-b border-border-subtle px-6 py-5">
            <DialogTitle>临时版本内容</DialogTitle>
            <DialogDescription>
              这里只读查看当前对话成功生成的临时版本。真正保存仍以右侧当前模板为准。
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[calc(90vh-88px)] space-y-5 overflow-auto bg-surface-container-low p-6">
            <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="rounded-xl border border-border-subtle bg-white p-4 shadow-sm">
                <div className="mb-2 text-[12px] font-medium text-on-surface-variant">模板标题</div>
                <div className="text-[14px] font-medium text-on-surface">{version?.name || '-'}</div>
              </div>
              <div className="rounded-xl border border-border-subtle bg-white p-4 shadow-sm">
                <div className="mb-2 text-[12px] font-medium text-on-surface-variant">简介</div>
                <div className="text-[14px] text-on-surface">{version?.description || '-'}</div>
              </div>
            </section>

            <section className="rounded-xl border border-border-subtle bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <div className="text-[13px] font-semibold text-on-surface">骨架模板</div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!version?.skeleton_html}
                  onClick={() =>
                    setPreviewState({
                      title: '骨架模板预览',
                      mode: 'html',
                      content: version?.skeleton_html || '',
                      htmlVariant: 'skeleton',
                    })
                  }
                >
                  预览骨架
                </Button>
              </div>
              <pre className="max-h-[220px] overflow-auto rounded-lg bg-surface-container-low p-3 text-[12px] text-on-surface">
                {version?.skeleton_html || '暂无骨架模板'}
              </pre>
            </section>

            <section className="grid grid-cols-1 gap-5 md:grid-cols-2">
              <div className="rounded-xl border border-border-subtle bg-white p-4 shadow-sm">
                <div className="mb-3 text-[13px] font-semibold text-on-surface">风格约束</div>
                <pre className="max-h-[260px] overflow-auto rounded-lg bg-surface-container-low p-3 text-[12px] text-on-surface">
                  {selectorWarnings}
                </pre>
              </div>
              <div className="rounded-xl border border-border-subtle bg-white p-4 shadow-sm">
                <div className="mb-3 text-[13px] font-semibold text-on-surface">规则配置</div>
                <pre className="max-h-[260px] overflow-auto rounded-lg bg-surface-container-low p-3 text-[12px] text-on-surface">
                  {ruleConfig}
                </pre>
              </div>
            </section>

            <section className="rounded-xl border border-border-subtle bg-white p-4 shadow-sm">
              <div className="mb-3 text-[13px] font-semibold text-on-surface">笔记案例</div>
              <div className="flex flex-wrap gap-2">
                {supportsFormat('markdown') && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!version?.example_content?.markdown}
                    onClick={() =>
                      setPreviewState({
                        title: 'Markdown 案例预览',
                        mode: 'markdown',
                        content: version?.example_content?.markdown || '',
                      })
                    }
                  >
                    预览 MD
                  </Button>
                )}
                {supportsFormat('html') && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!version?.example_content?.html}
                    onClick={() =>
                      setPreviewState({
                        title: 'HTML 案例预览',
                        mode: 'html',
                        content: version?.example_content?.html || '',
                        htmlVariant: 'raw',
                      })
                    }
                  >
                    预览 HTML
                  </Button>
                )}
                {!supportsFormat('markdown') && !supportsFormat('html') && (
                  <div className="text-[12px] text-on-surface-variant">当前版本没有可预览的案例格式。</div>
                )}
              </div>
            </section>
          </div>
        </DialogContent>
      </Dialog>

      <TemplateRenderPreviewDialog
        open={!!previewState}
        title={previewState?.title || '内容预览'}
        mode={previewState?.mode || 'html'}
        content={previewState?.content || ''}
        htmlVariant={previewState?.htmlVariant}
        onOpenChange={open => !open && setPreviewState(null)}
      />
    </>
  )
}

export default TemplateVersionDialog
