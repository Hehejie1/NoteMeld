export interface ComposerTextInputState {
  text: string
  urlCard: string
}

export interface MarkdownImportPayloadDraft {
  mode: 'note' | 'chat'
  conversationId?: string
  fileName: string
  content: string
  sourceUrl?: string
  sourceType?: string
}

export interface MarkdownImportPayload {
  import_mode: 'chat_asset' | 'note'
  conversation_id?: string
  title: string
  content: string
  format: 'markdown'
  file_name: string
  source_type: string
  source_url?: string
}

export type UploadedFileKind = 'markdown' | 'audio' | 'video' | 'document' | 'image'

const MARKDOWN_EXTENSIONS = new Set(['md', 'markdown'])
const AUDIO_EXTENSIONS = new Set(['mp3', 'm4a', 'wav', 'aac', 'ogg', 'flac', 'opus'])
const VIDEO_EXTENSIONS = new Set(['mp4', 'mov', 'm4v', 'avi', 'mkv', 'webm'])
const DOCUMENT_EXTENSIONS = new Set(['txt', 'pdf', 'doc', 'docx', 'ppt', 'pptx', 'rtf'])
const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'webp'])

const extensionOf = (fileName: string): string =>
  fileName.split('.').pop()?.trim().toLowerCase() || ''

export const detectUploadedFileKind = ({
  fileName,
  contentType,
}: {
  fileName: string
  contentType?: string
}): UploadedFileKind => {
  const ext = extensionOf(fileName)
  const normalizedType = (contentType || '').toLowerCase()

  if (MARKDOWN_EXTENSIONS.has(ext) || normalizedType.includes('markdown')) return 'markdown'
  if (normalizedType.startsWith('audio/') || AUDIO_EXTENSIONS.has(ext)) return 'audio'
  if (normalizedType.startsWith('video/') || VIDEO_EXTENSIONS.has(ext)) return 'video'
  if (normalizedType.startsWith('image/') || IMAGE_EXTENSIONS.has(ext)) return 'image'
  if (
    DOCUMENT_EXTENSIONS.has(ext) ||
    normalizedType.includes('pdf') ||
    normalizedType.includes('word') ||
    normalizedType.includes('officedocument') ||
    normalizedType.includes('presentation') ||
    normalizedType.startsWith('text/')
  ) {
    return 'document'
  }

  return 'document'
}

export const shouldCollapseComposerTextInput = ({
  text,
  urlCard,
}: ComposerTextInputState): boolean => {
  return Boolean(urlCard && !text.trim())
}

export const deriveMarkdownTitle = (fileName: string, content: string): string => {
  const heading = content
    .split('\n')
    .map(line => line.trim())
    .find(line => line.startsWith('# '))

  if (heading) return heading.slice(2).trim()
  return fileName.replace(/\.md$/i, '') || '未命名笔记'
}

export const buildMarkdownImportPayload = ({
  mode,
  conversationId,
  fileName,
  content,
  sourceUrl,
  sourceType = 'manual',
}: MarkdownImportPayloadDraft): MarkdownImportPayload => {
  return {
    import_mode: mode === 'note' ? 'note' : 'chat_asset',
    conversation_id: conversationId,
    title: deriveMarkdownTitle(fileName, content),
    content,
    format: 'markdown',
    file_name: fileName,
    source_type: sourceType,
    ...(sourceUrl ? { source_url: sourceUrl } : {}),
  }
}
