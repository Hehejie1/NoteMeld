'use client'

import { useEffect, useRef, useState } from 'react'
import { Copy, Download, BrainCircuit, FileText, Trash2, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Badge } from '@/components/ui/badge'
import type { NoteDocument } from '@/store/taskStore'

interface VersionNote {
  ver_id: string
  model_name?: string
  style?: string
  created_at?: string
}

export interface HeaderActionItem {
  key: string
  label: string
  onSelect: () => void
  icon?: typeof Copy
}

const OPEN_DELAY_MS = 90
const CLOSE_DELAY_MS = 180

interface NoteHeaderProps {
  currentTask?: {
    markdown: VersionNote[] | string
  }
  isMultiVersion: boolean
  currentVerId: string
  setCurrentVerId: (id: string) => void
  modelName: string
  style: string
  noteStyles: readonly { value: string; label: string }[]
  copyActions: HeaderActionItem[]
  exportActions: HeaderActionItem[]
  onDeleteDocument?: () => void
  documents?: NoteDocument[]
  activeDocumentTaskId?: string
  onSelectDocument?: (taskId: string) => void
  createAt?: string | Date
  showTranscribe?: boolean
  setShowTranscribe?: (show: boolean) => void
  viewMode?: 'preview' | 'map' | 'wiki'
  setViewMode?: (mode: 'preview' | 'map' | 'wiki') => void
}

export function MarkdownHeader({
  currentTask,
  isMultiVersion,
  currentVerId,
  setCurrentVerId,
  style,
  noteStyles,
  copyActions,
  exportActions,
  onDeleteDocument,
  documents = [],
  activeDocumentTaskId = '',
  onSelectDocument,
  viewMode = 'preview',
  setViewMode,
}: NoteHeaderProps) {
  const headerRef = useRef<HTMLDivElement | null>(null)
  const openTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [compactActions, setCompactActions] = useState(false)
  const [openMenu, setOpenMenu] = useState<'copy' | 'export' | null>(null)

  useEffect(() => {
    const node = headerRef.current
    if (!node) return

    const updateCompact = () => setCompactActions(node.offsetWidth < 620)
    updateCompact()

    const observer = new ResizeObserver(updateCompact)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    return () => {
      if (openTimerRef.current) clearTimeout(openTimerRef.current)
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current)
    }
  }, [])

  const styleLabel = noteStyles.find(v => v.value === style)?.label || style || '默认'
  const activeDocument = documents.find(document => document.taskId === activeDocumentTaskId) || documents[0]
  const actionButtonClass = compactActions
    ? 'h-9 w-10 px-0 text-on-surface-variant hover:text-primary md:h-8 md:w-9'
    : 'h-9 px-2 text-on-surface-variant hover:text-primary md:h-8'
  const actionIconClass = compactActions ? 'h-4 w-4' : 'mr-1.5 h-4 w-4'
  const menuPanelClass = 'absolute right-0 top-full z-20 mt-1 min-w-[148px] rounded-xl border border-border-subtle bg-white p-1.5 shadow-lg'

  const clearOpenTimer = () => {
    if (!openTimerRef.current) return
    clearTimeout(openTimerRef.current)
    openTimerRef.current = null
  }

  const clearCloseTimer = () => {
    if (!closeTimerRef.current) return
    clearTimeout(closeTimerRef.current)
    closeTimerRef.current = null
  }

  const scheduleOpen = (key: 'copy' | 'export') => {
    clearCloseTimer()
    clearOpenTimer()
    openTimerRef.current = setTimeout(() => {
      setOpenMenu(key)
      openTimerRef.current = null
    }, OPEN_DELAY_MS)
  }

  const scheduleClose = (key: 'copy' | 'export') => {
    clearOpenTimer()
    clearCloseTimer()
    closeTimerRef.current = setTimeout(() => {
      setOpenMenu(current => (current === key ? null : current))
      closeTimerRef.current = null
    }, CLOSE_DELAY_MS)
  }

  const renderActionMenu = (
    key: 'copy' | 'export',
    icon: typeof Copy,
    label: string,
    items: HeaderActionItem[],
  ) => {
    const Icon = icon

    return (
      <div
        className="relative"
        onMouseEnter={() => scheduleOpen(key)}
        onMouseLeave={() => scheduleClose(key)}
      >
        <Button
          variant="ghost"
          size="sm"
          className={actionButtonClass}
          aria-label={label}
        >
          <Icon className={actionIconClass} />
          {!compactActions && <span className="text-[12px]">{label}</span>}
          <ChevronDown
            className={compactActions
              ? 'ml-0.5 h-3 w-3 text-on-surface-variant'
              : 'ml-1 h-3.5 w-3.5 text-on-surface-variant'}
          />
        </Button>

        {openMenu === key && items.length > 0 && (
          <>
            <div
              className="safe-zone-bridge absolute inset-x-0 top-full z-10 h-3"
              aria-hidden="true"
              onMouseEnter={() => {
                clearCloseTimer()
              }}
              onMouseLeave={() => scheduleClose(key)}
            />
            <div
              className={menuPanelClass}
              onMouseEnter={() => {
                clearCloseTimer()
                clearOpenTimer()
              }}
              onMouseLeave={() => scheduleClose(key)}
            >
            {items.map(item => (
              <button
                key={item.key}
                type="button"
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] text-on-surface hover:bg-slate-50"
                onClick={() => {
                  clearOpenTimer()
                  clearCloseTimer()
                  item.onSelect()
                  setOpenMenu(null)
                }}
              >
                {(() => {
                  const ItemIcon = item.icon || (key === 'copy' ? Copy : Download)
                  return <ItemIcon className="h-4 w-4 text-on-surface-variant" />
                })()}
                {item.label}
              </button>
            ))}
            </div>
          </>
        )}
      </div>
    )
  }

  return (
    <div
      ref={headerRef}
      className="sticky top-0 z-10 flex min-h-12 flex-wrap items-center justify-between gap-x-2 gap-y-2 border-b border-border-subtle/60 bg-white px-3 py-2 backdrop-blur-sm md:px-5 md:py-2.5"
    >
      {/* 左侧：文档 + 版本 + 风格 */}
      <div className="flex min-w-0 flex-[1_1_220px] flex-wrap items-center gap-2 md:min-w-[180px] md:flex-[1_1_260px]">
        {documents.length > 0 && onSelectDocument && (
          <Select
            value={activeDocument?.taskId || ''}
            onValueChange={onSelectDocument}
          >
            <SelectTrigger className="h-9 min-w-[150px] max-w-[calc(100vw-160px)] flex-1 border-border-subtle text-[12px] md:h-8 md:min-w-[160px] md:max-w-[320px]">
              <span className="min-w-0 truncate text-on-surface">
                {activeDocument?.title || '选择文档'}
              </span>
            </SelectTrigger>
            <SelectContent>
              {documents.map(document => (
                <SelectItem key={document.taskId} value={document.taskId}>
                  {document.title || '未命名笔记'}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {isMultiVersion && Array.isArray(currentTask?.markdown) && (
          <Select value={currentVerId} onValueChange={setCurrentVerId}>
            <SelectTrigger className="h-9 w-[140px] border-border-subtle text-[12px] md:h-8">
              <span className="font-mono text-[11px] text-on-surface">
                v · {currentVerId.slice(-6)}
              </span>
            </SelectTrigger>
            <SelectContent>
              {(currentTask.markdown as VersionNote[]).map(v => {
                const shortId = v.ver_id.slice(-6)
                return (
                  <SelectItem key={v.ver_id} value={v.ver_id}>
                    {`版本 v · ${shortId}`}
                  </SelectItem>
                )
              })}
            </SelectContent>
          </Select>
        )}

        <Badge
          variant="secondary"
          className="border-border-subtle bg-primary-light font-mono text-[11px] text-primary"
        >
          {styleLabel}
        </Badge>
      </div>

      {/* 右侧：切换视图 + 复制 + 导出 */}
      <div className="ml-auto flex shrink-0 items-center gap-1">
        {setViewMode && (
          <Select
            value={viewMode}
            onValueChange={(val) => {
              if (val === 'preview' || val === 'map' || val === 'wiki') setViewMode(val)
            }}
          >
            <SelectTrigger className="h-9 w-[112px] border-border-subtle bg-transparent text-[12px] md:h-8 md:w-[120px]">
              <div className="flex items-center gap-1.5">
                {viewMode === 'preview' && <FileText className="h-4 w-4" />}
                {viewMode === 'map' && <BrainCircuit className="h-4 w-4" />}
                {viewMode === 'wiki' && <BrainCircuit className="h-4 w-4" />}
                <span>{viewMode === 'preview' ? '笔记文章' : viewMode === 'map' ? '思维导图' : 'wiki文章'}</span>
              </div>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="preview">笔记文章</SelectItem>
              <SelectItem value="map">思维导图</SelectItem>
              <SelectItem value="wiki">wiki文章</SelectItem>
            </SelectContent>
          </Select>
        )}

        {renderActionMenu('copy', Copy, '复制', copyActions)}
        {renderActionMenu('export', Download, '导出', exportActions)}

        {onDeleteDocument && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  onClick={onDeleteDocument}
                  variant="ghost"
                  size="sm"
                  className={compactActions
                    ? 'h-9 w-9 px-0 text-on-surface-variant hover:text-destructive md:h-8 md:w-8'
                    : 'h-9 px-2 text-on-surface-variant hover:text-destructive md:h-8'}
                  aria-label="删除"
                >
                  <Trash2 className={actionIconClass} />
                  {!compactActions && <span className="text-[12px]">删除</span>}
                </Button>
              </TooltipTrigger>
              <TooltipContent>删除当前笔记</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>
    </div>
  )
}
