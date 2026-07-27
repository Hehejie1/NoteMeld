export interface ScrollViewportLike {
  scrollTop: number
  scrollHeight: number
  clientHeight?: number
}

export interface ScrollViewportRootLike {
  querySelector: (selector: string) => ScrollViewportLike | null
}

export const findScrollViewport = (
  root?: ScrollViewportRootLike | null,
): ScrollViewportLike | null => {
  if (!root) return null
  return root.querySelector('[data-slot="scroll-area-viewport"]')
}

export const scrollElementToBottom = (element?: ScrollViewportLike | null): boolean => {
  if (!element) return false
  element.scrollTop = element.scrollHeight
  return true
}

export const isNearScrollBottom = (
  element?: ScrollViewportLike | null,
  threshold = 120,
): boolean => {
  if (!element) return false
  const clientHeight = element.clientHeight || 0
  return element.scrollHeight - element.scrollTop - clientHeight <= threshold
}
