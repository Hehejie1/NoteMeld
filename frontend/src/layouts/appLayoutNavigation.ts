export const shouldHighlightTaskInSidebar = (
  pathname: string,
  taskId: string,
  currentTaskId: string | null,
): boolean => pathname.startsWith('/notes/') && taskId === currentTaskId
