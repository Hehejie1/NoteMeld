import request from '@/utils/request'

export interface ConversationPayload {
  id: string
  mode: 'chat' | 'note'
  title?: string
  status?: string
  message?: string
  platform?: string
  linkedNoteTaskId?: string
  noteState?: 'none' | 'generating' | 'ready' | 'failed'
  formData?: Record<string, any>
  transcript?: Record<string, any>
  audioMeta?: Record<string, any>
  markdown?: any
}

export type ConversationPatchPayload = Partial<Omit<ConversationPayload, 'id'>>

export interface ConversationDocumentPayload {
  taskId: string
  title: string
  content?: string
  sourceUrl?: string
  platform?: string
  modelName?: string
  style?: string
  status?: string
  wikiStatus?: string
  createdAt?: string
  updatedAt?: string
}

export interface ConversationMessagePayload {
  id: string
  role: 'user' | 'assistant' | 'system'
  message_type?: 'user_input' | 'assistant_text' | 'note_progress' | 'note_result' | 'system_error'
  content: string
  status?: 'pending' | 'running' | 'success' | 'failed'
  meta?: Record<string, any>
  createdAt?: string
  updatedAt?: string
  sources?: Array<Record<string, any>>
  error?: boolean
}

export interface ConversationImportPayload {
  import_mode: 'chat_asset' | 'note'
  conversation_id?: string
  title?: string
  content: string
  format?: string
  file_name?: string
  source_url?: string
  source_type?: string
  tags?: string[]
  metadata?: Record<string, any>
}

export interface ConversationImportResult {
  conversation_id: string
  conversation_title: string
  import_mode: 'chat_asset' | 'note'
  asset_id?: string
  note_id?: string
  document_task_id?: string
  message_id?: string
  status: string
  wiki_status: string
}

export const fetchConversations = async () => {
  return await request.get<any, ConversationPayload[]>('/conversations')
}

export const fetchConversation = async (conversationId: string) => {
  return await request.get<
    any,
    ConversationPayload & {
      messages?: ConversationMessagePayload[]
      documents?: ConversationDocumentPayload[]
      activeDocumentTaskId?: string
    }
  >(
    "/conversations/" + conversationId,
  )
}

export const upsertConversation = async (
  conversationId: string,
  payload: ConversationPayload,
) => {
  return await request.put<any, ConversationPayload>("/conversations/" + conversationId, payload)
}

export const patchConversation = async (
  conversationId: string,
  payload: ConversationPatchPayload,
) => {
  return await request.patch<any, ConversationPayload>("/conversations/" + conversationId, payload)
}

export const appendConversationMessage = async (
  conversationId: string,
  payload: ConversationMessagePayload,
) => {
  return await request.post<any, ConversationPayload & { messages?: ConversationMessagePayload[] }>(
    "/conversations/" + conversationId + "/messages",
    payload,
  )
}

export const patchConversationMessage = async (
  conversationId: string,
  messageId: string,
  payload: Partial<ConversationMessagePayload>,
) => {
  return await request.patch<any, ConversationPayload & { messages?: ConversationMessagePayload[] }>(
    "/conversations/" + conversationId + "/messages/" + messageId,
    payload,
  )
}

export const deleteConversation = async (conversationId: string) => {
  return await request.delete<any, { id: string }>("/conversations/" + conversationId)
}

export const deleteConversationDocument = async (conversationId: string, taskId: string) => {
  return await request.delete<
    any,
    ConversationPayload & {
      messages?: ConversationMessagePayload[]
      documents?: ConversationDocumentPayload[]
      activeDocumentTaskId?: string
    }
  >("/conversations/" + conversationId + "/documents/" + taskId)
}

export const importConversationMarkdown = async (payload: ConversationImportPayload) => {
  return await request.post<any, ConversationImportResult>('/notes/import', payload)
}
