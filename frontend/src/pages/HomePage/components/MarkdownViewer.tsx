import { useState, useEffect, useRef, useMemo, memo, FC, type MouseEvent, type RefObject } from 'react'
import ReactMarkdown from 'react-markdown'
import { Button } from '@/components/ui/button.tsx'
import { Copy, ArrowRight, Play, ExternalLink, FileCode2, Blocks, FileDown, FileText } from 'lucide-react'
import { toast } from 'react-hot-toast'
import Error from '@/components/Lottie/error.tsx'
import Loading from '@/components/Lottie/Loading.tsx'
import Idle from '@/components/Lottie/Idle.tsx'
import StepBar from '@/pages/HomePage/components/StepBar.tsx'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { atomDark as codeStyle } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Zoom from 'react-medium-image-zoom'
import 'react-medium-image-zoom/dist/styles.css'
import gfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import 'github-markdown-css/github-markdown-light.css'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import { useTaskStore } from '@/store/taskStore'
import { noteStyles } from '@/constant/note.ts'
import { getRuntimeApiBaseUrl, openExternalUrl } from '@/utils/runtime'
import { MarkdownHeader, type HeaderActionItem } from '@/pages/HomePage/components/MarkdownHeader.tsx'
import TranscriptViewer from '@/pages/HomePage/components/transcriptViewer.tsx'
import MarkmapEditor from '@/pages/HomePage/components/MarkmapComponent.tsx'
import WikiViewer from '@/pages/HomePage/components/WikiViewer.tsx'
import VideoBanner from '@/pages/HomePage/components/VideoBanner.tsx'
import { getLoadingProgressCopy, getProgressSteps, type CollectorTimings } from '@/pages/HomePage/progressSteps'

interface MarkdownViewerProps {
  content: string
  status: 'idle' | 'loading' | 'success' | 'failed'
  onDeleteDocument?: () => void
  onWikiRetrySuccess?: () => void
  initialViewMode?: 'map' | 'preview' | 'wiki'
}

const remarkPlugins = [gfm, remarkMath]
const rehypePlugins = [rehypeKatex]

/**
 * 构建 ReactMarkdown components 对象，baseURL 用于修正图片路径。
 * 使用函数 + useMemo 避免每次渲染都创建新的函数实例。
 */
const extractPlainText = (children: any): string =>
  (Array.isArray(children) ? children : [children])
    .map(child => {
      if (typeof child === 'string' || typeof child === 'number') {
        return String(child)
      }

      if (child?.props?.children) {
        return extractPlainText(child.props.children)
      }

      return ''
    })
    .join('')
    .trim()

const scrollToMarkdownHeading = (
  containerRef: RefObject<HTMLDivElement | null>,
  href?: string,
) => {
  if (!href?.startsWith('#')) {
    return
  }

  const container = containerRef.current
  if (!container) {
    return
  }

  const targetText = decodeURIComponent(href.slice(1)).trim()
  if (!targetText) {
    return
  }

  const headings = Array.from(
    container.querySelectorAll<HTMLHeadingElement>('h1, h2, h3, h4, h5, h6'),
  )
  const targetHeading =
    headings.find(heading => heading.id === targetText) ||
    headings.find(heading => heading.textContent?.trim() === targetText)

  if (!targetHeading) {
    return
  }

  targetHeading.scrollIntoView({ behavior: 'smooth', block: 'start' })
  window.history.replaceState(null, '', `#${encodeURIComponent(targetText)}`)
}

const openMarkdownExternalLink = (event: MouseEvent<HTMLAnchorElement>, href?: string) => {
  if (!href?.startsWith('http')) return
  event.preventDefault()
  openExternalUrl(href).catch(error => {
    console.warn('failed to open markdown link', error)
  })
}

function createMarkdownComponents(baseURL: string, containerRef: RefObject<HTMLDivElement | null>) {
  return {
    h1: ({ children, ...props }: any) => (
      <h1
        className="text-primary my-6 scroll-m-20 break-words text-2xl font-extrabold leading-tight tracking-tight md:text-3xl xl:text-4xl"
        {...props}
      >
        {children}
      </h1>
    ),
    h2: ({ children, ...props }: any) => (
      <h2
        className="text-primary mt-10 mb-4 scroll-m-20 border-b pb-2 text-2xl font-semibold tracking-tight first:mt-0"
        {...props}
      >
        {children}
      </h2>
    ),
    h3: ({ children, ...props }: any) => (
      <h3
        className="text-primary mt-8 mb-4 scroll-m-20 text-xl font-semibold tracking-tight"
        {...props}
      >
        {children}
      </h3>
    ),
    h4: ({ children, ...props }: any) => (
      <h4
        className="text-primary mt-6 mb-2 scroll-m-20 text-lg font-semibold tracking-tight"
        {...props}
      >
        {children}
      </h4>
    ),
    p: ({ children, ...props }: any) => (
      <p className="leading-7 [&:not(:first-child)]:mt-6" {...props}>
        {children}
      </p>
    ),
    a: ({ href, children, ...props }: any) => {
      const isOriginLink =
        typeof children[0] === 'string' &&
        (children[0] as string).startsWith('原片 @')
      const isHashLink = typeof href === 'string' && href.startsWith('#')

      if (isOriginLink) {
        const timeMatch = (children[0] as string).match(/原片 @ (\d{2}:\d{2})/)
        const timeText = timeMatch ? timeMatch[1] : '原片'

        return (
          <span className="origin-link my-2 inline-flex">
            <a
              href={href}
              onClick={event => openMarkdownExternalLink(event, href)}
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100"
              {...props}
            >
              <Play className="h-3.5 w-3.5" />
              <span>原片（{timeText}）</span>
            </a>
          </span>
        )
      }

      if (isHashLink) {
        const plainText = extractPlainText(children)

        return (
          <a
            href={href}
            className="text-primary hover:text-primary/80 inline-flex items-center gap-0.5 font-medium underline underline-offset-4"
            onClick={event => {
              event.preventDefault()
              scrollToMarkdownHeading(containerRef, href)
            }}
            title={plainText}
            {...props}
          >
            {children}
          </a>
        )
      }

      return (
        <a
          href={href}
          onClick={event => openMarkdownExternalLink(event, href)}
          rel="noopener noreferrer"
          className="text-primary hover:text-primary/80 inline-flex items-center gap-0.5 font-medium underline underline-offset-4"
          {...props}
        >
          {children}
          {href?.startsWith('http') && (
            <ExternalLink className="ml-0.5 inline-block h-3 w-3" />
          )}
        </a>
      )
    },
    img: ({ node, ...props }: any) => {
      let src = props.src
      if (src.startsWith('/')) {
        src = baseURL + src
      }
      props.src = src

      return (
        <div className="my-8 flex justify-center">
          <Zoom>
            <img
              {...props}
              className="max-w-full cursor-zoom-in rounded-lg object-cover shadow-md transition-all hover:shadow-lg"
              style={{ maxHeight: '500px' }}
            />
          </Zoom>
        </div>
      )
    },
    strong: ({ children, ...props }: any) => (
      <strong className="text-primary font-bold" {...props}>
        {children}
      </strong>
    ),
    li: ({ children, ...props }: any) => {
      const rawText = String(children)
      const isFakeHeading = /^(\*\*.+\*\*)$/.test(rawText.trim())

      if (isFakeHeading) {
        return (
          <div className="text-primary my-4 text-lg font-bold">{children}</div>
        )
      }

      return (
        <li className="my-1" {...props}>
          {children}
        </li>
      )
    },
    ul: ({ children, ...props }: any) => (
      <ul className="my-6 ml-6 list-disc [&>li]:mt-2" {...props}>
        {children}
      </ul>
    ),
    ol: ({ children, ...props }: any) => (
      <ol className="my-6 ml-6 list-decimal [&>li]:mt-2" {...props}>
        {children}
      </ol>
    ),
    blockquote: ({ children, ...props }: any) => (
      <blockquote
        className="border-primary/20 text-muted-foreground mt-6 border-l-4 pl-4 italic"
        {...props}
      >
        {children}
      </blockquote>
    ),
    code: ({ inline, className, children, ...props }: any) => {
      const match = /language-(\w+)/.exec(className || '')
      const codeContent = String(children).replace(/\n$/, '')

      if (!inline && match) {
        return (
          <div className="group bg-muted relative my-6 overflow-hidden rounded-lg border shadow-sm">
            <div className="bg-muted text-muted-foreground flex items-center justify-between px-4 py-1.5 text-sm font-medium">
              <div>{match[1].toUpperCase()}</div>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(codeContent)
                  toast.success('代码已复制')
                }}
                className="bg-background/80 hover:bg-background flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors"
              >
                <Copy className="h-3.5 w-3.5" />
                复制
              </button>
            </div>
            <SyntaxHighlighter
              style={codeStyle}
              language={match[1]}
              PreTag="div"
              className="!bg-muted !m-0 !p-0"
              customStyle={{
                margin: 0,
                padding: '1rem',
                background: 'transparent',
                fontSize: '0.9rem',
              }}
              {...props}
            >
              {codeContent}
            </SyntaxHighlighter>
          </div>
        )
      }

      return (
        <code
          className="bg-muted relative rounded px-[0.3rem] py-[0.2rem] font-mono text-sm"
          {...props}
        >
          {children}
        </code>
      )
    },
    table: ({ children, ...props }: any) => (
      <div className="my-6 w-full overflow-y-auto">
        <table className="w-full border-collapse text-sm" {...props}>
          {children}
        </table>
      </div>
    ),
    th: ({ children, ...props }: any) => (
      <th
        className="border-muted-foreground/20 border px-4 py-2 text-left font-medium [&[align=center]]:text-center [&[align=right]]:text-right"
        {...props}
      >
        {children}
      </th>
    ),
    td: ({ children, ...props }: any) => (
      <td
        className="border-muted-foreground/20 border px-4 py-2 text-left [&[align=center]]:text-center [&[align=right]]:text-right"
        {...props}
      >
        {children}
      </td>
    ),
    hr: ({ ...props }: any) => (
      <hr className="border-muted-foreground/20 my-8" {...props} />
    ),
  }
}

const MarkdownViewer: FC<MarkdownViewerProps> = memo(({
  status,
  onDeleteDocument,
  onWikiRetrySuccess,
  initialViewMode = 'preview',
}) => {
  const [currentVerId, setCurrentVerId] = useState<string>('')
  const [selectedContent, setSelectedContent] = useState<string>('')
  const [modelName, setModelName] = useState<string>('')
  const [style, setStyle] = useState<string>('')
  const [createTime, setCreateTime] = useState<string>('')
  // 确保baseURL没有尾部斜杠
  const baseURL = (
    String(getRuntimeApiBaseUrl() || import.meta.env.VITE_API_BASE_URL || '').replace('/api', '') || ''
  ).replace(/\/$/, '')
  const currentTask = useTaskStore(state => state.getCurrentTask())
  const selectNoteDocument = useTaskStore(state => state.selectNoteDocument)
  const taskStatus = currentTask?.status || 'PENDING'
  const taskPlatform = currentTask?.platform || currentTask?.formData?.platform
  const steps = getProgressSteps(taskPlatform)
  const retryTask = useTaskStore.getState().retryTask
  const isMultiVersion = false
  const [showTranscribe, setShowTranscribe] = useState(false)
  const [viewMode, setViewMode] = useState<'map' | 'preview' | 'wiki'>(initialViewMode)
  const markdownContainerRef = useRef<HTMLDivElement>(null)

  // 缓存 ReactMarkdown components，仅在 baseURL 变化时重建
  const markdownComponents = useMemo(
    () => createMarkdownComponents(baseURL, markdownContainerRef),
    [baseURL],
  )

  useEffect(() => {
    if (!currentTask) return
    setCurrentVerId('')
    const activeDocument = (currentTask.documents || []).find(
      document => document.taskId === currentTask.activeDocumentTaskId,
    )
    setModelName(activeDocument?.modelName || currentTask.formData.model_name)
    setStyle(activeDocument?.style || currentTask.formData.style || '')
    setCreateTime(currentTask.createdAt)
    setSelectedContent(activeDocument?.content || currentTask.markdown || '')
  }, [
    currentTask?.id,
    currentTask?.markdown,
    currentTask?.activeDocumentTaskId,
    currentTask?.documents,
    taskStatus,
  ])

  useEffect(() => {
    setViewMode(initialViewMode)
  }, [initialViewMode, currentTask?.id, currentTask?.activeDocumentTaskId])

  const handleSelectDocument = (taskId: string) => {
    if (!currentTask?.id || !taskId) return
    selectNoteDocument(currentTask.id, taskId)
  }

  const activeDocument = (currentTask?.documents || []).find(
    document => document.taskId === currentTask?.activeDocumentTaskId,
  )
  const currentDocumentTaskId = activeDocument?.taskId || currentTask?.activeDocumentTaskId || currentTask?.id || ''
  const currentDocumentTitle =
    activeDocument?.title || currentTask?.audioMeta?.title || currentTask?.title || '未命名笔记'
  const transcriptText = currentTask?.transcript?.full_text?.trim() || ''
  const currentProgressMessage = (currentTask?.messages || []).find(message => {
    if (message.message_type !== 'note_progress') return false
    const messageTaskId = typeof message.meta?.task_id === 'string' ? message.meta.task_id : ''
    return !messageTaskId || messageTaskId === currentDocumentTaskId
  })
  const collectorTimings = currentProgressMessage?.meta?.collector_timings as CollectorTimings | undefined
  const loadingProgressCopy = getLoadingProgressCopy(collectorTimings)

  const downloadBlob = (blob: Blob, filename: string) => {
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(link.href)
  }

  const handleCopyMarkdown = async () => {
    try {
      await navigator.clipboard.writeText(selectedContent)
      toast.success('已复制到剪贴板')
    } catch {
      toast.error('复制失败')
    }
  }

  const handleCopyMcp = async () => {
    const safeTitle = currentDocumentTitle.replace(/"/g, '“')
    const prompt = `用 NoteMeld MCP 的 notemeld_search_notes 搜索标题“${safeTitle}”，再用 notemeld_read_note 读取 taskId“${currentDocumentTaskId}”对应的全文。`

    try {
      await navigator.clipboard.writeText(prompt)
      toast.success('MCP 引用已复制')
    } catch {
      toast.error('复制失败')
    }
  }

  const handleDownloadMarkdown = () => {
    const blob = new Blob([selectedContent], { type: 'text/markdown;charset=utf-8' })
    downloadBlob(blob, `${currentDocumentTitle}.md`)
  }

  const handleDownloadTranscriptComparison = () => {
    if (!transcriptText) return

    const content = [
      `标题：${currentDocumentTitle}`,
      `Task ID：${currentDocumentTaskId}`,
      '',
      '【原文 / 转写】',
      transcriptText,
      '',
      '------------------------------',
      '',
      '【笔记 Markdown】',
      selectedContent,
    ].join('\n')

    downloadBlob(new Blob([content], { type: 'text/plain;charset=utf-8' }), `${currentDocumentTitle}-原文对照.txt`)
  }

  const copyActions: HeaderActionItem[] = [
    { key: 'copy-md', label: '复制 MD', onSelect: handleCopyMarkdown, icon: FileCode2 },
    { key: 'copy-mcp', label: '复制 MCP', onSelect: handleCopyMcp, icon: Blocks },
  ]

  const exportActions: HeaderActionItem[] = [
    { key: 'export-md', label: 'Markdown', onSelect: handleDownloadMarkdown, icon: FileDown },
    ...(transcriptText
      ? [{ key: 'export-transcript', label: '原文对照', onSelect: handleDownloadTranscriptComparison, icon: FileText }]
      : []),
  ]

  if (status === 'loading') {
    return (
      <div className="flex h-full min-h-0 w-full flex-col items-center justify-center space-y-4 px-4 text-neutral-500">
        <StepBar steps={steps} currentStep={taskStatus} collectorTimings={collectorTimings} />
        <Loading className="h-5 w-5" />
        <div className="text-center text-sm">
          <p className="text-lg font-bold">{loadingProgressCopy.title}</p>
          <p className="mt-2 text-xs text-neutral-500">{loadingProgressCopy.description}</p>
        </div>
      </div>
    )
  }

  if (status === 'idle') {
    return (
      <div className="flex h-full min-h-0 w-full flex-col items-center justify-center space-y-3 px-4 text-neutral-500">
        <Idle />
        <div className="text-center">
          <p className="text-lg font-bold">输入视频链接并点击"生成笔记"</p>
          <p className="mt-2 text-xs text-neutral-500">支持哔哩哔哩、YouTube 、抖音等视频平台</p>
        </div>
      </div>
    )
  }

  if (status === 'failed' && !isMultiVersion) {
    return (
      <div className="flex h-full min-h-0 w-full flex-col items-center justify-center gap-4 space-y-3 px-4">
        <Error />
        <div className="text-center">
          <p className="text-lg font-bold text-red-500">笔记生成失败</p>
          <p className="mt-2 mb-2 text-xs text-red-400">
            模型服务超时，请减少视频理解或切换模型
          </p>

          <Button
            onClick={() => {
              if (!currentTask?.id) return
              retryTask(
                currentTask.id,
                undefined,
                currentTask.activeDocumentTaskId || currentTask.linkedNoteTaskId || currentTask.id,
              )
            }}
            size="lg"
          >
            重试
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
      <MarkdownHeader
        currentTask={currentTask || undefined}
        isMultiVersion={isMultiVersion}
        currentVerId={currentVerId}
        setCurrentVerId={setCurrentVerId}
        modelName={modelName}
        style={style}
        noteStyles={noteStyles}
        copyActions={copyActions}
        exportActions={exportActions}
        onDeleteDocument={currentTask?.activeDocumentTaskId ? onDeleteDocument : undefined}
        documents={currentTask?.documents || []}
        activeDocumentTaskId={currentTask?.activeDocumentTaskId}
        onSelectDocument={handleSelectDocument}
        createAt={createTime}
        showTranscribe={showTranscribe}
        setShowTranscribe={setShowTranscribe}
        viewMode={viewMode}
        setViewMode={setViewMode}
      />

      {viewMode === 'map' ? (
        <div className="flex w-full flex-1 overflow-hidden bg-white">
          <div className={'w-full'}>
            <MarkmapEditor
              value={selectedContent}
              onChange={() => {}}
              height="100%" // 根据需求可以设定百分比或固定高度
              title={currentTask?.audioMeta?.title || '思维导图'}
            />
          </div>
        </div>
      ) : viewMode === 'wiki' ? (
        <div className="flex h-full w-full flex-col overflow-hidden bg-white">
          <WikiViewer
            taskId={currentTask?.activeDocumentTaskId || ''}
            wikiStatus={currentTask?.documents?.find(document => document.taskId === currentTask?.activeDocumentTaskId)?.wikiStatus || 'pending'}
            onRetrySuccess={onWikiRetrySuccess}
          />
        </div>
      ) : (
        <div className="flex flex-1 overflow-hidden bg-white px-4 py-4 md:px-5 md:py-5">
          {selectedContent && selectedContent !== 'loading' && selectedContent !== 'empty' ? (
            <>
              <ScrollArea className="min-w-0 flex-1">
                <div className="min-w-0 px-1">
                  <VideoBanner
                    audioMeta={currentTask?.audioMeta}
                    videoUrl={currentTask?.formData?.video_url}
                  />
                </div>
                <div ref={markdownContainerRef} className="markdown-body min-w-0 w-full px-1 pb-10">
                  <ReactMarkdown
                    remarkPlugins={remarkPlugins}
                    rehypePlugins={rehypePlugins}
                    components={markdownComponents}
                  >
                    {selectedContent.replace(/^>\s*来源链接：[^\n]*\n*/m, '')}
                  </ReactMarkdown>
                </div>
              </ScrollArea>
              {showTranscribe && (
                <div className="hidden border-l border-border-subtle pl-2 md:block md:w-2/4">
                  <TranscriptViewer />
                </div>
              )}
            </>
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <div className="w-[300px] flex-col justify-items-center">
                <div className="bg-primary-light mb-4 flex h-16 w-16 items-center justify-center rounded-full">
                  <ArrowRight className="text-primary h-8 w-8" />
                </div>
                <p className="mb-2 text-neutral-600">输入视频链接并点击"生成笔记"按钮</p>
                <p className="text-xs text-neutral-500">支持哔哩哔哩、YouTube等视频网站</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
})

MarkdownViewer.displayName = 'MarkdownViewer'

export default MarkdownViewer
