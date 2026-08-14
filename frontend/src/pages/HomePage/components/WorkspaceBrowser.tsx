import { type FC, useCallback, useEffect, useState } from 'react'
import {
  ArrowLeft,
  ChevronRight,
  File as FileIcon,
  Folder,
  FolderOpen,
  PanelRightClose,
  PanelRightOpen,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import {
  extractWorkspaceErrorCode,
  listWorkspace,
  readWorkspaceFile,
  type WorkspaceEntry,
  type WorkspaceReadResult,
} from '@/services/workspace'

interface WorkspaceBrowserProps {
  conversationId: string
  className?: string
  defaultOpen?: boolean
}

interface DirState {
  path: string
  entries: WorkspaceEntry[]
  loading: boolean
  error: string
}

interface FilePreview {
  path: string
  result: WorkspaceReadResult
  loading: boolean
  error: string
}

const formatFileSize = (size: number): string => {
  if (!Number.isFinite(size) || size < 0) return '-'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`
  return `${(size / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

const joinPath = (base: string, name: string): string => {
  if (!base) return name
  return `${base.replace(/\/$/, '')}/${name}`
}

const parentPath = (path: string): string => {
  if (!path) return ''
  const trimmed = path.replace(/\/$/, '')
  const idx = trimmed.lastIndexOf('/')
  if (idx <= 0) return ''
  return trimmed.slice(0, idx)
}

const pathSegments = (path: string): Array<{ name: string; path: string }> => {
  if (!path) return []
  const parts = path.split('/').filter(Boolean)
  const segments: Array<{ name: string; path: string }> = []
  let acc = ''
  for (const part of parts) {
    acc = acc ? `${acc}/${part}` : part
    segments.push({ name: part, path: acc })
  }
  return segments
}

const WorkspaceBrowser: FC<WorkspaceBrowserProps> = ({
  conversationId,
  className,
  defaultOpen = false,
}) => {
  const [open, setOpen] = useState(defaultOpen)
  const [dir, setDir] = useState<DirState>({
    path: '',
    entries: [],
    loading: false,
    error: '',
  })
  const [preview, setPreview] = useState<FilePreview | null>(null)

  const loadDir = useCallback(async (path: string) => {
    setDir(prev => ({ ...prev, path, loading: true, error: '' }))
    setPreview(null)
    try {
      const result = await listWorkspace(conversationId, path)
      setDir({
        path: result.path || path,
        entries: Array.isArray(result.entries) ? result.entries : [],
        loading: false,
        error: '',
      })
    } catch (err) {
      const code = extractWorkspaceErrorCode(err)
      const msg = code === 403 ? '路径越界' : code === 404 ? '不存在' : ''
      setDir(prev => ({ ...prev, loading: false, error: msg }))
    }
  }, [conversationId])

  const loadFile = useCallback(async (path: string) => {
    setPreview({ path, result: null as unknown as WorkspaceReadResult, loading: true, error: '' })
    try {
      const result = await readWorkspaceFile(conversationId, path)
      setPreview({ path, result, loading: false, error: '' })
    } catch (err) {
      const code = extractWorkspaceErrorCode(err)
      const msg = code === 403 ? '路径越界' : code === 404 ? '文件不存在' : ''
      setPreview({ path, result: null as unknown as WorkspaceReadResult, loading: false, error: msg })
    }
  }, [conversationId])

  useEffect(() => {
    if (open && conversationId) {
      void loadDir('')
    }
  }, [open, conversationId, loadDir])

  const handleEntryClick = (entry: WorkspaceEntry) => {
    if (entry.type === 'directory') {
      void loadDir(joinPath(dir.path, entry.name))
    } else {
      void loadFile(joinPath(dir.path, entry.name))
    }
  }

  const segments = pathSegments(dir.path)

  if (!open) {
    return (
      <div className={cn('flex items-center', className)}>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setOpen(true)}
        >
          <PanelRightOpen className="mr-1.5 h-4 w-4" />
          工作空间
        </Button>
      </div>
    )
  }

  const sortedEntries = [...dir.entries].sort((a, b) => {
    if (a.type !== b.type) return a.type === 'directory' ? -1 : 1
    return a.name.localeCompare(b.name)
  })

  return (
    <div
      className={cn(
        'flex flex-col overflow-hidden rounded-xl border border-border-subtle bg-white shadow-[0_2px_12px_rgba(15,23,42,0.04)]',
        className,
      )}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between gap-2 border-b border-border-subtle px-3 py-2">
        <div className="flex min-w-0 items-center gap-1.5 text-[13px] font-medium text-on-surface">
          <FolderOpen className="h-4 w-4 shrink-0 text-primary" />
          <span className="truncate">会话工作空间</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setOpen(false)}
          aria-label="收起工作空间"
        >
          <PanelRightClose className="h-4 w-4" />
        </Button>
      </div>

      {/* 面包屑 */}
      <div className="flex items-center gap-1 overflow-x-auto border-b border-border-subtle px-3 py-2 text-[12px]">
        {dir.path && (
          <button
            type="button"
            onClick={() => void loadDir('')}
            className="shrink-0 text-primary hover:underline"
          >
            根目录
          </button>
        )}
        {!dir.path && <span className="text-on-surface-variant">根目录</span>}
        {segments.map(seg => (
          <span key={seg.path} className="flex shrink-0 items-center gap-1">
            <ChevronRight className="h-3 w-3 text-on-surface-variant/50" />
            <button
              type="button"
              onClick={() => void loadDir(seg.path)}
              className="text-on-surface-variant hover:text-primary hover:underline"
            >
              {seg.name}
            </button>
          </span>
        ))}
      </div>

      {/* 返回上级 */}
      {dir.path && (
        <button
          type="button"
          onClick={() => void loadDir(parentPath(dir.path))}
          className="flex items-center gap-1.5 border-b border-border-subtle px-3 py-1.5 text-[12px] text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          返回上级
        </button>
      )}

      {/* 主体 */}
      <div className="flex min-h-0 flex-1 flex-col">
        {dir.error && (
          <Alert variant="destructive" className="mx-3 mt-3">
            <AlertDescription>{dir.error}</AlertDescription>
          </Alert>
        )}

        <ScrollArea className="max-h-[280px] min-h-0 flex-1">
          {dir.loading ? (
            <div className="px-3 py-6 text-center text-[13px] text-on-surface-variant">
              加载中...
            </div>
          ) : sortedEntries.length === 0 && !dir.error ? (
            <div className="px-3 py-6 text-center text-[13px] text-on-surface-variant">
              空目录
            </div>
          ) : (
            <ul className="divide-y divide-border-subtle/60">
              {sortedEntries.map(entry => {
                const isActive = preview?.path === joinPath(dir.path, entry.name)
                return (
                  <li key={`${entry.type}-${entry.name}`}>
                    <button
                      type="button"
                      onClick={() => handleEntryClick(entry)}
                      className={cn(
                        'flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] transition-colors',
                        isActive
                          ? 'bg-primary-light/60 text-primary'
                          : 'text-on-surface hover:bg-surface-container-low',
                      )}
                    >
                      {entry.type === 'directory' ? (
                        <Folder className="h-4 w-4 shrink-0 text-primary/70" />
                      ) : (
                        <FileIcon className="h-4 w-4 shrink-0 text-on-surface-variant/60" />
                      )}
                      <span className="min-w-0 flex-1 truncate">{entry.name}</span>
                      {entry.type === 'file' && (
                        <span className="shrink-0 font-mono text-[11px] text-on-surface-variant/60">
                          {formatFileSize(entry.size)}
                        </span>
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </ScrollArea>

        {/* 文件预览 */}
        {preview && (
          <div className="border-t border-border-subtle">
            <div className="flex items-center justify-between gap-2 border-b border-border-subtle px-3 py-1.5">
              <span className="min-w-0 truncate text-[12px] font-medium text-on-surface">
                {preview.path}
              </span>
              <button
                type="button"
                onClick={() => setPreview(null)}
                className="shrink-0 rounded p-0.5 text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface"
                aria-label="关闭预览"
              >
                <PanelRightClose className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="max-h-[260px] min-h-0">
              {preview.error ? (
                <Alert variant="destructive" className="mx-3 my-2">
                  <AlertDescription>{preview.error}</AlertDescription>
                </Alert>
              ) : preview.loading ? (
                <div className="px-3 py-6 text-center text-[13px] text-on-surface-variant">
                  读取中...
                </div>
              ) : preview.result ? (
                <div className="flex flex-col">
                  {preview.result.encoding === 'base64' && (
                    <div className="border-b border-border-subtle bg-surface-container-low px-3 py-1.5 text-[11px] text-on-surface-variant">
                      二进制文件（不支持预览内容）
                    </div>
                  )}
                  {preview.result.truncated && (
                    <div className="border-b border-border-subtle bg-warning/10 px-3 py-1.5 text-[11px] text-warning">
                      文件过大，内容已截断
                    </div>
                  )}
                  {preview.result.encoding === 'utf-8' ? (
                    <ScrollArea className="max-h-[220px]">
                      <pre className="whitespace-pre-wrap break-words px-3 py-2 font-mono text-[12px] leading-relaxed text-on-surface">
                        {preview.result.content}
                      </pre>
                    </ScrollArea>
                  ) : (
                    <div className="px-3 py-6 text-center text-[12px] text-on-surface-variant">
                      {formatFileSize(preview.result.size)}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default WorkspaceBrowser
