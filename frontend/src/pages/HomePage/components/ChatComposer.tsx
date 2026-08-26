import { FC, useState, useRef, useEffect, useMemo, KeyboardEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Paperclip,
  Crop,
  ArrowUp,
  ChevronDown,
  Loader2,
  ChevronUp,
  Check,
  X,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { v4 as uuidv4 } from 'uuid'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { generateNote, type GenerateNotePayload } from '@/services/note'
import { resolveAgentApproval, startAgentTurn, streamAgentEvents } from '@/services/agent'
import { createLearningCanvas } from '@/services/learning'
import {
  appendConversationMessage,
  patchConversationMessage,
  patchConversation,
  upsertConversation,
} from '@/services/conversation'
import { ingestUploadedFile, uploadFile, type UploadFileResponse } from '@/services/upload'
import { useTaskStore } from '@/store/taskStore'
import { useModelStore } from '@/store/modelStore'
import { useProviderStore } from '@/store/providerStore'
import { noteStyles as builtinNoteStyles } from '@/constant/note'
import { fetchNoteStyles, type NoteStyleItem } from '@/services/noteStyle'
import { cn } from '@/lib/utils'
import { composeNoteFirstMessage } from '@/pages/HomePage/conversationHelpers'
import { useBackendInitContext } from '@/contexts/BackendInitContext.tsx'
import PlatformLinkCard, {
  detectPlatform,
  formatUrlHost,
  getPlatformLabel,
  type PlatformCookieStatus,
} from '@/pages/HomePage/components/PlatformLinkCard'
import {
  detectUploadedFileKind,
  shouldCollapseComposerTextInput,
} from '@/pages/HomePage/chatComposerHelpers'

export type ComposerMode = 'note' | 'chat' | 'learn'

interface ChatComposerProps {
  /** Hero 模式（中央放大）/ Bottom 模式（聊天底部固定） */
  layout?: 'hero' | 'bottom'
  className?: string
}

const URL_REGEX = /(https?:\/\/[^\s]+)/i
const FILE_ACCEPT =
  'video/*,audio/*,image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp,.md,.markdown,.txt,.pdf,.doc,.docx,.ppt,.pptx,.rtf,text/markdown,text/plain,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation'

/** 风格按钮 icon — 自绘调色盘图标，保持和 Lucide 线性风格一致 */
const StyleIcon: FC<{ className?: string }> = ({ className }) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    aria-hidden
  >
    <path
      d="M12.2 3.25c-5.1 0-9.2 3.66-9.2 8.36 0 4.28 3.48 7.76 7.78 7.76h.74c.76 0 1.22-.82.82-1.47-.58-.94.1-2.16 1.2-2.16h2.13c3.1 0 5.33-2.25 5.33-5.12 0-4.15-3.82-7.37-8.8-7.37Z"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M7.25 11.15h.01M9.15 7.9h.01M13 7.55h.01M16.55 9.35h.01"
      stroke="currentColor"
      strokeWidth="2.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M15.4 15.7c1.45 1.22 2.7 2.9 3.35 5.05"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
)

const ChatComposer: FC<ChatComposerProps> = ({ layout = 'hero', className }) => {
  const [mode, setMode] = useState<ComposerMode>('chat')
  const [text, setText] = useState('')
  const [urlCard, setUrlCard] = useState('')
  const [pendingUploadedFile, setPendingUploadedFile] = useState<UploadFileResponse | null>(null)
  const [uploading, setUploading] = useState(false)
  const [styleValue, setStyleValue] = useState<string>('knowledge_card')
  const [styleTouched, setStyleTouched] = useState(true)
  const [styleOpen, setStyleOpen] = useState(false)
  const [screenshot, setScreenshot] = useState(false)
  const [modelOpen, setModelOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [compactToolbar, setCompactToolbar] = useState(false)
  const [showLinkNoteInput, setShowLinkNoteInput] = useState(false)
  const [urlCookieStatus, setUrlCookieStatus] = useState<PlatformCookieStatus | null>(null)
  const [cookieFallbackPromptOpen, setCookieFallbackPromptOpen] = useState(false)
  const [conversationAssetContentMap, setConversationAssetContentMap] = useState<
    Record<string, string>
  >({})
  const composerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const styleRef = useRef<HTMLDivElement>(null)
  const modelRef = useRef<HTMLDivElement>(null)
  const modeWasExplicitlySelectedRef = useRef(false)
  const learningSubmissionLockRef = useRef(false)

  const {
    createConversation,
    appendMessage,
    updateMessage,
    linkNoteTask,
    loadConversation,
    selectNoteDocument,
    setNoteState,
    learningRequestInFlight,
    beginLearningRequest,
    finishLearningRequest,
    tasks,
    pendingContextRefs,
    removeContextRef,
    clearContextRefs,
  } = useTaskStore()
  const { modelList, loadEnabledModels } = useModelStore()
  const providerList = useProviderStore(state => state.provider)
  const fetchProviderList = useProviderStore(state => state.fetchProviderList)
  const navigate = useNavigate()

  useEffect(() => {
    const handlePrefillResearch = (event: Event) => {
      const prompt = (event as CustomEvent<{ prompt?: string }>).detail?.prompt
      if (!prompt) return
      setText(prompt)
      setMode('learn')
      modeWasExplicitlySelectedRef.current = true
      requestAnimationFrame(() => inputRef.current?.focus())
    }
    window.addEventListener('notemeld:prefill-research', handlePrefillResearch)
    return () => window.removeEventListener('notemeld:prefill-research', handlePrefillResearch)
  }, [])
  const { taskId } = useParams<{ taskId?: string }>()
  const [modelName, setModelName] = useState<string>('')
  const { backendReady } = useBackendInitContext()
  const [stylesList, setStylesList] = useState<{ value: string; label: string }[]>(
    builtinNoteStyles.map(s => ({ value: s.value, label: s.label })),
  )

  useEffect(() => {
    if (!backendReady) return

    void loadEnabledModels()
    void fetchProviderList()
    // 动态拉取风格模板（含用户自建）
    void fetchNoteStyles()
      .then((items: NoteStyleItem[]) => {
        if (items?.length) {
          setStylesList(items.map(it => ({ value: it.id, label: it.name })))
        }
      })
      .catch(() => {
        /* 失败时使用内置 */
      })
  }, [backendReady, loadEnabledModels, fetchProviderList])

  useEffect(() => {
    if (modelList.length && !modelName) {
      setModelName(modelList[0].model_name)
    }
  }, [modelList, modelName])

  useEffect(() => {
    if (modeWasExplicitlySelectedRef.current) return
    if (urlCard) {
      setMode('note')
      return
    }
    if (text.trim()) {
      setMode('chat')
    }
  }, [urlCard, text])

  useEffect(() => {
    const el = composerRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      setCompactToolbar(entry.contentRect.width < 520)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const urlChip = urlCard
  const plainText = text.trim()
  const hasLearningGoal = mode === 'learn' && !!plainText
  const canSubmit = (!!plainText || !!urlChip || !!pendingUploadedFile) && !uploading && !submitting && (mode !== 'learn' || (hasLearningGoal && !learningRequestInFlight))
  const currentConversation = taskId ? tasks.find(t => t.id === taskId) : null
  const collapseTextInput = mode !== 'learn'
    && shouldCollapseComposerTextInput({ text, urlCard })
    && !showLinkNoteInput

  /** 关闭 popover when click outside */
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (styleRef.current && !styleRef.current.contains(e.target as Node)) {
        setStyleOpen(false)
      }
      if (modelRef.current && !modelRef.current.contains(e.target as Node)) {
        setModelOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const removeUrl = () => {
    setUrlCard('')
    setShowLinkNoteInput(false)
  }

  const removePendingUpload = () => {
    setPendingUploadedFile(null)
  }

  const selectMode = (nextMode: ComposerMode) => {
    modeWasExplicitlySelectedRef.current = true
    if (mode === 'learn' && nextMode !== 'learn') {
      const match = text.match(URL_REGEX)
      if (match) {
        setUrlCard(match[0])
        setText(text.replace(match[0], '').trimStart())
        setShowLinkNoteInput(false)
      }
    }
    setMode(nextMode)
  }

  const handleTextChange = (value: string) => {
    if (mode === 'learn') {
      setText(value)
      return
    }
    const match = value.match(URL_REGEX)
    if (match) {
      setUrlCard(match[0])
      setText(value.replace(match[0], '').trimStart())
      setShowLinkNoteInput(false)
      return
    }
    setText(value)
  }

  const deriveUploadTitle = (fileName: string) => fileName.replace(/\.[^.]+$/, '') || '未命名文件'

  const ensureConversation = async (nextMode: ComposerMode, fallbackTitle: string) => {
    if (currentConversation?.id) return currentConversation.id
    const persistedMode = nextMode === 'learn' ? 'chat' : nextMode
    const conversationId = createConversation({
      mode: persistedMode,
      title: fallbackTitle,
    })
    await upsertConversation(conversationId, {
      id: conversationId,
      mode: persistedMode,
      title: fallbackTitle,
      status: 'SUCCESS',
      noteState: persistedMode === 'chat' ? 'none' : 'ready',
    })
    return conversationId
  }

  const appendNoteSeedMessage = async (conversationId: string, source: string, extras: string) => {
    const content = composeNoteFirstMessage(source, extras)
    const message = {
      id: uuidv4(),
      role: 'user' as const,
      message_type: 'user_input' as const,
      content,
      meta: { source, extras },
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    appendMessage(conversationId, message)
    await appendConversationMessage(conversationId, message)
    return message
  }

  const buildNotePayload = ({
    conversationId,
    platform,
    providerId,
    extras,
    forceWebFallback = false,
  }: {
    conversationId: string
    platform: string
    providerId: string
    extras: string
    forceWebFallback?: boolean
  }): GenerateNotePayload => ({
    video_url: urlChip,
    platform,
    quality: 'medium',
    model_name: modelName,
    provider_id: providerId,
    style: styleValue,
    format: screenshot ? ['summary', 'toc', 'screenshot', 'link'] : ['summary', 'toc'],
    extras,
    screenshot,
    link: screenshot,
    video_understanding: screenshot,
    enable_refine_engine: true,
    vision_mode: 'fixed_interval',
    max_sampling_points: 8,
    video_interval: 6,
    grid_size: [2, 2],
    conversation_id: conversationId,
    force_web_fallback: forceWebFallback,
  })

  const buildChatQuestion = (uploaded?: UploadFileResponse | null) => {
    if (urlChip) return composeNoteFirstMessage(urlChip, plainText)
    if (uploaded && plainText) {
      return `基于我上传的文件《${deriveUploadTitle(uploaded.file_name)}》，${plainText}`
    }
    if (uploaded) {
      return `请阅读我上传的文件《${deriveUploadTitle(uploaded.file_name)}》，提炼重点并给出摘要。`
    }
    return plainText
  }

  const submitUploadedMediaNote = async (uploaded: UploadFileResponse) => {
    const matchedModel = ensureModel()
    if (!matchedModel) return
    if (!ensureBackendReady()) return
    const extras = plainText
    const fallbackTitle = extras?.slice(0, 24) || deriveUploadTitle(uploaded.file_name)
    const conversationId = await ensureConversation('note', fallbackTitle)
    await appendNoteSeedMessage(conversationId, uploaded.url, extras)

    const payload: GenerateNotePayload = {
      video_url: uploaded.url,
      platform: 'local',
      quality: 'medium',
      model_name: modelName,
      provider_id: matchedModel.provider_id,
      style: styleValue,
      format: screenshot ? ['summary', 'toc', 'screenshot', 'link'] : ['summary', 'toc'],
      extras,
      screenshot,
      link: screenshot,
      video_understanding: screenshot,
      enable_refine_engine: true,
      vision_mode: 'fixed_interval',
      max_sampling_points: 8,
      video_interval: 6,
      grid_size: [2, 2],
      conversation_id: conversationId,
    }

    await upsertConversation(conversationId, {
      id: conversationId,
      mode: 'note',
      title: fallbackTitle,
      status: 'PENDING',
      noteState: 'generating',
      platform: 'local',
      linkedNoteTaskId: '',
      formData: payload,
    })
    const data = await generateNote(payload)
    if (!data?.task_id) throw new Error('笔记生成任务提交失败')
    linkNoteTask(conversationId, data.task_id, payload, 'local')
    setNoteState(conversationId, 'generating')
    resetInput()
    navigate(`/notes/${conversationId}`)
  }

  const submitUploadedNote = async (uploaded: UploadFileResponse) => {
    const inferredKind = detectUploadedFileKind({
      fileName: uploaded.file_name,
      contentType: uploaded.content_type,
    })

    if (mode === 'note' && (inferredKind === 'video' || inferredKind === 'audio')) {
      await submitUploadedMediaNote(uploaded)
      return
    }

    if (
      mode === 'note'
      && (inferredKind === 'document' || inferredKind === 'image')
      && !ensureModel()
    ) {
      return
    }

    if (!ensureBackendReady()) return

    const fallbackTitle =
      mode === 'chat'
        ? plainText.slice(0, 24) || deriveUploadTitle(uploaded.file_name)
        : plainText.slice(0, 24) || deriveUploadTitle(uploaded.file_name)
    const conversationId = await ensureConversation(mode, fallbackTitle)
    const documentModel =
      mode === 'note' && (inferredKind === 'document' || inferredKind === 'image') ? ensureModel() : null

    if (mode === 'note' && (inferredKind === 'document' || inferredKind === 'image')) {
      if (!documentModel) return
      await appendNoteSeedMessage(conversationId, uploaded.url, plainText)
    }

    const data = await ingestUploadedFile({
      file_url: uploaded.url,
      file_name: uploaded.file_name,
      content_type: uploaded.content_type,
      mode: mode === 'learn' ? 'chat' : mode,
      conversation_id: conversationId,
      model_name: documentModel ? modelName : undefined,
      provider_id: documentModel?.provider_id,
      format:
        mode === 'note' && (inferredKind === 'document' || inferredKind === 'image')
          ? screenshot
            ? ['summary', 'toc', 'screenshot', 'link']
            : ['summary', 'toc']
          : undefined,
      style:
        mode === 'note' && (inferredKind === 'document' || inferredKind === 'image')
          ? styleValue
          : undefined,
      extras: mode === 'note' ? plainText : undefined,
    })

    const loadedConversation = await loadConversation(data.conversation_id)

    if (data.action === 'imported_note') {
      const documentTaskId =
        data.document_task_id
        || data.note_id
        || loadedConversation?.activeDocumentTaskId
        || loadedConversation?.documents?.find(document => document.content)?.taskId
      if (documentTaskId) {
        selectNoteDocument(data.conversation_id, documentTaskId)
      }
      resetInput()
      navigate(`/notes/${data.conversation_id}`)
      toast.success('笔记已导入')
      return
    }

    if (data.action === 'note_task' && data.task_id) {
      linkNoteTask(
        data.conversation_id,
        data.task_id,
        {
          video_url: uploaded.url,
          platform: 'uploaded_document',
          quality: 'medium',
          model_name: modelName,
          provider_id: documentModel?.provider_id || '',
          style: styleValue,
          extras: plainText,
        },
        'uploaded_document',
      )
      setNoteState(data.conversation_id, 'generating')
      const existingDocumentTaskId =
        loadedConversation?.activeDocumentTaskId
        || loadedConversation?.documents?.find(document => document.content)?.taskId
      if (existingDocumentTaskId) {
        selectNoteDocument(data.conversation_id, existingDocumentTaskId)
      }
      resetInput()
      navigate(`/notes/${data.conversation_id}`)
      toast.success(
        data.message || (inferredKind === 'image' ? '图片笔记任务已提交' : '文档笔记任务已提交'),
      )
    }
  }

  const onPickFile = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = FILE_ACCEPT
    input.onchange = async e => {
      const f = (e.target as HTMLInputElement).files?.[0]
      if (!f) return

      setUploading(true)
      try {
        const formData = new FormData()
        formData.append('file', f)
        const uploaded = await uploadFile(formData)
        setPendingUploadedFile(uploaded)
      } catch (err) {
        toast.error((err as any)?.detail || (err as any)?.msg || '文件处理失败，请重试')
      } finally {
        setUploading(false)
      }
    }
    input.click()
  }

  const ensureModel = () => {
    if (!modelName) {
      toast.error('请先在设置中添加模型')
      navigate('/settings/model')
      return null
    }
    const matchedModel = modelList.find(m => m.model_name === modelName)
    if (!matchedModel) {
      toast.error('当前模型已失效，请重新选择')
      return null
    }
    return matchedModel
  }

  const ensureBackendReady = () => {
    if (!backendReady) {
      toast.error('后端尚未就绪，请稍后重试或点击顶部提示中的重试')
      return false
    }

    return true
  }

  const resetInput = () => {
    setText('')
    setUrlCard('')
    setPendingUploadedFile(null)
    setShowLinkNoteInput(false)
    setUrlCookieStatus(null)
    setCookieFallbackPromptOpen(false)
    modeWasExplicitlySelectedRef.current = false
  }

  const runChatRequest = async ({
    conversationId,
    question,
    linkedTaskId,
    assetContent,
    contextRefs,
  }: {
    conversationId: string
    question: string
    linkedTaskId?: string
    assetContent?: string
    contextRefs?: typeof pendingContextRefs
  }) => {
    const matchedModel = ensureModel()
    if (!matchedModel) return
    if (!ensureBackendReady()) return

    const input: { text: string; attachments?: Array<{ type: string; content: string; source?: string }>; context_refs?: typeof contextRefs } = {
      text: question,
    }
    if (assetContent) {
      input.attachments = [{ type: 'text', content: assetContent, source: 'upload_asset' }]
    }
    if (contextRefs?.length) {
      input.context_refs = contextRefs as typeof contextRefs
    }

    const assistantMessageId = uuidv4()
    const assistantMessage = {
      id: assistantMessageId,
      role: 'assistant' as const,
      message_type: 'assistant_text' as const,
      content: '',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      isStreaming: true,
    }

    appendMessage(conversationId, assistantMessage)

    let finalAnswer = ''
    let finalSources: any[] = []
    let streamError = ''

    const turn = await startAgentTurn(conversationId, {
      input,
      model: modelName,
      idempotency_key: assistantMessageId,
      linked_task_id: linkedTaskId,
      asset_content: assetContent,
      context_refs: contextRefs,
    })
    // Open the conversation as soon as the turn is accepted. Provider errors
    // should still leave the user on the conversation with a visible failure.
    navigate(`/notes/${conversationId}`)

    for await (const event of streamAgentEvents(turn.data.turn_id)) {
      const payload = event.payload || {}
      if (event.type === 'message.delta' && typeof payload.delta === 'string') {
        finalAnswer += payload.delta
        updateMessage(conversationId, assistantMessageId, {
          content: finalAnswer,
          error: false,
          isStreaming: true,
        })
      } else if (event.type === 'message.completed') {
        const completedContent = payload.content
        if (typeof completedContent === 'string' && completedContent) {
          finalAnswer = completedContent
          updateMessage(conversationId, assistantMessageId, {
            content: finalAnswer,
            error: false,
            isStreaming: true,
          })
        }
      } else if (event.type === 'turn.succeeded') {
        const terminalAnswer = payload.answer || payload.content
        if (typeof terminalAnswer === 'string' && terminalAnswer) {
          finalAnswer = terminalAnswer
        }
        finalSources = Array.isArray(payload.sources) ? payload.sources : []
      } else if (event.type === 'turn.failed' || event.type === 'turn.cancelled' || event.type === 'turn.interrupted') {
        const error = payload.error
        streamError = typeof error === 'object' && error && 'message' in error ? String(error.message) : 'Agent 执行失败'
      } else if (event.type === 'approval.required') {
        const approvalId = String(payload.approval_id || '')
        if (!approvalId) {
          streamError = 'Agent 审批事件缺少 approval_id'
          continue
        }
        const summary = String(payload.summary || 'Agent 请求执行受保护操作')
        const risk = String(payload.risk || 'unknown')
        const approved = window.confirm(`${summary}\n\n风险级别：${risk}\n\n是否批准继续执行？`)
        try {
          await resolveAgentApproval(approvalId, approved ? 'approve' : 'deny')
        } catch {
          toast.error('审批提交失败，可从另一个 NoteMeld 入口重试')
        }
      } else if (event.type === 'tool.started' || event.type === 'tool.progress' || event.type === 'tool.completed') {
        const toolName = String(payload.tool_name || payload.name || '工具执行')
        const cardMessageId = `agent-tool-${event.turn_id}`
        const existing = useTaskStore.getState().tasks
          .find(t => t.id === conversationId)
          ?.messages?.find(m => m.id === cardMessageId)
        const cardMeta = { tool_name: toolName, event_type: event.type, progress: payload.progress }
        if (existing) {
          updateMessage(conversationId, cardMessageId, { meta: { ...(existing.meta || {}), ...cardMeta }, updatedAt: new Date().toISOString() })
        } else {
          appendMessage(conversationId, {
            id: cardMessageId,
            role: 'assistant',
            message_type: 'task_card',
            content: toolName,
            meta: cardMeta,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          })
        }
      }
    }

    if (streamError) {
      updateMessage(conversationId, assistantMessageId, {
        content: streamError,
        error: true,
        isStreaming: false,
      })
      throw new Error(streamError)
    }

    updateMessage(conversationId, assistantMessageId, {
      content: finalAnswer,
      sources: finalSources,
      error: false,
      isStreaming: false,
    })
    // Assistant content is owned by the Host; the UI keeps this local until
    // the canonical conversation reload endpoint returns it.
  }

  const submitChat = async (uploaded?: UploadFileResponse | null) => {
    const matchedModel = ensureModel()
    if (!matchedModel) return
    if (!ensureBackendReady()) return

    const question = buildChatQuestion(uploaded)
    const initialUserMessage = {
      id: uuidv4(),
      role: 'user' as const,
      message_type: 'user_input' as const,
      content: question,
      meta: {
        extras: plainText,
        url: urlChip,
        uploaded_file_name: uploaded?.file_name || '',
        uploaded_file_url: uploaded?.url || '',
        context_refs: pendingContextRefs,
      },
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    const fallbackTitle =
      question.slice(0, 24)
      || (uploaded ? deriveUploadTitle(uploaded.file_name) : '')
      || '未命名对话'
    const conversationId =
      currentConversation?.id ||
      createConversation({
        mode: 'chat',
        firstMessage: question,
        title: fallbackTitle,
      })

    if (currentConversation) {
      appendMessage(conversationId, initialUserMessage)
      // The Agent v1 Turn command persists the user message in the Host.
    } else {
      await upsertConversation(conversationId, {
        id: conversationId,
        mode: 'chat',
        title: fallbackTitle,
        status: 'SUCCESS',
        noteState: 'none',
      })
      // The Agent v1 Turn command persists the user message in the Host.
    }

    try {
      setSubmitting(true)
      let assetContent = conversationAssetContentMap[conversationId]
      if (uploaded) {
        const data = await ingestUploadedFile({
          file_url: uploaded.url,
          file_name: uploaded.file_name,
          content_type: uploaded.content_type,
          mode: 'chat',
          conversation_id: conversationId,
        })
        if (data.action !== 'chat_asset') {
          throw new Error(data.message || '文件加入聊天上下文失败')
        }
        if (data.asset_content) {
          assetContent = data.asset_content
          setConversationAssetContentMap(prev => ({
            ...prev,
            [conversationId]: data.asset_content || '',
          }))
          if (
            detectUploadedFileKind({
              fileName: uploaded.file_name,
              contentType: uploaded.content_type,
            }) === 'image'
          ) {
            toast.success('图片文字已提取，可直接继续提问')
          }
        }
      }

      const linkedTaskId =
        currentConversation?.linkedNoteTaskId || currentConversation?.id

      resetInput()
      await runChatRequest({
        conversationId,
        question,
        linkedTaskId,
        assetContent,
        contextRefs: pendingContextRefs,
      })
      clearContextRefs()
    } catch (err: any) {
      toast.error(err?.detail || err?.message || '聊天失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }

  const submitLearning = async () => {
    if (learningSubmissionLockRef.current || !ensureBackendReady()) return
    if (!beginLearningRequest()) {
      toast('已有学习空间正在生成，可稍后从侧栏打开')
      return
    }
    learningSubmissionLockRef.current = true
    setSubmitting(true)
    let learningConversationId = ''
    let learningProgressMessageId = ''
    let learningCanvasCreated = false
    const learningOriginPath = window.location.pathname

    try {
      const goal = plainText
      if (!goal) {
        toast.error('请描述你想真正学会的主题')
        return
      }
      const fallbackTitle = goal.slice(0, 24) || '未命名学习主题'
      const conversationId = await ensureConversation('learn', fallbackTitle)
      learningConversationId = conversationId
      const userMessage = {
        id: uuidv4(),
        role: 'user' as const,
        message_type: 'user_input' as const,
        content: goal,
        meta: {
          intent: 'learn',
          extras: plainText,
          context_refs: pendingContextRefs,
        },
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      }
      const progressMessage = {
        id: uuidv4(),
        role: 'assistant' as const,
        message_type: 'assistant_text' as const,
        content: '正在结合 NoteMeld、本地知识、学术论文和 GitHub 构建学习空间…',
        status: 'running' as const,
        meta: { intent: 'learn', kind: 'learning_build_progress' },
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      }
      learningProgressMessageId = progressMessage.id

      appendMessage(conversationId, userMessage)
      appendMessage(conversationId, progressMessage)
      await appendConversationMessage(conversationId, userMessage)
      await appendConversationMessage(conversationId, progressMessage)
      const matchedModel = ensureModel()
      const learningCanvas = await createLearningCanvas(conversationId, {
        goal,
        provider_id: matchedModel?.provider_id,
        model_name: modelName,
        context_refs: pendingContextRefs,
      })
      learningCanvasCreated = true
      const needsClarification = learningCanvas.status === 'clarifying'
      const projectionUnavailable = learningCanvas.external_errors?.some(
        error => error.code === 'projection_save_failed',
      )
      const completionContent = needsClarification
        ? '需要先确认研究对象。'
        : projectionUnavailable
          ? '研究笔记已保存，白板暂时不可用。'
          : '研究笔记与白板已生成。'
      updateMessage(conversationId, progressMessage.id, {
        content: completionContent,
        status: 'success',
        error: false,
        updatedAt: new Date().toISOString(),
      })
      await patchConversationMessage(conversationId, progressMessage.id, {
        content: completionContent,
        status: 'success',
        error: false,
      }).catch(error => {
        console.warn('学习空间已生成，但构建状态消息更新失败', error)
      })
      resetInput()
      clearContextRefs()
      setMode('chat')
      await loadConversation(conversationId).catch(error => {
        console.warn('学习空间已生成，但会话刷新失败', error)
      })
      const shouldAutoNavigate = window.location.pathname === learningOriginPath
      if (shouldAutoNavigate) {
        try {
          navigate(`/notes/${conversationId}`)
        } catch (error) {
          console.warn('学习空间已生成，但自动打开会话失败', error)
        }
      }
      toast.success(
        needsClarification
          ? '请先在对话中确认研究对象'
          : projectionUnavailable
            ? '研究笔记已保存，白板暂时不可用'
          : shouldAutoNavigate
            ? '研究笔记与白板已生成'
            : '研究结果已生成，可从侧栏打开',
      )
    } catch (err: any) {
      if (learningCanvasCreated) {
        toast.success('学习空间已生成，可从侧栏打开')
      } else if (learningConversationId && learningProgressMessageId) {
        const failureContent = err?.detail || err?.msg || err?.message || '学习空间生成失败，请重试'
        updateMessage(learningConversationId, learningProgressMessageId, {
          content: failureContent,
          status: 'failed',
          error: true,
        })
        await patchConversationMessage(learningConversationId, learningProgressMessageId, {
          content: failureContent,
          status: 'failed',
          error: true,
        }).catch(() => undefined)
      }
      if (!learningCanvasCreated) {
        toast.error(err?.detail || err?.msg || err?.message || '学习空间生成失败，请重试')
      }
    } finally {
      learningSubmissionLockRef.current = false
      finishLearningRequest()
      setSubmitting(false)
    }
  }

  useEffect(() => {
    const retryPayload = (window as any).__NOTEMELD_CHAT_RETRY__
    if (!retryPayload || retryPayload.conversationId !== taskId) return
    ;(window as any).__NOTEMELD_CHAT_RETRY__ = null

    setSubmitting(true)
    runChatRequest({
      conversationId: retryPayload.conversationId,
      question: retryPayload.question,
      linkedTaskId: currentConversation?.linkedNoteTaskId || currentConversation?.id,
      assetContent: conversationAssetContentMap[retryPayload.conversationId],
      contextRefs: pendingContextRefs,
    })
      .catch((err: any) => {
        toast.error(err?.message || '聊天失败，请重试')
      })
      .finally(() => {
        setSubmitting(false)
      })
  }, [
    taskId,
    currentConversation?.id,
    currentConversation?.linkedNoteTaskId,
    modelName,
    conversationAssetContentMap,
  ])

  const submitNote = async ({ forceWebFallback = false }: { forceWebFallback?: boolean } = {}) => {
    if (pendingUploadedFile) {
      await submitUploadedNote(pendingUploadedFile)
      return
    }

    const url = urlChip
    const extras = plainText

    if (!url) {
      toast.error('请先粘贴链接')
      return
    }
    const matchedModel = ensureModel()
    if (!matchedModel) return
    if (!ensureBackendReady()) return

    const platform = detectPlatform(url)
    const shouldConfirmCookieFallback =
      !forceWebFallback
      && urlCookieStatus?.platform === platform
      && urlCookieStatus.cookieMissing

    if (shouldConfirmCookieFallback) {
      setCookieFallbackPromptOpen(true)
      return
    }

    const effectivePlatform = forceWebFallback ? 'web_link' : platform
    const userInputContent = composeNoteFirstMessage(url, extras)
    const conversationId =
      currentConversation?.id ||
      createConversation({
        mode: 'note',
        title: extras?.slice(0, 24) || formatUrlHost(url),
        platform: effectivePlatform,
      })
    const firstMessage = {
      id: uuidv4(),
      role: 'user' as const,
      message_type: 'user_input' as const,
      content: userInputContent,
      meta: {
        url,
        platform,
        effective_platform: effectivePlatform,
        extras,
        force_web_fallback: forceWebFallback,
      },
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }

    const payload = buildNotePayload({
      conversationId,
      platform,
      providerId: matchedModel.provider_id,
      extras,
      forceWebFallback,
    })

    try {
      setSubmitting(true)
      await upsertConversation(conversationId, {
        id: conversationId,
        mode: 'note',
        title: extras?.slice(0, 24) || formatUrlHost(url),
        status: 'PENDING',
        noteState: 'generating',
        platform: effectivePlatform,
        linkedNoteTaskId: '',
        formData: payload,
      })
      await appendConversationMessage(conversationId, firstMessage)
      appendMessage(conversationId, firstMessage)
      const data = await generateNote(payload)
      if (!data?.task_id) throw new Error('笔记生成任务提交失败')
      linkNoteTask(conversationId, data.task_id, payload, effectivePlatform)
      setNoteState(conversationId, 'generating')
      resetInput()
      navigate(`/notes/${conversationId}`)
    } catch (err: any) {
      setNoteState(conversationId, 'failed')
      try {
        await patchConversation(conversationId, {
          status: 'FAILED',
          noteState: 'failed',
          message: err?.detail || err?.message || '提交失败，请重试',
        })
      } catch {
        // 保持本地失败态，避免覆盖原始错误提示
      }
      toast.error(err?.detail || err?.message || '提交失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }

  const onSubmit = async () => {
    if (!canSubmit) return
    if (mode === 'chat') {
      await submitChat(pendingUploadedFile)
      return
    }
    if (mode === 'learn') {
      await submitLearning()
      return
    }
    await submitNote()
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      if (canSubmit) onSubmit()
    }
  }

  const styleLabel = stylesList.find(s => s.value === styleValue)?.label || '精简'

  /** 按 provider_id 分组 modelList，组内保持原顺序 */
  const groupedModels = useMemo(() => {
    const groups = new Map<string, typeof modelList>()
    modelList.forEach(m => {
      const list = groups.get(m.provider_id) || []
      list.push(m)
      groups.set(m.provider_id, list)
    })
    return Array.from(groups.entries()).map(([providerId, items]) => ({
      providerId,
      providerName:
        providerList.find(p => p.id === providerId)?.name || '未知来源',
      items,
    }))
  }, [modelList, providerList])
  const hideToolText = layout === 'bottom' && compactToolbar

  return (
    <div
      ref={composerRef}
      className={cn(
        'rounded-xl border border-border-subtle bg-white shadow-[0_4px_20px_rgba(15,23,42,0.04)]',
        className,
      )}
    >
      {/* URL 卡片 + 文本 */}
      {pendingContextRefs.length > 0 && (
        <div className="flex flex-wrap gap-2 border-b border-border-subtle/60 px-4 py-2">
          {pendingContextRefs.map(reference => (
            <div key={reference.id} className="flex max-w-[280px] items-center gap-2 rounded-md bg-primary-light/60 px-2.5 py-1.5 text-[11px] text-primary">
              <span className="truncate">
                引用：{reference.label}
                {reference.type === 'whiteboard_selection'
                  ? ` · ${reference.card_ids.length} 张卡片 · ${reference.relation_ids.length} 条关系`
                  : ''}
              </span>
              <button type="button" onClick={() => removeContextRef(reference.id)} aria-label="移除引用"><X className="h-3 w-3" /></button>
            </div>
          ))}
        </div>
      )}
      <div
        className={cn(
          'flex gap-2 px-4 pt-3',
          collapseTextInput ? 'items-center pb-1' : 'items-start',
        )}
      >
        {pendingUploadedFile && mode !== 'learn' && (
          <div className="flex max-w-[320px] items-center gap-2 rounded-lg border border-border-subtle bg-surface-container-low px-3 py-2 text-[12px] text-on-surface">
            <Paperclip className="h-3.5 w-3.5 shrink-0 text-on-surface-variant" />
            <span className="truncate">{pendingUploadedFile.file_name}</span>
            <button
              type="button"
              onClick={removePendingUpload}
              className="rounded p-0.5 text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface"
              aria-label="移除上传文件"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
        {urlChip && mode !== 'learn' && (
          <PlatformLinkCard
            url={urlChip}
            onRemove={removeUrl}
            onCookieStatusChange={setUrlCookieStatus}
            className={cn('mt-0.5 max-w-[320px]', collapseTextInput && 'max-w-[420px] flex-1')}
          />
        )}
        {collapseTextInput ? (
          <button
            type="button"
            onClick={() => {
              setShowLinkNoteInput(true)
              requestAnimationFrame(() => inputRef.current?.focus())
            }}
            className="shrink-0 rounded-md px-2 py-1 text-[12px] text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface"
          >
            添加说明
          </button>
        ) : (
          <textarea
            ref={inputRef}
            value={text}
            rows={1}
            placeholder={
              mode === 'learn'
                ? '描述你想真正学会的主题，例如：理解并能实现 AI Agent…'
                : '粘一条链接，上传一个文件，或描述你想沉淀的主题...'
            }
            className="min-h-8 flex-1 resize-none border-0 bg-transparent py-1 text-[14px] leading-6 text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none"
            onChange={e => {
              handleTextChange(e.target.value)
              const el = e.target
              el.style.height = 'auto'
              el.style.height = Math.min(el.scrollHeight, 160) + 'px'
            }}
            onKeyDown={onKeyDown}
          />
        )}
      </div>

      {/* 工具条 */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1">
          {/* 上传 */}
          <button
            onClick={onPickFile}
            disabled={uploading || mode === 'learn'}
            className="flex h-9 items-center gap-1.5 rounded-md px-2 text-[13px] text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface disabled:opacity-50 md:h-8"
          >
            {uploading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Paperclip className="h-3.5 w-3.5" />
            )}
            <span className={cn(hideToolText && 'hidden')}>上传文件</span>
          </button>

          {/* Chat / Note / Learn 模式切换 */}
          <ModeSwitch mode={mode} onChange={selectMode} />

          {/* 仅 Note 模式显示风格 + 截图总结 */}
          {mode === 'note' && (
            <>
              {/* 风格 */}
              <div ref={styleRef} className="relative">
                <button
                  onClick={() => setStyleOpen(v => !v)}
                  className={cn(
                    'inline-flex h-9 items-center gap-1.5 rounded-md px-2 text-[13px] leading-none transition-colors hover:bg-surface-container md:h-8',
                    styleTouched
                      ? 'text-primary font-medium'
                      : 'text-on-surface-variant hover:text-on-surface',
                  )}
                >
                  <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center">
                    <StyleIcon className="h-[22px] w-[22px]" />
                  </span>
                  <span className={cn('leading-none', hideToolText && 'hidden')}>
                    {styleTouched ? styleLabel : '选择风格'}
                  </span>
                </button>
                {styleOpen && (
                  <div className="absolute bottom-full left-0 z-30 mb-2 max-h-[280px] w-44 overflow-auto rounded-lg border border-border-subtle bg-white p-1 shadow-lg">
                    {stylesList.map(s => (
                      <button
                        key={s.value}
                        onClick={() => {
                          setStyleValue(s.value)
                          setStyleTouched(true)
                          setStyleOpen(false)
                        }}
                        className={cn(
                          'flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-[13px] transition-colors',
                          styleTouched && styleValue === s.value
                            ? 'bg-primary-light text-primary font-medium'
                            : 'text-on-surface hover:bg-surface-container-low',
                        )}
                      >
                        <span>{s.label}</span>
                        {styleTouched && styleValue === s.value && (
                          <Check className="h-3.5 w-3.5" />
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* 截图总结 */}
              <button
                onClick={() => setScreenshot(v => !v)}
                className={cn(
                  'inline-flex h-9 items-center gap-1.5 rounded-md px-2 text-[13px] leading-none transition-colors md:h-8',
                  screenshot
                    ? 'bg-primary-light text-primary font-medium'
                    : 'text-on-surface-variant hover:bg-surface-container hover:text-on-surface',
                )}
              >
                <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center">
                  <Crop className="h-4 w-4" />
                </span>
                <span className={cn('leading-none', hideToolText && 'hidden')}>截图总结</span>
              </button>
            </>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* 模型 */}
          <div ref={modelRef} className="relative">
            <button
              onClick={() => setModelOpen(v => !v)}
              className="flex h-9 items-center gap-1.5 rounded-md border border-border-subtle bg-white px-2.5 text-[12px] text-on-surface transition-colors hover:bg-surface-container-low md:h-8"
            >
              <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-primary/10">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" />
              </span>
              <span className={cn('max-w-[140px] truncate font-medium', hideToolText && 'hidden')}>
                {modelName || '请选择模型'}
              </span>
              {modelOpen ? (
                <ChevronUp className="h-3.5 w-3.5" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5" />
              )}
            </button>
            {modelOpen && (
              <div className="absolute bottom-full right-0 z-30 mb-2 max-h-72 w-60 overflow-auto rounded-lg border border-border-subtle bg-white p-1 shadow-lg">
                {modelList.length === 0 ? (
                  <button
                    type="button"
                    onClick={() => navigate('/settings/model')}
                    className="w-full rounded-md px-3 py-3 text-left text-[12px] text-muted-foreground transition-colors hover:bg-primary-light hover:text-primary"
                  >
                    还没有可用模型，点击去设置 AI 模型
                  </button>
                ) : (
                  groupedModels.map((group, gi) => (
                    <div
                      key={group.providerId}
                      className={cn(gi > 0 && 'mt-1 border-t border-border-subtle pt-1')}
                    >
                      <div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-on-surface-variant/70">
                        {group.providerName}
                      </div>
                      {group.items.map(m => (
                        <button
                          key={m.id}
                          onClick={() => {
                            setModelName(m.model_name)
                            setModelOpen(false)
                          }}
                          className={cn(
                            'flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-[12px] transition-colors',
                            modelName === m.model_name
                              ? 'bg-primary-light text-primary font-medium'
                              : 'text-on-surface hover:bg-surface-container-low',
                          )}
                        >
                          <span className="truncate">{m.model_name}</span>
                          {modelName === m.model_name && <Check className="h-3 w-3" />}
                        </button>
                      ))}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* 发送 */}
          <Button
            onClick={onSubmit}
            disabled={!canSubmit}
            className={cn(
              'h-9 w-10 rounded-md p-0 transition-colors md:h-8 md:w-9',
              canSubmit
                ? 'bg-primary hover:bg-primary-strong'
                : 'cursor-not-allowed bg-surface-container text-on-surface-variant hover:bg-surface-container',
            )}
            aria-label="发送"
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ArrowUp className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
      <Dialog open={cookieFallbackPromptOpen} onOpenChange={setCookieFallbackPromptOpen}>
        <DialogContent className="max-w-[520px] p-0" showCloseButton>
          <DialogHeader className="gap-3 px-6 pb-4 pt-6 text-left">
            <DialogTitle className="text-[18px] font-semibold text-on-surface">
              未设置 {getPlatformLabel(urlCookieStatus?.platform || 'web_link')} Cookie
            </DialogTitle>
            <DialogDescription className="text-[14px] leading-6 text-on-surface-variant">
              当前链接所在平台没有设置 Cookie，无法解析视频内容，只能解析网页内容。你可以先去设置 Cookie，或继续发送并按普通网页处理。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex-row items-center justify-between border-t border-border-subtle px-6 py-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setCookieFallbackPromptOpen(false)
                void submitNote({ forceWebFallback: true })
              }}
            >
              继续发送
            </Button>
            <Button
              type="button"
              onClick={() => {
                const targetPlatform = urlCookieStatus?.platform
                setCookieFallbackPromptOpen(false)
                if (targetPlatform) {
                  navigate(`/settings/download/${targetPlatform}`)
                }
              }}
            >
              去设置
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

const ModeSwitch: FC<{ mode: ComposerMode; onChange: (m: ComposerMode) => void }> = ({
  mode,
  onChange,
}) => {
  return (
    <div className="ml-1 flex h-7 items-center rounded-md border border-border-subtle bg-surface-container-low p-0.5">
      <button
        onClick={() => onChange('chat')}
        className={cn(
          'h-6 rounded px-2 text-[12px] font-medium transition-colors',
          mode === 'chat' ? 'bg-white text-primary shadow-sm' : 'text-on-surface-variant',
        )}
      >
        聊天
      </button>
      <button
        onClick={() => onChange('note')}
        className={cn(
          'h-6 rounded px-2 text-[12px] font-medium transition-colors',
          mode === 'note' ? 'bg-white text-primary shadow-sm' : 'text-on-surface-variant',
        )}
      >
        笔记
      </button>
      <button
        onClick={() => onChange('learn')}
        className={cn(
          'h-6 rounded px-2 text-[12px] font-medium transition-colors',
          mode === 'learn' ? 'bg-white text-primary shadow-sm' : 'text-on-surface-variant',
        )}
      >
        学习
      </button>
    </div>
  )
}

export default ChatComposer
