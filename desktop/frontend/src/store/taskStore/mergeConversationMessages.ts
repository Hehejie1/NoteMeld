export interface MergeableConversationMessage {
  id: string
  createdAt?: string
  isStreaming?: boolean
}

const byCreatedAt = (a: MergeableConversationMessage, b: MergeableConversationMessage) => {
  const left = a.createdAt ? Date.parse(a.createdAt) : 0
  const right = b.createdAt ? Date.parse(b.createdAt) : 0
  return left - right
}

export const mergeConversationMessages = <T extends MergeableConversationMessage>(
  serverMessages: T[],
  localMessages: T[] = [],
): T[] => {
  const merged = new Map<string, T>()
  serverMessages.forEach(message => {
    merged.set(message.id, message)
  })

  localMessages.forEach(message => {
    if (message.isStreaming && !merged.has(message.id)) {
      merged.set(message.id, message)
    }
  })

  return Array.from(merged.values()).sort(byCreatedAt)
}
