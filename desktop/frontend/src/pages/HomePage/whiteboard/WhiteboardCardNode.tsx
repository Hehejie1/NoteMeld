import { memo, type KeyboardEvent } from 'react'
import { FileText, Globe2, Maximize2, Network, Pencil, StickyNote } from 'lucide-react'
import { Handle, NodeResizer, Position, type Node, type NodeProps } from '@xyflow/react'
import { Button } from '@/components/ui/button'
import type { WhiteboardCardNodeData } from './whiteboardProjection'
import WhiteboardCardContent from './WhiteboardCardContent'

export interface InteractiveWhiteboardCardNodeData extends WhiteboardCardNodeData {
  onEdit?: (cardId: string) => void
  onOpenNested?: (whiteboardId: string) => void
  onResizeEnd?: (cardId: string, bounds: { x: number; y: number; width: number; height: number }) => void
}

export type InteractiveWhiteboardCardNode = Node<InteractiveWhiteboardCardNodeData, 'whiteboardCard'>

const typeMeta = {
  markdown: { label: 'Markdown', icon: StickyNote, color: 'text-indigo-600 bg-indigo-50' },
  web: { label: '网页', icon: Globe2, color: 'text-sky-700 bg-sky-50' },
  file: { label: '文件', icon: FileText, color: 'text-amber-700 bg-amber-50' },
  whiteboard: { label: '白板', icon: Network, color: 'text-emerald-700 bg-emerald-50' },
} as const

function WhiteboardCardNode({ id, data, selected }: NodeProps<InteractiveWhiteboardCardNode>) {
  const meta = typeMeta[data.card.type]
  const Icon = meta.icon
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    data.onEdit?.(id)
  }
  return (
    <div
      role="group"
      aria-label={`${meta.label}卡片：${data.card.title || '未命名卡片'}`}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      className={`group h-full w-full overflow-hidden rounded-2xl border bg-white shadow-sm outline-none transition-[border-color,box-shadow] focus-visible:ring-2 focus-visible:ring-primary/60 ${
        selected ? 'border-primary shadow-[0_12px_35px_rgba(79,70,229,0.16)]' : 'border-border-subtle hover:border-primary/35'
      }`}
    >
      <NodeResizer
        isVisible={selected}
        minWidth={220}
        minHeight={120}
        maxWidth={960}
        maxHeight={720}
        color="#6366f1"
        onResizeEnd={(_, bounds) => data.onResizeEnd?.(id, bounds)}
      />
      <Handle type="target" position={Position.Left} className="!h-2.5 !w-2.5 !border-2 !border-white !bg-slate-400" />
      <Handle type="source" position={Position.Right} className="!h-2.5 !w-2.5 !border-2 !border-white !bg-primary" />

      <div className="flex h-full min-h-0 flex-col p-3.5">
        <div className="flex items-start gap-2.5">
          <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${meta.color}`}>
            <Icon className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="min-w-0 flex-1 truncate text-[13px] font-semibold text-on-surface">
                {data.card.title || '未命名卡片'}
              </h3>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="nodrag nopan h-6 w-6 opacity-0 transition-opacity group-hover:opacity-100"
                aria-label="编辑卡片"
                onClick={() => data.onEdit?.(id)}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            </div>
            <div className="mt-0.5 text-[10px] font-medium uppercase tracking-wide text-on-surface-variant">
              {meta.label}
            </div>
          </div>
        </div>

        <p className="mt-2.5 line-clamp-2 min-h-9 text-[11px] leading-[18px] text-on-surface-variant">
          {data.card.description || '暂无描述，可编辑补充这块内容表达什么。'}
        </p>

        {data.card.source_refs.length > 0 ? (
          <div className="mt-2 flex min-w-0 flex-wrap gap-1">
            {data.card.source_refs.slice(0, 3).map(source => (
              <span
                key={`${source.source_type}:${source.source_id}`}
                className="max-w-[105px] truncate rounded-full border border-border-subtle bg-surface-container/55 px-2 py-0.5 text-[9px] text-on-surface-variant"
                title={source.title}
              >
                {source.title}
              </span>
            ))}
            {data.card.source_refs.length > 3 ? (
              <span className="rounded-full bg-surface-container px-1.5 py-0.5 text-[9px] text-on-surface-variant">
                +{data.card.source_refs.length - 3}
              </span>
            ) : null}
          </div>
        ) : null}

        {!data.active ? (
          <div className="mt-auto flex items-center gap-1 pt-2 text-[9px] text-on-surface-variant/80">
            <Maximize2 className="h-3 w-3" />
            {data.card.collapsed ? '已折叠 · 选中查看内容' : '选中查看内容'}
          </div>
        ) : null}

        {data.active && (
          <div className="nodrag nopan mt-3 min-h-0 border-t border-border-subtle pt-3">
            <WhiteboardCardContent card={data.card} onOpenNested={data.onOpenNested} />
          </div>
        )}
      </div>
    </div>
  )
}

export default memo(WhiteboardCardNode)
