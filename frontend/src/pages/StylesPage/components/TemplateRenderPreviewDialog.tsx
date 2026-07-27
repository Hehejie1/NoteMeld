import { FC, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

export type TemplatePreviewMode = 'html' | 'markdown'
export type TemplateHtmlVariant = 'raw' | 'skeleton'

interface Props {
  open: boolean
  title: string
  mode: TemplatePreviewMode
  content: string
  htmlVariant?: TemplateHtmlVariant
  description?: string
  onOpenChange: (open: boolean) => void
}

const PREVIEW_STYLE = `
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 24px;
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: #1f2937;
    background: #f8fafc;
    line-height: 1.6;
  }
  article, section, main, aside, header, footer, nav, div {
    display: block;
  }
  article, section, main, aside, header, footer, nav, div, ul, ol, table, blockquote, pre {
    margin-bottom: 16px;
  }
  article, section, main, aside, header, footer {
    border: 1px dashed rgba(99, 102, 241, 0.25);
    border-radius: 16px;
    padding: 16px;
    background: rgba(255,255,255,0.92);
  }
  h1, h2, h3, h4, h5, h6 {
    margin: 0 0 12px;
    font-weight: 700;
    color: #111827;
  }
  p, li, figcaption, blockquote {
    font-size: 14px;
  }
  ul, ol {
    padding-left: 20px;
  }
  img, video {
    display: block;
    width: 100%;
    min-height: 160px;
    border-radius: 12px;
    background: linear-gradient(135deg, rgba(99,102,241,0.12), rgba(59,130,246,0.12));
    border: 1px solid rgba(99,102,241,0.16);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    overflow: hidden;
    border-radius: 12px;
    background: white;
  }
  th, td {
    border: 1px solid rgba(148,163,184,0.35);
    padding: 10px 12px;
    text-align: left;
  }
  blockquote {
    padding: 12px 16px;
    border-left: 4px solid #6366f1;
    background: rgba(99, 102, 241, 0.08);
    border-radius: 12px;
  }
  pre, code {
    font-family: "SFMono-Regular", Consolas, monospace;
  }
  pre {
    padding: 16px;
    background: #0f172a;
    color: #e2e8f0;
    border-radius: 12px;
    overflow: auto;
  }
  .preview-placeholder {
    color: #475569;
  }
`

const hasMeaningfulText = (text: string | null | undefined) => Boolean(text && text.trim())

const injectSkeletonPlaceholders = (rawHtml: string) => {
  if (!rawHtml.trim() || typeof DOMParser === 'undefined') {
    return rawHtml
  }

  const parser = new DOMParser()
  const doc = parser.parseFromString(rawHtml, 'text/html')
  const body = doc.body
  let seed = 1

  const placeholderText = (tag: string) => {
    const index = seed++
    switch (tag) {
      case 'h1':
        return `示例标题 ${index}`
      case 'h2':
      case 'h3':
      case 'h4':
      case 'h5':
      case 'h6':
        return `章节标题 ${index}`
      case 'li':
        return `列表项内容 ${index}`
      case 'blockquote':
        return `这里是引用占位内容 ${index}`
      case 'code':
        return `const placeholder${index} = true`
      case 'figcaption':
        return `配图说明 ${index}`
      case 'a':
        return `链接文本 ${index}`
      case 'th':
        return `表头 ${index}`
      case 'td':
        return `单元格 ${index}`
      default:
        return `这里是用于预览骨架结构的占位内容 ${index}。`
    }
  }

  const visit = (element: Element) => {
    const tag = element.tagName.toLowerCase()
    const children = Array.from(element.children)

    if ((tag === 'ul' || tag === 'ol') && children.length === 0) {
      for (let i = 0; i < 3; i += 1) {
        const li = doc.createElement('li')
        li.textContent = placeholderText('li')
        li.classList.add('preview-placeholder')
        element.appendChild(li)
      }
      return
    }

    if (tag === 'table' && !element.querySelector('tr')) {
      const thead = doc.createElement('thead')
      const headerRow = doc.createElement('tr')
      const tbody = doc.createElement('tbody')
      const bodyRow = doc.createElement('tr')
      for (let i = 0; i < 3; i += 1) {
        const th = doc.createElement('th')
        th.textContent = placeholderText('th')
        const td = doc.createElement('td')
        td.textContent = placeholderText('td')
        headerRow.appendChild(th)
        bodyRow.appendChild(td)
      }
      thead.appendChild(headerRow)
      tbody.appendChild(bodyRow)
      element.appendChild(thead)
      element.appendChild(tbody)
      return
    }

    if (tag === 'img' && !element.getAttribute('alt')) {
      element.setAttribute('alt', '图片占位')
      return
    }

    if (tag === 'video' && !children.length) {
      const fallback = doc.createElement('p')
      fallback.textContent = '视频占位区域'
      fallback.classList.add('preview-placeholder')
      element.appendChild(fallback)
      return
    }

    if (!children.length && !hasMeaningfulText(element.textContent)) {
      if (['article', 'section', 'main', 'aside', 'header', 'footer', 'div'].includes(tag)) {
        const paragraph = doc.createElement('p')
        paragraph.textContent = placeholderText('p')
        paragraph.classList.add('preview-placeholder')
        element.appendChild(paragraph)
        return
      }
      element.textContent = placeholderText(tag)
      element.classList.add('preview-placeholder')
      return
    }

    children.forEach(child => visit(child))
  }

  Array.from(body.children).forEach(child => visit(child))
  return body.innerHTML
}

const buildPreviewDoc = (rawHtml: string, variant: TemplateHtmlVariant) => {
  const html = variant === 'skeleton' ? injectSkeletonPlaceholders(rawHtml) : rawHtml
  return `<!doctype html><html><head><meta charset="utf-8" /><style>${PREVIEW_STYLE}</style></head><body>${html || '<p class="preview-placeholder">暂无可预览内容</p>'}</body></html>`
}

const TemplateRenderPreviewDialog: FC<Props> = ({
  open,
  title,
  mode,
  content,
  htmlVariant = 'raw',
  description,
  onOpenChange,
}) => {
  const iframeDoc = useMemo(
    () => (mode === 'html' ? buildPreviewDoc(content, htmlVariant) : ''),
    [content, htmlVariant, mode],
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-[calc(100vw-32px)] overflow-hidden p-0 md:max-w-[960px]">
        <DialogHeader className="border-b border-border-subtle px-6 py-5">
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description || '以渲染后的方式查看当前内容。'}</DialogDescription>
        </DialogHeader>
        <div className="max-h-[calc(90vh-88px)] overflow-auto bg-surface-container-low p-6">
          {mode === 'html' ? (
            <iframe
              title={title}
              srcDoc={iframeDoc}
              className="h-[70vh] w-full rounded-xl border border-border-subtle bg-white"
              sandbox="allow-same-origin"
            />
          ) : (
            <div className="markdown-body rounded-xl border border-border-subtle bg-white p-6 text-[14px] text-on-surface shadow-sm">
              {content.trim() ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
              ) : (
                <div className="text-on-surface-variant">暂无 Markdown 内容</div>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default TemplateRenderPreviewDialog
