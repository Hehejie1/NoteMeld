import { FC, useEffect, useMemo, useState } from 'react'
import { Plus, Search, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  cancelNoteStyleExtractionTask,
  createNoteStyle,
  deleteNoteStyle,
  emptyNoteStylePayload,
  extractNoteStyleFromFile,
  extractNoteStyleFromText,
  fetchNoteStyleExtractionTask,
  fetchNoteStyles,
  retryNoteStyleExtractionTask,
  updateNoteStyle,
  type NoteStyleItem,
  type NoteStylePayload,
  type StyleGenerationMode,
  type StyleExtractionTask,
} from '@/services/noteStyle'
import { uploadFile } from '@/services/upload'
import { cn } from '@/lib/utils'
import { getRuntimeApiBaseUrl } from '@/utils/runtime'
import { FeatureGuideTarget } from '@/demo/FeatureGuideTarget'
import type {
  StyleImportConversationItem,
  StyleImportDraft,
  StyleImportSubmitPayload,
} from './components/StyleImportChat'
import TemplateVersionDialog from './components/TemplateVersionDialog'
import StyleTemplateDrawer from './components/StyleTemplateDrawer'

type DialogMode = 'create' | 'edit' | 'view'
const RUNNING_IMPORT_STATUSES: StyleExtractionTask['status'][] = ['pending', 'running', 'retrying']

const emptyImportDraft = (
  model_name = '',
  provider_id = '',
): StyleImportDraft => ({
  instruction: '',
  file: null,
  model_name,
  provider_id,
})

const upsertConversationTask = (
  conversation: StyleImportConversationItem[],
  requestId: string,
  task: StyleExtractionTask,
) => {
  const taskItem: StyleImportConversationItem = {
    id: `task-${task.task_id}`,
    type: 'task',
    requestId,
    task,
  }
  const existingIndex = conversation.findIndex(
    item =>
      item.type === 'task' &&
      (item.task.task_id === task.task_id || item.requestId === requestId),
  )
  if (existingIndex === -1) {
    return [...conversation, taskItem]
  }
  return conversation.map(item =>
    item.type === 'task' &&
    (item.task.task_id === task.task_id || item.requestId === requestId)
      ? taskItem
      : item,
  )
}

const toPayload = (it: NoteStyleItem): NoteStylePayload => ({
  name: it.name,
  description: it.description,
  skeleton_html: it.skeleton_html,
  style_constraints: it.style_constraints,
  rule_config: it.rule_config,
  example_content: it.example_content,
  output_formats: it.output_formats,
})

const StylesPage: FC = () => {
  const [items, setItems] = useState<NoteStyleItem[]>([])
  const [loading, setLoading] = useState(true)
  const [keyword, setKeyword] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<DialogMode>('create')
  const [form, setForm] = useState<NoteStylePayload>(emptyNoteStylePayload())
  const [editingId, setEditingId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<NoteStyleItem | null>(null)
  const [importTask, setImportTask] = useState<StyleExtractionTask | null>(null)
  const [importConversation, setImportConversation] = useState<StyleImportConversationItem[]>([])
  const [importDraft, setImportDraft] = useState<StyleImportDraft>(emptyImportDraft())
  const [draftSnapshots, setDraftSnapshots] = useState<Record<string, StyleImportDraft>>({})
  const [viewingVersion, setViewingVersion] = useState<NoteStylePayload | null>(null)
  const [leaveGuardOpen, setLeaveGuardOpen] = useState(false)
  const apiBaseUrl = String(getRuntimeApiBaseUrl() || import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
  const hasRunningImportTask =
    dialogOpen && !!importTask && RUNNING_IMPORT_STATUSES.includes(importTask.status)

  const getRequestIdByTaskId = (taskId: string) => {
    const taskItem = importConversation.find(
      item => item.type === 'task' && item.task.task_id === taskId,
    )
    return taskItem?.type === 'task' ? taskItem.requestId : undefined
  }

  const resetImportSession = () => {
    setImportTask(null)
    setImportConversation([])
    setImportDraft(emptyImportDraft())
    setDraftSnapshots({})
    setViewingVersion(null)
    setImporting(false)
    setLeaveGuardOpen(false)
  }

  const closeImportDrawer = () => {
    resetImportSession()
    setDialogOpen(false)
  }

  const load = async () => {
    setLoading(true)
    try {
      const data = await fetchNoteStyles()
      setItems(data || [])
    } catch {
      toast.error('加载风格模板失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    const taskId = importTask?.task_id
    if (!taskId || !importTask || ['succeeded', 'failed', 'canceled'].includes(importTask.status)) return

    const timer = window.setTimeout(async () => {
      try {
        const next = await fetchNoteStyleExtractionTask(taskId)
        setImportTask(next)
        setImportConversation(prev => {
          const requestId =
            prev.find(item => item.type === 'task' && item.task.task_id === taskId)?.requestId ||
            taskId
          return upsertConversationTask(prev, requestId, next)
        })
        if (next.status === 'succeeded' && next.result) {
          setForm(next.result)
        }
      } catch {
        // Keep the current task card visible; the next user action can retry.
      }
    }, 1500)

    return () => window.clearTimeout(timer)
  }, [importTask])

  useEffect(() => {
    if (!hasRunningImportTask) return

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [hasRunningImportTask])

  useEffect(() => {
    if (!hasRunningImportTask || !importTask?.task_id) return

    const handlePageHide = () => {
      void fetch(`${apiBaseUrl}/note_styles/extraction_tasks/${importTask.task_id}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
        keepalive: true,
      }).catch(() => undefined)
    }

    window.addEventListener('pagehide', handlePageHide)
    return () => window.removeEventListener('pagehide', handlePageHide)
  }, [apiBaseUrl, hasRunningImportTask, importTask?.task_id])

  const filtered = useMemo(() => {
    const k = keyword.trim().toLowerCase()
    if (!k) return items
    return items.filter(
      it =>
        it.name.toLowerCase().includes(k) || (it.description || '').toLowerCase().includes(k),
    )
  }, [items, keyword])

  const openCreate = () => {
    setForm(emptyNoteStylePayload())
    setEditingId(null)
    resetImportSession()
    setDialogMode('create')
    setDialogOpen(true)
  }

  const openEdit = (it: NoteStyleItem) => {
    setForm(toPayload(it))
    setEditingId(it.builtin ? null : it.id)
    resetImportSession()
    setDialogMode(it.builtin ? 'view' : 'edit')
    setDialogOpen(true)
  }

  const handleSubmit = async () => {
    if (hasRunningImportTask) {
      toast.error('当前模板任务仍在进行中，请先结束任务再保存')
      return
    }
    if (!form.name.trim()) {
      toast.error('请输入模板名称')
      return
    }
    if (!form.skeleton_html.trim()) {
      toast.error('请输入骨架模板')
      return
    }
    setSubmitting(true)
    try {
      if (editingId) {
        await updateNoteStyle(editingId, {
          ...form,
          name: form.name.trim(),
          description: form.description.trim(),
          skeleton_html: form.skeleton_html.trim(),
        })
        toast.success('已更新')
      } else {
        await createNoteStyle({
          ...form,
          name: form.name.trim(),
          description: form.description.trim(),
          skeleton_html: form.skeleton_html.trim(),
        })
        toast.success('已创建')
      }
      closeImportDrawer()
      load()
    } catch {
      // toast already shown by request interceptor
    } finally {
      setSubmitting(false)
    }
  }

  const handleImportSubmit = async (payload: StyleImportSubmitPayload) => {
    if (!payload.file && !payload.instruction.trim()) return
    setImporting(true)
    const generationMode: StyleGenerationMode =
      importConversation.some(item => item.type === 'task' && item.task.status === 'succeeded') ||
      form.name.trim() ||
      form.description.trim()
        ? 'edit'
        : 'create'
    const currentTemplateForRequest = generationMode === 'edit' ? form : undefined
    const requestId = `draft-${Date.now()}`
    const draftSnapshot: StyleImportDraft = {
      instruction: payload.instruction,
      file: payload.file,
      model_name: payload.model_name,
      provider_id: payload.provider_id,
    }
    setDraftSnapshots(prev => ({
      ...prev,
      [requestId]: draftSnapshot,
    }))
    setImportDraft(emptyImportDraft(payload.model_name, payload.provider_id))
    const userConversationItem: StyleImportConversationItem = {
      id: `user-${requestId}`,
      type: 'user',
      requestId,
      content: payload.instruction,
      fileName: payload.file?.name,
      modelName: payload.model_name,
      providerId: payload.provider_id,
      createdAt: Date.now(),
    }
    setImportConversation(prev => [...prev, userConversationItem])
    try {
      let task: StyleExtractionTask
      if (payload.file) {
        const formData = new FormData()
        formData.append('file', payload.file)
        const upload = await uploadFile(formData)
        task = await extractNoteStyleFromFile({
          file_url: upload.url,
          file_name: upload.file_name,
          content_type: upload.content_type,
          provider_id: payload.provider_id,
          model_name: payload.model_name,
          user_instruction: payload.instruction,
          current_template: currentTemplateForRequest,
          generation_mode: generationMode,
        })
      } else {
        task = await extractNoteStyleFromText({
          content: payload.instruction,
          source_name: 'manual.md',
          provider_id: payload.provider_id,
          model_name: payload.model_name,
          user_instruction: payload.instruction,
          current_template: currentTemplateForRequest,
          generation_mode: generationMode,
        })
      }
      setImportConversation(prev => upsertConversationTask(prev, requestId, task))
      setImportTask(task)
      if (task.result) {
        setForm(task.result)
      }
    } catch {
      setImportDraft(draftSnapshot)
      toast.error('提取模板失败，已恢复本次草稿')
    } finally {
      setImporting(false)
    }
  }

  const handleImportRetry = async (taskId: string) => {
    setImporting(true)
    try {
      const task = await retryNoteStyleExtractionTask(taskId)
      setImportTask(task)
      setImportConversation(prev => upsertConversationTask(prev, getRequestIdByTaskId(taskId) || taskId, task))
    } catch {
      toast.error('重试模板提取失败')
    } finally {
      setImporting(false)
    }
  }

  const handleImportTaskCancel = async (taskId: string) => {
    try {
      const task = await cancelNoteStyleExtractionTask(taskId)
      setImportTask(task)
      setImportConversation(prev =>
        upsertConversationTask(prev, getRequestIdByTaskId(taskId) || taskId, task),
      )
      toast.success('已取消模板任务')
    } catch {
      toast.error('取消模板任务失败')
    }
  }

  const handleRestoreDraft = (requestId: string) => {
    const snapshot = draftSnapshots[requestId]
    if (!snapshot) {
      toast.error('未找到可恢复草稿')
      return
    }
    setImportDraft(snapshot)
    toast.success('已恢复本次草稿')
  }

  const handleViewVersion = (version: NoteStylePayload) => {
    setViewingVersion(version)
  }

  const handleUseFollowupPrompt = (prompt: string) => {
    setImportDraft(prev => ({
      ...prev,
      instruction: prompt,
    }))
  }

  const handleDrawerCloseRequest = () => {
    if (hasRunningImportTask) {
      setLeaveGuardOpen(true)
      return
    }
    closeImportDrawer()
  }

  const handleConfirmLeave = async () => {
    if (!importTask?.task_id || !RUNNING_IMPORT_STATUSES.includes(importTask.status)) {
      closeImportDrawer()
      return
    }
    try {
      await cancelNoteStyleExtractionTask(importTask.task_id)
      closeImportDrawer()
      toast.success('已结束当前模板任务')
    } catch {
      toast.error('结束任务失败，请稍后重试')
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteNoteStyle(deleteTarget.id)
      toast.success('已删除')
      setDeleteTarget(null)
      load()
    } catch {
      // toast handled
    }
  }

  const readonlyView = dialogMode === 'view'

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-surface">
      {/* 顶部工具条 */}
      <div className="flex flex-col gap-3 border-b border-border-subtle/60 bg-white px-4 py-4 md:flex-row md:items-center md:px-6">
        <div className="relative w-full flex-1 md:max-w-xl">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-on-surface-variant" />
          <Input
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            placeholder="搜索名称或描述..."
            className="h-10 border-border-subtle bg-surface-container pl-9 focus-visible:ring-primary"
          />
        </div>
        <FeatureGuideTarget featureId="styles-create" onExecute={openCreate}>
        <Button
          onClick={openCreate}
          className="h-10 w-full gap-1.5 rounded-md bg-primary px-4 text-white hover:bg-primary/90 md:w-auto"
        >
          <Plus className="h-4 w-4" />
          新建模板
        </Button>
        </FeatureGuideTarget>
      </div>

      {/* 模板列表 */}
      <ScrollArea className="min-h-0 flex-1">
        <div className="px-4 py-4 pb-6 md:px-6 md:py-6">
          {loading ? (
            <SkeletonGrid />
          ) : filtered.length === 0 ? (
            <div className="flex h-[260px] items-center justify-center rounded-xl border border-dashed border-border-subtle bg-white text-[13px] text-on-surface-variant">
              {keyword ? '没有匹配的风格模板' : '还没有任何风格模板'}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {filtered.map(it => (
                <StyleCard
                  key={it.id}
                  item={it}
                  keyword={keyword}
                  onClick={() => openEdit(it)}
                  onDelete={() => setDeleteTarget(it)}
                />
              ))}
            </div>
          )}
        </div>
      </ScrollArea>

      <StyleTemplateDrawer
        open={dialogOpen}
        title={
          readonlyView ? '查看内置风格模板' : editingId ? '编辑笔记风格模板' : '新建笔记风格模板'
        }
        value={form}
        readonly={readonlyView}
        submitting={submitting}
        importing={importing}
        importConversation={importConversation}
        importDraft={importDraft}
        onChange={setForm}
        onClose={handleDrawerCloseRequest}
        onSubmit={handleSubmit}
        onImportDraftChange={setImportDraft}
        onImportSubmit={handleImportSubmit}
        onImportRetry={handleImportRetry}
        onImportCancel={handleImportTaskCancel}
        onImportRestoreDraft={handleRestoreDraft}
        onImportUsePrompt={handleUseFollowupPrompt}
        onImportViewVersion={handleViewVersion}
      />

      <TemplateVersionDialog
        open={!!viewingVersion}
        version={viewingVersion}
        onOpenChange={open => !open && setViewingVersion(null)}
      />

      <Dialog open={leaveGuardOpen} onOpenChange={setLeaveGuardOpen}>
        <DialogContent className="max-w-[calc(100vw-32px)] md:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>结束当前模板任务？</DialogTitle>
            <DialogDescription>
              当前模板任务仍在进行中。必须先点“结束任务并离开”，或者继续留在当前页。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLeaveGuardOpen(false)}>
              继续留在当前页
            </Button>
            <Button variant="destructive" onClick={handleConfirmLeave}>
              结束任务并离开
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认 */}
      <Dialog
        open={!!deleteTarget}
        onOpenChange={(open: boolean) => !open && setDeleteTarget(null)}
      >
        <DialogContent className="max-w-[calc(100vw-32px)] md:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>删除风格模板？</DialogTitle>
            <DialogDescription>
              将永久删除「{deleteTarget?.name}」，此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              onClick={handleDelete}
              className="bg-destructive text-white hover:bg-destructive/90"
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/* ===== 子组件：模板卡片 ===== */
const StyleCard: FC<{
  item: NoteStyleItem
  keyword: string
  onClick: () => void
  onDelete: () => void
}> = ({ item, keyword, onClick, onDelete }) => {
  return (
    <div
      onClick={onClick}
      className={cn(
        'group relative flex cursor-pointer flex-col gap-2 rounded-xl border border-border-subtle bg-white p-4 transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-[0_8px_24px_rgba(76,64,246,0.08)]',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-display flex-1 truncate text-[15px] font-semibold text-on-surface">
          <Highlight text={item.name} keyword={keyword} />
        </h3>
        {item.builtin ? (
          <span className="inline-flex h-5 shrink-0 items-center rounded-md bg-surface-container px-1.5 text-[10px] font-medium text-on-surface-variant">
            内置
          </span>
        ) : (
          <button
            type="button"
            onClick={e => {
              e.stopPropagation()
              onDelete()
            }}
            className="shrink-0 rounded-md p-1 text-on-surface-variant/60 opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
            title="删除"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
      <p className="text-[12.5px] leading-relaxed text-on-surface-variant line-clamp-3">
        <Highlight text={item.description || '暂无描述'} keyword={keyword} />
      </p>
      <div className="mt-auto flex gap-1.5 pt-2">
        {item.output_formats.map(format => (
          <span
            key={format}
            className="rounded bg-surface-container px-1.5 py-0.5 text-[10px] text-on-surface-variant"
          >
            {format.toUpperCase()}
          </span>
        ))}
      </div>
    </div>
  )
}

/* ===== 子组件：高亮匹配 ===== */
const Highlight: FC<{ text: string; keyword: string }> = ({ text, keyword }) => {
  const k = keyword.trim()
  if (!k) return <>{text}</>
  const safe = k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`(${safe})`, 'ig')
  const parts = text.split(re)
  return (
    <>
      {parts.map((p, i) =>
        re.test(p) ? (
          <mark
            key={i}
            className="rounded bg-primary-light px-0.5 text-primary"
          >
            {p}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  )
}

/* ===== 子组件：骨架 ===== */
const SkeletonGrid: FC = () => (
  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
    {Array.from({ length: 8 }).map((_, i) => (
      <div
        key={i}
        className="h-[120px] animate-pulse rounded-xl border border-border-subtle bg-white"
      />
    ))}
  </div>
)

export default StylesPage
