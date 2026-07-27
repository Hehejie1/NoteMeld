import request from '@/utils/request' // 你项目里封装好的axios或者fetch

export interface UploadFileResponse {
  url: string
  upload_id?: string
  file_name: string
  stored_name?: string
  content_type: string
  file_kind: 'markdown' | 'audio' | 'video' | 'document' | 'image'
}

export interface IngestUploadedFilePayload {
  file_url: string
  file_name: string
  content_type?: string
  mode: 'chat' | 'note'
  conversation_id?: string
  model_name?: string
  provider_id?: string
  format?: string[]
  style?: string
  extras?: string
}

export interface IngestUploadedFileResponse {
  action: 'chat_asset' | 'imported_note' | 'note_task'
  conversation_id: string
  file_kind: 'markdown' | 'audio' | 'video' | 'document' | 'image'
  asset_content?: string
  asset_id?: string
  note_id?: string
  document_task_id?: string
  task_id?: string
  message?: string
}

export const uploadFile = async (formData: FormData): Promise<UploadFileResponse> => {
  return request.post('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
}

export const ingestUploadedFile = async (
  payload: IngestUploadedFilePayload,
): Promise<IngestUploadedFileResponse> => {
  return request.post('/uploaded_files/ingest', payload)
}
