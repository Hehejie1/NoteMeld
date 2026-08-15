import { create } from 'zustand'
import { generateNote } from '@/services/note.ts'
import { deleteConversation, deleteConversationDocument, fetchConversation, fetchConversations, upsertConversation } from '@/services/conversation'
import { v4 as uuidv4 } from 'uuid'
import toast from 'react-hot-toast'
import { extractNoteTitleFromMarkdown } from '@/store/taskTitle'
import { mergeConversationMessages } from '@/store/taskStore/mergeConversationMessages'
import type { CollectorTimings, ProgressTiming } from '@/types/progress'
import type { ConversationContextRef } from '@/services/chat'


export type TaskStatus =
  | 'PENDING'
  | 'PARSING'
  | 'DOWNLOADING'
  | 'TRANSCRIBING'
  | 'SUMMARIZING'
  | 'FORMATTING'
  | 'SAVING'
  | 'SUCCESS'
  | 'FAILED'
  | 'CANCELED'
  | 'NOT_FOUND'

export interface AudioMeta {
  cover_url: string
  duration: number
  file_path: string
  platform: string
  raw_info: any
  title: string
  video_id: string
}

export interface Segment {
  start: number
  end: number
  text: string
}

export interface Transcript {
  full_text: string
  language: string
  raw: any
  segments: Segment[]
}

export interface NoteDocument {
  taskId: string
  title: string
  content: string
  sourceUrl?: string
  platform?: string
  modelName?: string
  style?: string
  status?: string
  wikiStatus?: string
  createdAt: string
}

export type ConversationMode = 'chat' | 'note'
export type ConversationNoteState = 'none' | 'generating' | 'ready' | 'failed'
export type ConversationMessageRole = 'user' | 'assistant' | 'system'
export type ConversationMessageType =
  | 'user_input'
  | 'assistant_text'
  | 'note_progress'
  | 'note_result'
  | 'system_error'
  | 'task_card'
  | 'task_card_progress'
  | 'parameter_request'
  | 'parameter_response'
  | 'learning_canvas'
export type ConversationMessageStatus = 'pending' | 'running' | 'success' | 'failed'

export interface ConversationSource {
  text: string
  type?: string
  source_type?: string
  snippet?: string
  title?: string
  page_id?: string
  section_title?: string
  score?: number
  metadata?: Record<string, any>
}

export interface ConversationMessage {
  id: string
  role: ConversationMessageRole
  message_type: ConversationMessageType
  content: string
  status?: ConversationMessageStatus
  meta?: Record<string, any>
  createdAt: string
  updatedAt: string
  sources?: ConversationSource[]
  error?: boolean
  isStreaming?: boolean
}

export interface TaskStatusMeta {
  taskId: string
  currentStep?: TaskStatus
  attemptId?: string
  attempt?: number
  sourceUrl?: string
  extras?: string
  stageTimings?: Record<string, ProgressTiming>
  collectorTimings?: CollectorTimings
  stageStartedAt?: string
  updatedAt?: string
}

export interface Task {
  id: string
  markdown: string
  transcript: Transcript
  status: TaskStatus
  message?: string
  audioMeta: AudioMeta
  createdAt: string
  platform?: string
  mode?: ConversationMode
  title?: string
  messages?: ConversationMessage[]
  linkedNoteTaskId?: string
  pendingNoteTaskIds?: string[]
  activeDocumentTaskId?: string
  documents?: NoteDocument[]
  noteState?: ConversationNoteState
  formData: {
    video_url: string
    link: undefined | boolean
    screenshot: undefined | boolean
    platform: string
    quality: string
    model_name: string
    provider_id: string
    style?: string
    extras?: string
  }
}

interface TaskStore {
  tasks: Task[]
  currentTaskId: string | null
  hasLoadedConversations: boolean
  learningRequestInFlight: boolean
  pendingContextRefs: ConversationContextRef[]
  addContextRef: (reference: ConversationContextRef) => void
  removeContextRef: (referenceId: string) => void
  clearContextRefs: () => void
  beginLearningRequest: () => boolean
  finishLearningRequest: () => void
  addPendingTask: (taskId: string, platform: string, formData: any) => void
  createConversation: (data: {
    id?: string
    mode: ConversationMode
    title?: string
    firstMessage?: string
    formData?: any
    platform?: string
  }) => string
  appendMessage: (taskId: string, message: Omit<ConversationMessage, 'id' | 'createdAt'> & Partial<Pick<ConversationMessage, 'id' | 'createdAt'>>) => void
  updateMessage: (taskId: string, messageId: string, data: Partial<ConversationMessage>) => void
  linkNoteTask: (conversationId: string, noteTaskId: string, formData: any, platform: string) => void
  setNoteState: (conversationId: string, noteState: ConversationNoteState) => void
  updateTaskContent: (id: string, data: Partial<Omit<Task, 'id' | 'createdAt'>> & { documentTaskId?: string; taskStatusMeta?: TaskStatusMeta }) => void
  selectNoteDocument: (conversationId: string, taskId: string) => void
  deleteNoteDocument: (conversationId: string, taskId: string) => Promise<void>
  removeTask: (id: string) => Promise<void>
  clearTasks: () => void
  setCurrentTask: (taskId: string | null) => void
  getCurrentTask: () => Task | null
  retryTask: (id: string, payload?: any, noteTaskIdOverride?: string) => Promise<void>
  loadConversations: () => Promise<void>
  loadConversation: (id: string) => Promise<Task | null>
  refreshConversation: (id: string) => Promise<Task | null>
  retryChat: (id: string) => Promise<void>
}

const defaultFormData = () => ({
  video_url: '',
  link: undefined,
  screenshot: undefined,
  platform: '',
  quality: 'medium',
  model_name: '',
  provider_id: '',
  style: '',
})

const defaultTranscript = (): Transcript => ({
  full_text: '',
  language: '',
  raw: null,
  segments: [],
})

const defaultAudioMeta = (): AudioMeta => ({
  cover_url: '',
  duration: 0,
  file_path: '',
  platform: '',
  raw_info: null,
  title: '',
  video_id: '',
})

export const normalizeConversationMessage = (raw: Record<string, any>): ConversationMessage => {
  const createdAt = raw.createdAt || raw.created_at || new Date().toISOString()
  const missingMessageType = !raw.message_type
  const meta = {
    ...(raw.meta || {}),
    ...(missingMessageType ? { contract_error: "missing_message_type" } : {}),
  }

  if (missingMessageType) {
    console.warn("Conversation message missing message_type, downgraded to system_error", raw)
  }

  return {
    id: raw.id || uuidv4(),
    role: (raw.role || "assistant") as ConversationMessageRole,
    message_type: (raw.message_type || "system_error") as ConversationMessageType,
    content: raw.content || (missingMessageType ? "Message missing message_type; downgraded to system_error." : ""),
    status: raw.status || undefined,
    meta,
    createdAt,
    updatedAt: raw.updatedAt || raw.updated_at || createdAt,
    sources: raw.sources || [],
    error: Boolean(raw.error) || missingMessageType,
    isStreaming: Boolean(raw.isStreaming),
  }
}

export const normalizeNoteDocument = (rawDocument: Record<string, any>): NoteDocument => ({
  taskId: rawDocument.taskId || rawDocument.task_id || '',
  title: rawDocument.title || '未命名笔记',
  content: rawDocument.content || '',
  sourceUrl: rawDocument.sourceUrl || rawDocument.source_url || '',
  platform: rawDocument.platform || '',
  modelName: rawDocument.modelName || rawDocument.model_name || '',
  style: rawDocument.style || '',
  status: rawDocument.status || '',
  wikiStatus: rawDocument.wikiStatus || rawDocument.wiki_status || '',
  createdAt: rawDocument.createdAt || rawDocument.created_at || new Date().toISOString(),
})

export const derivePendingNoteTaskIds = (messages: ConversationMessage[], explicitIds: string[]): string[] => {
  const activeIds = messages
    .filter(message =>
      message.message_type === 'note_progress'
      && (message.status === 'pending' || message.status === 'running')
      && typeof message.meta?.task_id === 'string',
    )
    .map(message => message.meta?.task_id as string)
  return Array.from(new Set([...explicitIds, ...activeIds]))
}

export const normalizeTask = (raw: Record<string, any>): Task => {
  const messages = (raw.messages || []).map((message: Record<string, any>) => normalizeConversationMessage(message))
  const explicitPendingIds = raw.pendingNoteTaskIds || raw.pending_note_task_ids || []
  return {
    id: raw.id || uuidv4(),
    markdown: raw.markdown || '',
    transcript: {
      ...defaultTranscript(),
      ...(raw.transcript || {}),
    },
    status: (raw.status || 'SUCCESS') as TaskStatus,
    message: raw.message || '',
    audioMeta: {
      ...defaultAudioMeta(),
      ...(raw.audioMeta || raw.audio_meta || {}),
    },
    createdAt: raw.createdAt || raw.created_at || new Date().toISOString(),
    platform: raw.platform || '',
    mode: raw.mode || 'chat',
    title: raw.title || '',
    messages,
    linkedNoteTaskId: raw.linkedNoteTaskId || raw.linked_note_task_id || '',
    pendingNoteTaskIds: derivePendingNoteTaskIds(messages, explicitPendingIds),
    activeDocumentTaskId: raw.activeDocumentTaskId || raw.active_document_task_id || '',
    documents: (raw.documents || []).map((rawDocument: Record<string, any>) => normalizeNoteDocument(rawDocument)),
    noteState: raw.noteState || raw.note_state || (raw.mode === 'note' ? 'generating' : 'none'),
    formData: {
      ...defaultFormData(),
      ...(raw.formData || raw.form_data || {}),
    },
  }
}

const upsertLocalTask = (tasks: Task[], nextTask: Task): Task[] => {
  const existing = tasks.find(task => task.id === nextTask.id)
  if (!existing) return [nextTask, ...tasks]
  return tasks.map(task =>
    task.id === nextTask.id
      ? {
          ...task,
          ...nextTask,
          activeDocumentTaskId: preserveActiveDocumentTaskIdForRefresh(task, nextTask),
          messages: preserveRetryingNoteProgressDuringRefresh(
            mergeConversationMessages(nextTask.messages || [], task.messages || []),
            task.messages || [],
          ),
        }
      : task,
  )
}

const preserveActiveDocumentTaskIdForRefresh = (existing: Task, nextTask: Task): string => {
  const documents = nextTask.documents?.length ? nextTask.documents : existing.documents || []
  const currentActiveTaskId = existing.activeDocumentTaskId || ''
  const nextActiveTaskId = nextTask.activeDocumentTaskId || ''
  const hasCurrentActiveDocument = Boolean(currentActiveTaskId)
    && documents.some(document => document.taskId === currentActiveTaskId && document.content)
  if (hasCurrentActiveDocument) return currentActiveTaskId

  const hasNextActiveDocument = Boolean(nextActiveTaskId)
    && documents.some(document => document.taskId === nextActiveTaskId && document.content)
  if (hasNextActiveDocument) return nextActiveTaskId

  return nextActiveTaskId || currentActiveTaskId
}

const createRetryAttemptId = (noteTaskId: string): string => `${noteTaskId}:${Date.now()}`

export const findTaskSourceForRetry = (task: Task, noteTaskId: string) => {
  const progressMessage = (task.messages || []).find(message =>
    message.message_type === 'note_progress'
    && message.meta?.task_id === noteTaskId,
  )
  const resultMessage = (task.messages || []).find(message =>
    message.message_type === 'note_result'
    && message.meta?.task_id === noteTaskId,
  )
  const document = (task.documents || []).find(item => item.taskId === noteTaskId)
  return {
    sourceUrl:
      progressMessage?.meta?.source_url
      || resultMessage?.meta?.source_url
      || document?.sourceUrl
      || task.formData?.video_url
      || '',
    extras: progressMessage?.meta?.extras || task.formData?.extras || '',
  }
}

const createRetryProgressMessage = (
  noteTaskId: string,
  attemptId: string,
  retryMessage: string,
  retryStartedAt: string,
  sourceUrl: string,
  extras: string,
): ConversationMessage => ({
  id: `note-progress-${noteTaskId}`,
  role: 'assistant',
  message_type: 'note_progress',
  content: retryMessage,
  status: 'pending',
  meta: {
    task_id: noteTaskId,
    attempt_id: attemptId,
    retry_started_at: retryStartedAt,
    current_step: 'PENDING',
    detail: retryMessage,
    source_url: sourceUrl,
    extras,
  },
  createdAt: retryStartedAt,
  updatedAt: retryStartedAt,
})

export const markNoteProgressAsRetrying = (task: Task, noteTaskId: string, attemptId: string): Task => {
  const retryMessage = '任务已提交，等待后台生成'
  const retryStartedAt = new Date().toISOString()
  const retrySource = findTaskSourceForRetry(task, noteTaskId)
  let matchedProgressMessage = false
  const messages = (task.messages || []).map(message => {
    if (message.message_type !== 'note_progress') return message
    const messageTaskId = typeof message.meta?.task_id === 'string' ? message.meta.task_id : ''
    if (messageTaskId && messageTaskId !== noteTaskId) return message
    matchedProgressMessage = true
    return {
      ...message,
      status: 'pending' as const,
      error: false,
      content: retryMessage,
      meta: {
        ...(message.meta || {}),
        task_id: noteTaskId,
        attempt_id: attemptId,
        retry_started_at: retryStartedAt,
        current_step: 'PENDING',
        detail: retryMessage,
        source_url: message.meta?.source_url || retrySource.sourceUrl,
        extras: message.meta?.extras || retrySource.extras,
      },
    }
  })
  if (!matchedProgressMessage) {
    messages.push(createRetryProgressMessage(
      noteTaskId,
      attemptId,
      retryMessage,
      retryStartedAt,
      retrySource.sourceUrl,
      retrySource.extras,
    ))
  }

  return {
    ...task,
    status: 'PENDING',
    noteState: 'generating',
    pendingNoteTaskIds: Array.from(new Set([...(task.pendingNoteTaskIds || []), noteTaskId])),
    messages,
  }
}

export const preserveRetryingNoteProgressDuringRefresh = (
  mergedMessages: ConversationMessage[],
  localMessages: ConversationMessage[],
): ConversationMessage[] => {
  const localRetryingMessages = new Map(
    localMessages
      .filter(message =>
        message.message_type === 'note_progress'
        && (message.status === 'pending' || message.status === 'running')
        && typeof message.meta?.task_id === 'string',
      )
      .map(message => [message.meta?.task_id as string, message]),
  )

  if (localRetryingMessages.size === 0) return mergedMessages

  return mergedMessages.map(message => {
    if (message.message_type !== 'note_progress' || message.status !== 'failed') return message
    const messageTaskId = typeof message.meta?.task_id === 'string' ? message.meta.task_id : ''
    const localRetryingMessage = localRetryingMessages.get(messageTaskId)
    if (!localRetryingMessage) return message

    const localAttemptId = typeof localRetryingMessage.meta?.attempt_id === 'string'
      ? localRetryingMessage.meta.attempt_id
      : ''
    const remoteAttemptId = typeof message.meta?.attempt_id === 'string' ? message.meta.attempt_id : ''
    if (!localAttemptId || remoteAttemptId !== localAttemptId) return localRetryingMessage

    return message
  })
}

export const updateNoteProgressMessages = (
  messages: ConversationMessage[] = [],
  noteTaskId: string,
  status: ConversationMessageStatus,
  content: string,
  taskStatusMeta?: TaskStatusMeta,
): ConversationMessage[] => {
  let matched = false
  const now = new Date().toISOString()
  const nextMessages = messages.map(message => {
    if (message.message_type !== 'note_progress') return message
    const messageTaskId = typeof message.meta?.task_id === 'string' ? message.meta.task_id : ''
    if (messageTaskId && messageTaskId !== noteTaskId) return message
    matched = true
    return {
      ...message,
      status,
      error: status === 'failed',
      content,
      updatedAt: now,
      meta: {
        ...(message.meta || {}),
        task_id: noteTaskId,
        current_step: status === 'failed' ? 'FAILED' : taskStatusMeta?.currentStep || message.meta?.current_step,
        detail: content,
        attempt_id: taskStatusMeta?.attemptId || message.meta?.attempt_id || '',
        attempt: taskStatusMeta?.attempt ?? message.meta?.attempt ?? 0,
        source_url: taskStatusMeta?.sourceUrl || message.meta?.source_url || '',
        extras: taskStatusMeta?.extras || message.meta?.extras || '',
        stage_timings: taskStatusMeta?.stageTimings || message.meta?.stage_timings || {},
        collector_timings: taskStatusMeta?.collectorTimings || message.meta?.collector_timings || {},
        stage_started_at: taskStatusMeta?.stageStartedAt || message.meta?.stage_started_at || '',
        timing_updated_at: taskStatusMeta?.updatedAt || message.meta?.timing_updated_at || '',
      },
    }
  })
  if (!matched) {
    nextMessages.push({
      id: `note-progress-${noteTaskId}`,
      role: 'assistant',
      message_type: 'note_progress',
      content,
      status,
      error: status === 'failed',
      meta: {
        task_id: noteTaskId,
        current_step: status === 'failed' ? 'FAILED' : taskStatusMeta?.currentStep || 'PENDING',
        detail: content,
        attempt_id: taskStatusMeta?.attemptId || '',
        attempt: taskStatusMeta?.attempt || 0,
        source_url: taskStatusMeta?.sourceUrl || '',
        extras: taskStatusMeta?.extras || '',
        stage_timings: taskStatusMeta?.stageTimings || {},
        collector_timings: taskStatusMeta?.collectorTimings || {},
        stage_started_at: taskStatusMeta?.stageStartedAt || '',
        timing_updated_at: taskStatusMeta?.updatedAt || '',
      },
      createdAt: now,
      updatedAt: now,
    })
  }
  return nextMessages
}

const isTerminalFailureStatus = (status?: string): boolean =>
  status === 'FAILED' || status === 'CANCELED' || status === 'NOT_FOUND'

export const useTaskStore = create<TaskStore>()((set, get) => ({
  tasks: [],
  currentTaskId: null,
  hasLoadedConversations: false,
  learningRequestInFlight: false,
  pendingContextRefs: [],
  addContextRef: reference => set(state => ({
    pendingContextRefs: [
      ...state.pendingContextRefs.filter(item => item.id !== reference.id),
      {
        ...reference,
        snapshot: reference.snapshot.slice(
          0,
          reference.type === 'whiteboard_selection' ? 12000 : 2000,
        ),
      },
    ].slice(-8),
  })),
  removeContextRef: referenceId => set(state => ({
    pendingContextRefs: state.pendingContextRefs.filter(item => item.id !== referenceId),
  })),
  clearContextRefs: () => set({ pendingContextRefs: [] }),

  beginLearningRequest: () => {
    if (get().learningRequestInFlight) return false
    set({ learningRequestInFlight: true })
    return true
  },

  finishLearningRequest: () => set({ learningRequestInFlight: false }),

  addPendingTask: (taskId: string, platform: string, formData: any) =>

    set(state => ({
      tasks: upsertLocalTask(
        state.tasks,
        normalizeTask({
          formData,
          id: taskId,
          status: 'PENDING',
          message: '',
          markdown: '',
          platform,
          mode: 'note',
          noteState: 'generating',
        }),
      ),
      currentTaskId: taskId,
    })),

  createConversation: ({ id, mode, title, firstMessage, formData, platform }) => {
    const taskId = id || uuidv4()
    const now = new Date().toISOString()
    const messages: ConversationMessage[] = firstMessage
      ? [{
          id: uuidv4(),
          role: 'user',
          message_type: 'user_input',
          content: firstMessage,
          createdAt: now,
          updatedAt: now,
        }]
      : []
    set(state => ({
      tasks: upsertLocalTask(
        state.tasks,
        normalizeTask({
          id: taskId,
          mode,
          title: title || firstMessage?.slice(0, 24) || '未命名对话',
          messages,
          linkedNoteTaskId: '',
          noteState: mode === 'note' ? 'generating' : 'none',
          status: mode === 'note' ? 'PENDING' : 'SUCCESS',
          message: '',
          markdown: '',
          platform: platform || formData?.platform || '',
          formData: formData || defaultFormData(),
          createdAt: now,
        }),
      ),
      currentTaskId: taskId,
    }))
    return taskId
  },

  appendMessage: (taskId, message) =>
    set(state => ({
      tasks: state.tasks.map(task =>
        task.id === taskId
          ? {
              ...task,
              messages: [
                ...(task.messages || []),
                normalizeConversationMessage(message),
              ],
              title:
                task.title ||
                (message.role === 'user' ? message.content.slice(0, 24) : undefined) ||
                '未命名对话',
            }
          : task,
      ),
    })),

  updateMessage: (taskId, messageId, data) =>
    set(state => ({
      tasks: state.tasks.map(task =>
        task.id === taskId
          ? {
              ...task,
              messages: (task.messages || []).map(message =>
                message.id === messageId
                  ? { ...message, ...data }
                  : message,
              ),
            }
          : task,
      ),
    })),

  linkNoteTask: (conversationId, noteTaskId, formData, platform) =>
    set(state => ({
      tasks: state.tasks.map(task =>
        task.id === conversationId
          ? {
              ...task,
              mode: 'note',
              linkedNoteTaskId: noteTaskId,
              pendingNoteTaskIds: Array.from(new Set([...(task.pendingNoteTaskIds || []), noteTaskId])),
              noteState: 'generating',
              status: 'PENDING',
              platform,
              formData,
            }
          : task,
      ),
      currentTaskId: conversationId,
    })),

  setNoteState: (conversationId, noteState) =>
    set(state => ({
      tasks: state.tasks.map(task =>
        task.id === conversationId ? { ...task, noteState } : task,
      ),
    })),

  updateTaskContent: (id, data) =>
    set(state => ({
      tasks: state.tasks.map(task => {
        if (task.id !== id) return task

        const documentTaskId = data.documentTaskId || task.linkedNoteTaskId || task.id
        const pendingNoteTaskIds = (task.pendingNoteTaskIds || []).filter(taskId => taskId !== documentTaskId)
        const progressStatus: ConversationMessageStatus | null =
          isTerminalFailureStatus(data.status)
            ? 'failed'
            : data.status === 'SUCCESS'
            ? 'success'
            : data.status
            ? 'running'
            : null
        const progressMessage = data.message || task.message || ''

        if (typeof data.markdown === 'string') {
          const title = extractNoteTitleFromMarkdown(data.markdown) || data.audioMeta?.title || task.audioMeta?.title || task.title || '未命名笔记'
          const nextDocument: NoteDocument = {
            taskId: documentTaskId,
            title,
            content: data.markdown,
            platform: data.audioMeta?.platform || task.platform || task.formData?.platform,
            modelName: task.formData?.model_name,
            style: task.formData?.style,
            createdAt: new Date().toISOString(),
          }
          const documents = [
            nextDocument,
            ...(task.documents || []).filter(document => document.taskId !== documentTaskId),
          ]
          return {
            ...task,
            ...data,
            title,
            markdown: data.markdown,
            documents,
            activeDocumentTaskId: documentTaskId,
            pendingNoteTaskIds,
            messages: progressStatus
              ? updateNoteProgressMessages(task.messages, documentTaskId, progressStatus, progressMessage, data.taskStatusMeta)
              : task.messages,
            noteState: pendingNoteTaskIds.length === 0 && data.status === 'SUCCESS' ? 'ready' : task.noteState,
            status: pendingNoteTaskIds.length === 0 ? (data.status || task.status) : 'PENDING',
          }
        }

        return {
          ...task,
          ...data,
          pendingNoteTaskIds: isTerminalFailureStatus(data.status) ? pendingNoteTaskIds : task.pendingNoteTaskIds,
          messages: progressStatus
            ? updateNoteProgressMessages(task.messages, documentTaskId, progressStatus, progressMessage, data.taskStatusMeta)
            : task.messages,
          status: isTerminalFailureStatus(data.status) && pendingNoteTaskIds.length > 0 ? 'PENDING' : (data.status || task.status),
          noteState:
            isTerminalFailureStatus(data.status) && pendingNoteTaskIds.length > 0
              ? 'generating'
              : data.status === 'SUCCESS'
              ? 'ready'
              : isTerminalFailureStatus(data.status)
              ? 'failed'
              : task.noteState,
        }
      }),
    })),

  selectNoteDocument: (conversationId, taskId) =>
    set(state => ({
      tasks: state.tasks.map(task => {
        if (task.id !== conversationId) return task
        const document = (task.documents || []).find(item => item.taskId === taskId)
        if (!document) return { ...task, activeDocumentTaskId: taskId }
        return {
          ...task,
          activeDocumentTaskId: taskId,
          markdown: document.content,
          title: document.title || task.title,
        }
      }),
    })),

  deleteNoteDocument: async (conversationId: string, taskId: string) => {
    if (!conversationId || !taskId) return
    const nextTask = normalizeTask(await deleteConversationDocument(conversationId, taskId))
    set(state => ({
      tasks: upsertLocalTask(state.tasks, nextTask),
    }))
    toast.success('笔记已删除')
  },

  getCurrentTask: () => {
    const currentTaskId = get().currentTaskId
    return get().tasks.find(task => task.id === currentTaskId) || null
  },

  retryTask: async (id: string, payload?: any, noteTaskIdOverride?: string) => {
    if (!id) {
      toast.error('任务不存在')
      return
    }
    const task = get().tasks.find(item => item.id === id)
    if (!task) return

    const newFormData = payload || task.formData
    const noteTaskId = noteTaskIdOverride || task.linkedNoteTaskId || id
    const retrySource = findTaskSourceForRetry(task, noteTaskId)
    const retryAttemptId = createRetryAttemptId(noteTaskId)
    set(state => ({
      tasks: state.tasks.map(t =>
        t.id === id ? markNoteProgressAsRetrying(t, noteTaskId, retryAttemptId) : t,
      ),
    }))
    await upsertConversation(id, {
      id,
      mode: 'note',
      title: task.title || extractNoteTitleFromMarkdown(task.markdown) || task.audioMeta?.title || '未命名对话',
      status: 'PENDING',
      noteState: 'generating',
      platform: task.platform || newFormData?.platform || '',
      linkedNoteTaskId: noteTaskId,
      formData: newFormData,
    })
    await generateNote({
      ...newFormData,
      conversation_id: id,
      task_id: noteTaskId,
      retry_attempt_id: retryAttemptId,
      video_url: retrySource.sourceUrl || newFormData.video_url,
      extras: retrySource.extras || newFormData.extras,
    }, { suppressSuccessToast: true })

    set(state => ({
      tasks: state.tasks.map(t =>
        t.id === id
          ? {
              ...t,
              formData: newFormData,
              status: 'PENDING',
              noteState: 'generating',
            }
          : t,
      ),
    }))
  },

  removeTask: async id => {
    await deleteConversation(id)
    set(state => ({
      tasks: state.tasks.filter(task => task.id !== id),
      currentTaskId: state.currentTaskId === id ? null : state.currentTaskId,
    }))
  },

  clearTasks: () => set({ tasks: [], currentTaskId: null, hasLoadedConversations: true }),

  setCurrentTask: taskId => set(state => ({
    currentTaskId: taskId,
    pendingContextRefs: state.currentTaskId === taskId ? state.pendingContextRefs : [],
  })),

  loadConversations: async () => {
    const data = await fetchConversations()
    set({
      tasks: data.map(item => normalizeTask(item)),
      hasLoadedConversations: true,
    })
  },

  loadConversation: async (id: string) => {
    const data = await fetchConversation(id)
    const task = normalizeTask(data)
    set(state => ({
      tasks: upsertLocalTask(state.tasks, task),
      currentTaskId: id,
    }))
    return task
  },

  refreshConversation: async (id: string) => {
    const data = await fetchConversation(id)
    const task = normalizeTask(data)
    set(state => ({
      tasks: upsertLocalTask(state.tasks, task),
    }))
    return task
  },

  retryChat: async (id: string) => {
    const task = get().tasks.find(item => item.id === id)
    if (!task || task.mode !== 'chat') return

    const messages = task.messages || []
    const lastUserIndex = [...messages].reverse().findIndex(message => message.role === 'user')
    if (lastUserIndex === -1) return

    const actualUserIndex = messages.length - 1 - lastUserIndex
    const lastUserMessage = messages[actualUserIndex]
    const failedReply = [...messages.slice(actualUserIndex + 1)]
      .reverse()
      .find(message => message.role === 'assistant' && message.error)
    const previousHistory = messages
      .slice(0, actualUserIndex)
      .filter(message => !message.error)
      .map(message => ({
        role: message.role,
        content: message.content,
      }))

    set(state => ({
      tasks: state.tasks.map(item =>
        item.id === id
          ? {
              ...item,
              messages: (item.messages || []).filter(message => message.id !== failedReply?.id),
            }
          : item,
      ),
    }))

    ;(window as any).__NOTEMELD_CHAT_RETRY__ = {
      conversationId: id,
      question: lastUserMessage.content,
      history: previousHistory,
    }
  },
}))
