import { type FC } from 'react'
import { AlertCircle, Bot, CheckCircle2, Copy, Loader2, RotateCcw, User } from 'lucide-react'
import { toast } from 'sonner'
import ChatMarkdown from '@/pages/HomePage/components/ChatMarkdown'
import { parseMessageContent } from '@/pages/HomePage/conversationHelpers'
import { getCollectorSubStatuses, getProgressSteps, getStepIndex, type CollectorTimings } from '@/pages/HomePage/progressSteps'
import PlatformLinkCard from '@/pages/HomePage/components/PlatformLinkCard'
import { cn } from '@/lib/utils'
import type { ConversationMessage, ConversationSource, TaskStatus } from '@/store/taskStore'

interface ConversationMessageRendererProps {
  message: ConversationMessage
  compact?: boolean
  taskPlatform?: string
  onRetry?: (taskId?: string) => void
  onRetryChat?: () => void
  onSelectNoteResult?: (taskId: string) => void
}

const getUserInputParts = (message: ConversationMessage) => {
  const parsed = parseMessageContent(message.content)
  const metaUrl = typeof message.meta?.url === 'string' ? message.meta.url : ''
  const metaExtras = typeof message.meta?.extras === 'string' ? message.meta.extras : ''

  return {
    url: metaUrl || parsed.url,
    text: metaExtras || parsed.text,
  }
}

const formatDuration = (durationMs: unknown): string => {
  if (typeof durationMs !== 'number' || !Number.isFinite(durationMs) || durationMs < 0) return ''
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`
  const seconds = durationMs / 1000
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  const minutes = Math.floor(seconds / 60)
  const restSeconds = Math.round(seconds % 60)
  return `${minutes}m${restSeconds}s`
}

const normalizeNoteFailureDetail = (detail?: string): string => {
  const raw = String(detail || '').trim()
  const lower = raw.toLowerCase()
  const looksLikeHtml = /<\s*html|<\s*body|<\s*h1/.test(lower)

  if (
    (lower.includes('504') ||
      lower.includes('gateway time-out') ||
      lower.includes('gateway timeout') ||
      lower.includes('timeout') ||
      lower.includes('timed out')) &&
    (looksLikeHtml || lower.includes('gateway') || lower.includes('timeout'))
  ) {
    return '模型服务超时，请减少视频理解或切换模型'
  }

  if (
    lower.includes('413') ||
    lower.includes('request body exceeds') ||
    lower.includes('request_too_large') ||
    lower.includes('payload too large') ||
    lower.includes('limit_bytes')
  ) {
    return '模型请求内容过大，请减少视频理解或切换模型'
  }

  if (looksLikeHtml) {
    return '模型服务返回异常，请稍后重试或切换模型'
  }

  return raw
}

const formatTokenCount = (value: unknown): string => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return ''
  return new Intl.NumberFormat('zh-CN').format(Math.round(value))
}

const sourceTypeLabelMap: Record<string, string> = {
  note_meta: '视频信息',
  note_markdown: '当前笔记',
  note_transcript: '字幕片段',
  wiki_entity: 'Wiki 实体',
  wiki_concept: 'Wiki 概念',
  wiki_claim: 'Wiki 观点',
  wiki_evidence: 'Wiki 证据',
  wiki_relation: 'Wiki 关系',
  meta: '视频信息',
  markdown: '当前笔记',
  transcript: '字幕片段',
  wiki: 'Wiki 来源',
}

export const getSourceTypeLabel = (type?: string) =>
  type ? sourceTypeLabelMap[type] || '参考来源' : '参考来源'

const formatSourceLabel = (source: ConversationSource) => {
  const type = source.type || source.source_type
  const label = getSourceTypeLabel(type)
  const title = source.title || source.section_title || source.page_id || ''
  return title && title !== label ? `${label}：${title}` : label
}

const AssistantTextBubble: FC<ConversationMessageRendererProps> = ({
  message,
  onRetryChat,
}) => {
  const isUser = message.role === 'user'
  const parsed = isUser ? getUserInputParts(message) : { url: '', text: message.content }
  const showStreamingLoader = !isUser && !message.error && message.isStreaming && !parsed.text
  const assistantStreamingText =
    !isUser && !message.error && message.isStreaming && parsed.text
      ? `${parsed.text}...`
      : parsed.text

  return (
    <div className={cn('flex w-full min-w-0 items-start gap-2 md:gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary md:flex">
          <Bot className="h-4 w-4" />
        </div>
      )}
      <div
        className={cn(
          'min-w-0 max-w-[calc(100vw-56px)] overflow-hidden rounded-xl px-3 py-2 text-[13px] leading-relaxed shadow-[0_2px_8px_rgba(15,23,42,0.05)] md:max-w-[620px]',
          isUser
            ? 'rounded-tr-sm bg-primary text-white'
            : message.error
            ? 'rounded-tl-sm border border-destructive/20 bg-destructive/5 text-destructive'
            : 'rounded-tl-sm border border-border-subtle bg-white text-on-surface',
        )}
      >
        {isUser && parsed.url && (
          <PlatformLinkCard
            url={parsed.url}
            tone="primary"
            className="mb-2 max-w-full"
          />
        )}
        {showStreamingLoader && (
          <div className="inline-flex items-center gap-0.5 text-[14px] leading-none text-on-surface-variant/70">
            <span className="animate-pulse [animation-delay:0ms]">.</span>
            <span className="animate-pulse [animation-delay:150ms]">.</span>
            <span className="animate-pulse [animation-delay:300ms]">.</span>
          </div>
        )}
        {assistantStreamingText && (
          isUser ? (
            <div className="min-w-0 whitespace-pre-wrap break-words">{assistantStreamingText}</div>
          ) : message.error ? (
            <div className="min-w-0 whitespace-pre-wrap break-words">{assistantStreamingText}</div>
          ) : (
            <ChatMarkdown content={assistantStreamingText} />
          )
        )}
        {!isUser && message.error && onRetryChat && (
          <button
            onClick={onRetryChat}
            type="button"
            title="重试"
            aria-label="重试"
            className="mt-3 inline-flex h-7 w-7 items-center justify-center rounded-md border border-border-subtle bg-white text-primary transition-colors hover:border-primary hover:bg-primary-light"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        )}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-2 border-t border-border-subtle/70 pt-2 text-[11px] text-on-surface-variant">
            来源：
            {message.sources
              .slice(0, 3)
              .map(source => formatSourceLabel(source))
              .join('、')}
          </div>
        )}
      </div>
      {isUser && (
        <div className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-full bg-on-surface text-white md:flex">
          <User className="h-4 w-4" />
        </div>
      )}
    </div>
  )
}

const NoteProgressBubble: FC<ConversationMessageRendererProps> = ({
  message,
  compact,
  taskPlatform,
  onRetry,
}) => {
  const fallbackSteps = getProgressSteps(taskPlatform)
  const rawSteps = Array.isArray(message.meta?.steps) && message.meta.steps.length > 0
    ? message.meta.steps.map(step => String(step))
    : fallbackSteps.map(step => String(step.matches[0] || step.label))
  const visibleSteps = rawSteps.filter(step =>
    fallbackSteps.some(item => item.matches.includes(step as TaskStatus)),
  )
  const currentStep = typeof message.meta?.current_step === 'string' ? message.meta.current_step : ''
  const currentStepIdx = currentStep
    ? visibleSteps.findIndex(step => step === currentStep)
    : getStepIndex((message.status || 'PENDING').toUpperCase() as TaskStatus, taskPlatform)
  const detail = normalizeNoteFailureDetail(
    typeof message.meta?.detail === 'string' ? message.meta.detail : message.content,
  )
  const failed = message.status === 'failed'
  const success = message.status === 'success'
  const retryTaskId = typeof message.meta?.task_id === 'string' ? message.meta.task_id : undefined
  const stageTimings = message.meta?.stage_timings
  const collectorSubStatuses = getCollectorSubStatuses(message.meta?.collector_timings as CollectorTimings | undefined)
  const handleCopyLogId = async () => {
    if (!retryTaskId) return
    try {
      await navigator.clipboard.writeText(retryTaskId)
      toast.success(`${retryTaskId} 复制成功`)
    } catch {
      toast.error('复制日志 ID 失败')
    }
  }

  return (
    <div className="flex w-full min-w-0 items-start gap-2 md:gap-3">
      <div className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary md:flex">
        <Bot className="h-4 w-4" />
      </div>
      <div
        className={cn(
          'min-w-0 flex-1 overflow-hidden rounded-xl rounded-tl-sm border border-border-subtle bg-white px-4 py-3 shadow-[0_2px_12px_rgba(15,23,42,0.04)]',
          compact ? 'max-w-full' : 'max-w-[600px]',
        )}
      >
        {failed ? (
          <div className="flex items-start gap-3">
            <div className="flex flex-1 items-start gap-2 text-destructive">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="text-[13px] leading-relaxed">
                <div className="font-medium">笔记生成失败</div>
                {detail && <div className="mt-1 text-on-surface-variant">{normalizeNoteFailureDetail(detail)}</div>}
              </div>
            </div>
            {onRetry && (
              <button
                onClick={() => onRetry?.(retryTaskId)}
                type="button"
                title="重试"
                aria-label="重试"
                className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border-subtle bg-white text-primary transition-colors hover:border-primary hover:bg-primary-light"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="mb-3 flex items-center gap-2 text-[13px] font-medium text-on-surface">
              <span>{success ? '笔记生成完成' : '正在为你生成笔记'}</span>
              {retryTaskId && (
                <button
                  type="button"
                  onClick={handleCopyLogId}
                  title="复制日志 ID"
                  aria-label="复制日志 ID"
                  className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-on-surface-variant transition-colors hover:bg-surface-container hover:text-primary"
                >
                  <Copy className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            <ol className="space-y-2.5">
              {visibleSteps.map((step, idx) => {
                const stepLabel =
                  fallbackSteps.find(item => item.matches.includes(step as TaskStatus))?.label || step
                const isDone = success || idx < currentStepIdx
                const isActive = !success && idx === currentStepIdx
                const stageTiming = typeof stageTimings === 'object' && stageTimings
                  ? (stageTimings as Record<string, any>)[step]
                  : undefined
                const timingLabel = formatDuration(stageTiming?.duration_ms)
                return (
                  <li key={`${message.id}-${step}`} className="flex items-center gap-2.5">
                    <span
                      className={cn(
                        'flex h-5 w-5 shrink-0 items-center justify-center rounded-full',
                        isDone
                          ? 'bg-status-success text-white'
                          : isActive
                          ? 'bg-primary-light text-primary'
                          : 'bg-surface-container text-on-surface-variant/60',
                      )}
                    >
                      {isDone ? (
                        <CheckCircle2 className="h-3.5 w-3.5" />
                      ) : isActive ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <span className="text-[10px] font-mono">{idx + 1}</span>
                      )}
                    </span>
                    <span
                      className={cn(
                        'text-[13px]',
                        isDone
                          ? 'text-on-surface'
                          : isActive
                          ? 'font-medium text-primary'
                          : 'text-on-surface-variant/60',
                      )}
                    >
                      {stepLabel}
                    </span>
                    {(isActive && detail) || timingLabel ? (
                      <span className="ml-auto flex min-w-0 items-center gap-2">
                        {isActive && detail && (
                          <span className="truncate text-[11px] text-on-surface-variant/70">
                            {detail}
                          </span>
                        )}
                        {timingLabel && (
                          <span className="shrink-0 rounded-full bg-surface-container px-1.5 py-0.5 font-mono text-[10px] text-on-surface-variant">
                            {timingLabel}
                          </span>
                        )}
                      </span>
                    ) : null}
                  </li>
                )
              })}
            </ol>
            {collectorSubStatuses.length > 0 && (
              <div className="mt-3 rounded-lg bg-surface-container/60 px-3 py-2">
                <div className="mb-2 text-[11px] font-medium text-on-surface-variant">并行采集素材</div>
                <div className="space-y-1.5">
                  {collectorSubStatuses.map(item => {
                    const running = item.state === 'running'
                    const done = item.state === 'done'
                    const failed = item.state === 'failed'
                    return (
                      <div key={`${message.id}-${item.key}`} className="flex min-w-0 items-center gap-2 text-[12px]">
                        <span
                          className={cn(
                            'h-2 w-2 shrink-0 rounded-full',
                            done
                              ? 'bg-status-success'
                              : failed
                              ? 'bg-destructive'
                              : running
                              ? 'animate-pulse bg-primary'
                              : 'bg-on-surface-variant/30',
                          )}
                        />
                        <span className="shrink-0 font-medium text-on-surface">{item.label}</span>
                        {item.detail && (
                          <span className="truncate text-on-surface-variant/70">{item.detail}</span>
                        )}
                        {item.timingLabel && (
                          <span className="ml-auto shrink-0 rounded-full bg-white px-1.5 py-0.5 font-mono text-[10px] text-on-surface-variant">
                            {item.timingLabel}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

const NoteResultBubble: FC<ConversationMessageRendererProps> = ({ message, compact, onSelectNoteResult }) => {
  const title = typeof message.meta?.title === 'string' ? message.meta.title : message.content
  const sourceUrl = typeof message.meta?.source_url === 'string' ? message.meta.source_url : ''
  const taskId = typeof message.meta?.task_id === 'string' ? message.meta.task_id : ''
  const importKind = typeof message.meta?.import_kind === 'string' ? message.meta.import_kind : ''
  const isImportedNote = importKind === 'imported_note'
  const detail =
    !isImportedNote && message.content && message.content !== title ? message.content : ''
  const totalDurationLabel = formatDuration(message.meta?.total_duration_ms)
  const totalTokensLabel = formatTokenCount(message.meta?.total_tokens)

  return (
    <div className="flex w-full min-w-0 items-start gap-2 md:gap-3">
      <div className="hidden h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary md:flex">
        <Bot className="h-4 w-4" />
      </div>
      <div
        className={cn(
          'min-w-0 flex-1 overflow-hidden rounded-xl rounded-tl-sm border border-status-success/20 bg-status-success/5 px-4 py-3 shadow-[0_2px_12px_rgba(15,23,42,0.04)]',
          compact ? 'max-w-full' : 'max-w-[600px]',
        )}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="text-[13px] font-medium text-on-surface">
            {isImportedNote ? '笔记已导入' : '笔记已生成'}
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            {totalDurationLabel && (
              <div className="rounded-full bg-white px-2 py-1 font-mono text-[11px] text-on-surface-variant">
                总耗时 {totalDurationLabel}
              </div>
            )}
            {totalTokensLabel && (
              <div className="rounded-full bg-white px-2 py-1 font-mono text-[11px] text-on-surface-variant">
                Token {totalTokensLabel}
              </div>
            )}
          </div>
        </div>
        {title && <div className="mt-1 break-words text-[14px] font-semibold text-on-surface">{title}</div>}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {taskId && onSelectNoteResult && (
            <button
              type="button"
              onClick={() => onSelectNoteResult(taskId)}
              className="inline-flex rounded-lg border border-primary/20 bg-white px-2.5 py-1.5 text-[12px] font-medium text-primary transition-colors hover:bg-primary-light"
            >
              {isImportedNote ? '查看导入笔记' : '查看这篇笔记'}
            </button>
          )}
          {!isImportedNote && sourceUrl && (
            <PlatformLinkCard url={sourceUrl} />
          )}
        </div>
        {detail && (
          <div className="mt-3 rounded-lg border border-border-subtle/60 bg-white px-3 py-2">
            <ChatMarkdown content={detail} />
          </div>
        )}
      </div>
    </div>
  )
}

export const ConversationMessageRenderer: FC<ConversationMessageRendererProps> = props => {
  const { message } = props

  if (message.message_type === 'note_progress') {
    return <NoteProgressBubble {...props} />
  }

  if (message.message_type === 'note_result') {
    return <NoteResultBubble {...props} />
  }

  return <AssistantTextBubble {...props} />
}
