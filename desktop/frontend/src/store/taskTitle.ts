interface MarkdownVersionLike {
  content?: string
  created_at?: string
}

interface TaskTitleLike {
  title?: string
  markdown?: string | MarkdownVersionLike[]
  audioMeta?: { title?: string }
  formData?: { video_url?: string }
  messages?: Array<{ role?: string; content?: string }>
}

const getLatestMarkdownContent = (markdown?: string | MarkdownVersionLike[]): string => {
  if (typeof markdown === 'string') return markdown
  if (!Array.isArray(markdown) || markdown.length === 0) return ''
  return [...markdown]
    .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
    .find(item => item.content?.trim())
    ?.content || ''
}

export const extractNoteTitleFromMarkdown = (markdown?: string | MarkdownVersionLike[]): string => {
  const content = getLatestMarkdownContent(markdown)
  if (!content) return ''

  const lines = content.split('\n')
  const headingLine = lines.find(line => /^\s*#\s+/.test(line))
  if (!headingLine) return ''

  return headingLine
    .replace(/^\s*#\s+/, '')
    .replace(/\s+#*\s*$/, '')
    .trim()
}

export const getTaskDisplayTitle = (task?: TaskTitleLike | null): string => {
  const firstUserMessage = task?.messages?.find(message => message.role === 'user')?.content
  return (
    extractNoteTitleFromMarkdown(task?.markdown) ||
    task?.audioMeta?.title ||
    task?.title ||
    firstUserMessage?.slice(0, 24) ||
    task?.formData?.video_url ||
    '未命名对话'
  )
}
