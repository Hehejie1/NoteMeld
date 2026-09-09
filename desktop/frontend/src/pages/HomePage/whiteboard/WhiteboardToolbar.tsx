import { FilePlus2, Globe2, Maximize, Network, Redo2, StickyNote, Undo2, ZoomIn, ZoomOut } from 'lucide-react'
import { useReactFlow } from '@xyflow/react'
import { Button } from '@/components/ui/button'
import type { WhiteboardCardType } from './types'

interface WhiteboardToolbarProps {
  canUndo: boolean
  canRedo: boolean
  pending: boolean
  onCreate: (type: WhiteboardCardType) => void
  onUndo: () => void
  onRedo: () => void
}

const createActions: Array<{ type: WhiteboardCardType; label: string; icon: typeof StickyNote }> = [
  { type: 'markdown', label: 'Markdown 卡片', icon: StickyNote },
  { type: 'web', label: '网页卡片', icon: Globe2 },
  { type: 'file', label: '文件卡片', icon: FilePlus2 },
  { type: 'whiteboard', label: '子白板卡片', icon: Network },
]

export default function WhiteboardToolbar({
  canUndo,
  canRedo,
  pending,
  onCreate,
  onUndo,
  onRedo,
}: WhiteboardToolbarProps) {
  const { fitView, zoomIn, zoomOut } = useReactFlow()
  return (
    <div className="absolute left-3 top-3 z-20 flex items-center gap-1 rounded-xl border border-border-subtle bg-white/95 p-1 shadow-md backdrop-blur">
      {createActions.map(action => {
        const Icon = action.icon
        return (
          <Button
            key={action.type}
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            title={action.label}
            aria-label={action.label}
            onClick={() => onCreate(action.type)}
          >
            <Icon className="h-4 w-4" />
          </Button>
        )
      })}
      <span className="mx-1 h-5 w-px bg-border-subtle" />
      <Button type="button" size="icon" variant="ghost" className="h-8 w-8" aria-label="放大" onClick={() => void zoomIn()}>
        <ZoomIn className="h-4 w-4" />
      </Button>
      <Button type="button" size="icon" variant="ghost" className="h-8 w-8" aria-label="缩小" onClick={() => void zoomOut()}>
        <ZoomOut className="h-4 w-4" />
      </Button>
      <Button type="button" size="icon" variant="ghost" className="h-8 w-8" aria-label="适配内容" onClick={() => void fitView({ padding: 0.18, duration: 240 })}>
        <Maximize className="h-4 w-4" />
      </Button>
      <span className="mx-1 h-5 w-px bg-border-subtle" />
      <Button type="button" size="icon" variant="ghost" className="h-8 w-8" aria-label="撤销" disabled={!canUndo || pending} onClick={onUndo}>
        <Undo2 className="h-4 w-4" />
      </Button>
      <Button type="button" size="icon" variant="ghost" className="h-8 w-8" aria-label="重做" disabled={!canRedo || pending} onClick={onRedo}>
        <Redo2 className="h-4 w-4" />
      </Button>
    </div>
  )
}
