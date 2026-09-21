import { FC, useEffect, useMemo, useRef, useState } from 'react'
import {
  Check,
  ChevronDown,
  ChevronUp,
  Loader2,
  Paperclip,
  RotateCcw,
  Send,
  Trash2,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { NoteStylePayload, StyleExtractionTask } from '@/services/noteStyle'
import { useModelStore } from '@/store/modelStore'
import { useProviderStore } from '@/store/providerStore'

export interface StyleImportSubmitPayload {
  file: File | null
  instruction: string
  provider_id: string
  model_name: string
}

export interface StyleImportDraft {
  instruction: string
  file: File | null
  model_name: string
  provider_id: string
}

export type StyleImportConversationItem =
  | {
      id: string
      type: 'user'
      requestId: string
      content: string
      fileName?: string
      modelName?: string
      providerId?: string
      createdAt: number
    }
  | {
      id: string
      type: 'task'
      requestId: string
      task: StyleExtractionTask
    }

interface Props {
  leftPanelWidth?: number
  conversation?: StyleImportConversationItem[]
  draft: StyleImportDraft
  submitting?: boolean
  onDraftChange: (draft: StyleImportDraft) => void
  onSubmit: (payload: StyleImportSubmitPayload) => void
  onRetry: (taskId: string) => void
  onCancelTask: (taskId: string) => void
  onRestoreDraft: (requestId: string) => void
  onUsePrompt: (prompt: string) => void
  onViewVersion: (version: NoteStylePayload) => void
}

const StyleImportChat: FC<Props> = ({
  leftPanelWidth,
  conversation = [],
  draft,
  submitting,
  onDraftChange,
  onSubmit,
  onRetry,
  onCancelTask,
  onRestoreDraft,
  onUsePrompt,
  onViewVersion,
}) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const modelRef = useRef<HTMLDivElement | null>(null)
  const [expandedRequests, setExpandedRequests] = useState<Record<string, boolean>>({})
  const [modelOpen, setModelOpen] = useState(false)
  const providerList = useProviderStore(state => state.provider)
  const fetchProviderList = useProviderStore(state => state.fetchProviderList)
  const modelList = useModelStore(state => state.modelList)
  const loadEnabledModels = useModelStore(state => state.loadEnabledModels)

  useEffect(() => {
    fetchProviderList()
    loadEnabledModels()
  }, [fetchProviderList, loadEnabledModels])

  useEffect(() => {
    if (!draft.model_name && modelList.length > 0) {
      onDraftChange({
        ...draft,
        model_name: modelList[0].model_name,
        provider_id: modelList[0].provider_id || '',
      })
    }
  }, [draft, modelList, onDraftChange])

  useEffect(() => {
    if (!draft.file && fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }, [draft.file])

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (modelRef.current && !modelRef.current.contains(event.target as Node)) {
        setModelOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const selectedModel = useMemo(
    () => modelList.find(item => item.model_name === draft.model_name),
    [draft.model_name, modelList],
  )
  const canSubmit = !!draft.instruction.trim() || !!draft.file
  const hasConversation = conversation.length > 0
  const groupedModels = useMemo(() => {
    const groups = new Map<string, typeof modelList>()
    modelList.forEach(model => {
      const list = groups.get(model.provider_id) || []
      list.push(model)
      groups.set(model.provider_id, list)
    })
    return Array.from(groups.entries()).map(([providerId, items]) => ({
      providerId,
      providerName: providerList.find(provider => provider.id === providerId)?.name || '未知来源',
      items,
    }))
  }, [modelList, providerList])

  const groupedConversation = useMemo(() => {
    const grouped = new Map<
      string,
      {
        requestId: string
        createdAt: number
        user?: Extract<StyleImportConversationItem, { type: 'user' }>
        task?: Extract<StyleImportConversationItem, { type: 'task' }>
      }
    >()

    conversation.forEach(item => {
      const current = grouped.get(item.requestId) || {
        requestId: item.requestId,
        createdAt: item.type === 'user' ? item.createdAt : item.task.created_at,
      }
      if (item.type === 'user') {
        current.user = item
        current.createdAt = item.createdAt
      } else {
        current.task = item
        current.createdAt = current.createdAt || item.task.created_at
      }
      grouped.set(item.requestId, current)
    })

    return Array.from(grouped.values()).sort((a, b) => a.createdAt - b.createdAt)
  }, [conversation])

  const toggleExpanded = (requestId: string) => {
    setExpandedRequests(prev => ({
      ...prev,
      [requestId]: !prev[requestId],
    }))
  }

  const renderAnalysisSummary = (
    analysisSummary: StyleExtractionTask['analysis_summary'],
    compact = false,
  ) => {
    if (!analysisSummary?.replication_score) return null
    return (
      <div
        className={cn(
          'rounded-lg border border-border-subtle bg-surface-container-low px-2.5 py-2 text-on-surface',
          compact ? 'text-[11px]' : 'text-[12px]',
        )}
      >
        <div className="font-medium">
          整体复刻度 {analysisSummary.replication_score.overall_score}/100
          {analysisSummary.replication_score.grade ? ` · ${analysisSummary.replication_score.grade}` : ''}
        </div>
        <div className="mt-1 text-[11px] text-on-surface-variant">
          路径 {analysisSummary.router?.strategy || 'unknown'} · 复杂度{' '}
          {analysisSummary.router?.complexity_level || 'unknown'}
        </div>
      </div>
    )
  }

  const renderTaskContent = (entry: Extract<StyleImportConversationItem, { type: 'task' }>) => {
    const item = entry.task
    const userMessage = item.user_message || null
    const displayFileName = userMessage?.file_name || item.file_name
    const displayModel = userMessage?.model_name || item.model_name || draft.model_name
    const itemProviderName = providerList.find(provider => provider.id === (userMessage?.provider_id || item.provider_id))?.name
    const itemProgress = typeof item.progress === 'number' ? item.progress : 0
    const canCancel =
      item.status === 'pending' || item.status === 'running' || item.status === 'retrying'
    const analysisSummary = item.analysis_summary || item.request_payload?.analysis_summary

    return (
      <div className="space-y-2 px-3 py-3">
        <div className="flex items-center justify-between">
          <div className="text-[12px] font-medium text-on-surface">任务状态</div>
          <div className="text-[11px] text-on-surface-variant">
            {item.stage || item.status} · {itemProgress}%
          </div>
        </div>
        {(displayFileName || displayModel) && (
          <div className="text-[11px] text-on-surface-variant">
            {displayFileName ? `${displayFileName} · ` : ''}
            {itemProviderName ? `${itemProviderName} / ` : ''}
            {displayModel || '未选择模型'}
          </div>
        )}
        <div className="h-1.5 overflow-hidden rounded-full bg-surface-container">
          <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${itemProgress}%` }} />
        </div>
        {renderAnalysisSummary(analysisSummary)}
        {(item.messages || []).map((message, index) => (
          <div key={index} className="rounded-lg bg-surface-container-low px-2.5 py-2 text-[12px] text-on-surface">
            {message}
          </div>
        ))}
        {item.error && (
          <div className="rounded-lg bg-destructive/10 px-2.5 py-2 text-[12px] text-destructive">
            {item.error}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          {item.status === 'succeeded' && item.result && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 gap-1.5 border-border-subtle text-[12px]"
              onClick={() => onViewVersion(item.result!)}
            >
              查看内容
            </Button>
          )}
          {item.status === 'failed' && (
            <>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 gap-1.5 border-border-subtle text-[12px]"
                onClick={() => onRetry(item.task_id)}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                重试
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-8 gap-1.5 px-0 text-[12px] text-on-surface-variant hover:bg-transparent hover:text-on-surface"
                onClick={() => onRestoreDraft(entry.requestId)}
              >
                恢复本次草稿
              </Button>
            </>
          )}
          {canCancel && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-8 gap-1.5 px-0 text-[12px] text-on-surface-variant hover:bg-transparent hover:text-destructive"
              onClick={() => onCancelTask(item.task_id)}
            >
              <Trash2 className="h-3.5 w-3.5" />
              取消任务
            </Button>
          )}
        </div>
        {!!analysisSummary?.recommended_followup_prompts?.length && (
          <div className="flex flex-wrap gap-2">
            {analysisSummary.recommended_followup_prompts.map(item => (
              <button
                key={item.label}
                type="button"
                className="rounded-full border border-border-subtle bg-white px-2.5 py-1 text-[11px] text-on-surface-variant transition-colors hover:border-primary/30 hover:text-primary"
                onClick={() => onUsePrompt(item.prompt)}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
        {item.status === 'canceled' && (
          <div className="rounded-lg bg-surface-container-low px-2.5 py-2 text-[12px] text-on-surface-variant">
            任务已结束，本次临时会话不会在下次打开时恢复。
          </div>
        )}
      </div>
    )
  }

  return (
    <aside
      className="flex h-full min-w-0 shrink-0 flex-col border-r border-border-subtle bg-surface-container/50"
      style={
        leftPanelWidth
          ? {
              width: `${leftPanelWidth}px`,
              minWidth: `${leftPanelWidth}px`,
              maxWidth: `${leftPanelWidth}px`,
            }
          : undefined
      }
    >
      <div className="border-b border-border-subtle p-4">
        <h3 className="font-display text-[15px] font-semibold text-on-surface">模板导入助手</h3>
        <p className="mt-1 text-[12px] leading-relaxed text-on-surface-variant">
          当前仅展示本次弹窗内的临时对话。关闭后不会恢复之前的消息或任务卡片。
        </p>
      </div>

      <div className="flex-1 overflow-auto p-4">
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="text-[12px] font-medium text-on-surface">本次临时会话</div>
            {!hasConversation ? (
              <div className="rounded-2xl border border-dashed border-border-subtle bg-white px-4 py-5 text-[12px] leading-relaxed text-on-surface-variant">
                当前弹窗还没有新的临时会话。发送一条说明或上传一个文件后，这里会展示本次合并卡片和任务状态。
              </div>
            ) : (
              <div className="space-y-3">
            {groupedConversation.map(entry => {
              const user = entry.user
              const task = entry.task
              const providerName = user?.providerId
                ? providerList.find(provider => provider.id === user.providerId)?.name || user.providerId
                : ''
              const expanded = expandedRequests[entry.requestId]
              const content = user?.content || ''
              const canExpand = content.length > 80 || content.includes('\n')

              return (
                <div
                  key={entry.requestId}
                  className="overflow-hidden rounded-2xl border border-border-subtle bg-white shadow-sm"
                >
                  <div className="border-b border-border-subtle bg-surface-container-low px-3 py-2.5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] font-medium text-on-surface-variant">
                          {user ? '用户发送' : '恢复记录'}
                        </div>
                        {user?.fileName && (
                          <div className="mt-2 flex items-center gap-2 text-[12px] text-on-surface">
                            <Paperclip className="h-3.5 w-3.5 shrink-0 text-on-surface-variant" />
                            <span className="truncate">{user.fileName}</span>
                          </div>
                        )}
                        {content && (
                          <div
                            className={cn(
                              'mt-2 whitespace-pre-wrap break-words text-[12px] leading-relaxed text-on-surface',
                              !expanded && canExpand && 'line-clamp-2',
                            )}
                          >
                            {content}
                          </div>
                        )}
                        <div className="mt-2 text-[11px] text-on-surface-variant">
                          {providerName ? `${providerName} / ` : ''}
                          {user?.modelName || task?.task.model_name || '未选择模型'}
                        </div>
                      </div>
                      {canExpand && (
                        <button
                          type="button"
                          className="mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-md text-on-surface-variant transition-colors hover:bg-white hover:text-on-surface"
                          onClick={() => toggleExpanded(entry.requestId)}
                          aria-label={expanded ? '收起用户内容' : '展开用户内容'}
                        >
                          {expanded ? (
                            <ChevronUp className="h-4 w-4" />
                          ) : (
                            <ChevronDown className="h-4 w-4" />
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="border-t border-border-subtle">
                    {task ? (
                      renderTaskContent(task)
                    ) : (
                      <div className="px-3 py-3 text-[12px] text-on-surface-variant">任务正在创建中...</div>
                    )}
                  </div>
                </div>
              )
            })}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="border-t border-border-subtle bg-white p-3">
        <div className="rounded-xl border border-border-subtle bg-surface-container-low p-2 shadow-sm">
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".png,.jpg,.jpeg,.webp,.gif,.html,.htm,.pdf,.docx,.md,.markdown,.txt"
            onChange={event =>
              onDraftChange({
                ...draft,
                file: event.target.files?.[0] || null,
              })
            }
          />
          <textarea
            value={draft.instruction}
            rows={2}
            placeholder="输入 URL、说明，或描述你想提取的模板风格..."
            className="max-h-28 min-h-14 w-full resize-none border-0 bg-transparent px-2 py-1 text-[13px] leading-5 text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none"
            onChange={event => {
              onDraftChange({
                ...draft,
                instruction: event.target.value,
              })
              event.currentTarget.style.height = 'auto'
              event.currentTarget.style.height = Math.min(event.currentTarget.scrollHeight, 112) + 'px'
            }}
          />

          {draft.file && (
            <div className="mb-2 flex max-w-full items-center gap-2 rounded-lg border border-border-subtle bg-white px-3 py-2 text-[12px] text-on-surface">
              <Paperclip className="h-3.5 w-3.5 shrink-0 text-on-surface-variant" />
              <span className="truncate">{draft.file.name}</span>
              <button
                type="button"
                onClick={() =>
                  onDraftChange({
                    ...draft,
                    file: null,
                  })
                }
                className="ml-auto rounded p-0.5 text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface"
                aria-label="移除上传文件"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex h-8 items-center gap-1.5 rounded-md px-2 text-[12px] text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface"
            >
              <Paperclip className="h-3.5 w-3.5" />
              上传文件
            </button>

            <div className="ml-auto flex items-center gap-2">
              <div ref={modelRef} className="relative">
                <button
                  type="button"
                  onClick={() => setModelOpen(value => !value)}
                  className="flex h-8 max-w-[152px] items-center gap-1.5 rounded-md border border-border-subtle bg-white px-2.5 text-[12px] text-on-surface transition-colors hover:bg-surface-container-low"
                >
                  <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                  </span>
                  <span className="max-w-[88px] truncate font-medium">
                    {draft.model_name || '请选择模型'}
                  </span>
                  {modelOpen ? (
                    <ChevronUp className="h-3.5 w-3.5 shrink-0" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5 shrink-0" />
                  )}
                </button>
                {modelOpen && (
                  <div className="absolute bottom-full right-0 z-30 mb-2 max-h-72 w-60 overflow-auto rounded-lg border border-border-subtle bg-white p-1 shadow-lg">
                    {modelList.length === 0 ? (
                      <div className="rounded-md px-3 py-3 text-left text-[12px] text-on-surface-variant">
                        暂无可用模型
                      </div>
                    ) : (
                      groupedModels.map((group, index) => (
                        <div
                          key={group.providerId}
                          className={cn(index > 0 && 'mt-1 border-t border-border-subtle pt-1')}
                        >
                          <div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-on-surface-variant/70">
                            {group.providerName}
                          </div>
                          {group.items.map(model => (
                            <button
                              key={model.id}
                              type="button"
                              onClick={() => {
                                onDraftChange({
                                  ...draft,
                                  model_name: model.model_name,
                                  provider_id: model.provider_id || draft.provider_id,
                                })
                                setModelOpen(false)
                              }}
                              className={cn(
                                'flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-[12px] transition-colors',
                                draft.model_name === model.model_name
                                  ? 'bg-primary-light text-primary font-medium'
                                  : 'text-on-surface hover:bg-surface-container-low',
                              )}
                            >
                              <span className="truncate">{model.model_name}</span>
                              {draft.model_name === model.model_name && <Check className="h-3 w-3" />}
                            </button>
                          ))}
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
              <Button
                type="button"
                size="icon"
                disabled={!canSubmit || submitting}
                className={cn('h-8 w-8 shrink-0 rounded-md bg-primary text-white hover:bg-primary/90')}
                onClick={() =>
                  onSubmit({
                    file: draft.file,
                    instruction: draft.instruction,
                    provider_id: selectedModel?.provider_id || draft.provider_id || '',
                    model_name: draft.model_name,
                  })
                }
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </aside>
  )
}

export default StyleImportChat
