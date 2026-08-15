import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import {
  Background,
  BackgroundVariant,
  ReactFlow,
  ReactFlowProvider,
  SelectionMode,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeTypes,
  type NodeTypes,
  type OnSelectionChangeParams,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { createWhiteboardContext } from '@/services/whiteboard'
import { useTaskStore } from '@/store/taskStore'
import { buildPasteOperations, copyWhiteboardSelection } from './whiteboardCommands'
import { cardMoveResizeOperation, projectWhiteboard, type WhiteboardFlowEdge } from './whiteboardProjection'
import { useWhiteboardController } from './useWhiteboardController'
import type {
  WhiteboardCard,
  WhiteboardCardType,
  WhiteboardOperation,
  WhiteboardPosition,
  WhiteboardRelation,
} from './types'
import WhiteboardCardNode, { type InteractiveWhiteboardCardNode } from './WhiteboardCardNode'
import WhiteboardRelationEdge from './WhiteboardRelationEdge'
import WhiteboardToolbar from './WhiteboardToolbar'
import WhiteboardSelectionToolbar from './WhiteboardSelectionToolbar'
import WhiteboardCardDialog, { type WhiteboardCardFormValue } from './WhiteboardCardDialog'
import WhiteboardRelationDialog from './WhiteboardRelationDialog'
import { createViewportCommitter, resolveContextForCurrentTask } from './whiteboardInteractions'

interface WhiteboardCanvasProps {
  conversationId: string
  whiteboardId: string
  onOpenNestedWhiteboard?: (whiteboardId: string) => void
}

const nodeTypes = { whiteboardCard: WhiteboardCardNode } as NodeTypes
const edgeTypes = { whiteboardRelation: WhiteboardRelationEdge } as EdgeTypes

const createId = (kind: 'card' | 'relation') =>
  `${kind}_${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}_${Math.random().toString(16).slice(2)}`}`

const isEditableTarget = (target: EventTarget | null) => {
  const element = target as HTMLElement | null
  return Boolean(element?.closest('input, textarea, select, [contenteditable="true"]'))
}

function WhiteboardCanvasInner({
  conversationId,
  whiteboardId,
  onOpenNestedWhiteboard,
}: WhiteboardCanvasProps) {
  const rootRef = useRef<HTMLDivElement | null>(null)
  const clipboardRef = useRef<ReturnType<typeof copyWhiteboardSelection> | null>(null)
  const { screenToFlowPosition } = useReactFlow<InteractiveWhiteboardCardNode, WhiteboardFlowEdge>()
  const controller = useWhiteboardController({ conversationId, whiteboardId })
  const submitOperations = controller.submitOperations
  const setSelection = controller.setSelection
  const setActiveCardId = controller.setActiveCardId
  const undo = controller.undo
  const redo = controller.redo
  const addContextRef = useTaskStore(state => state.addContextRef)
  const [nodes, setNodes, onNodesChange] = useNodesState<InteractiveWhiteboardCardNode>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<WhiteboardFlowEdge>([])
  const [cardDialogOpen, setCardDialogOpen] = useState(false)
  const [cardDialogType, setCardDialogType] = useState<WhiteboardCardType>('markdown')
  const [cardDialogPosition, setCardDialogPosition] = useState<WhiteboardPosition>({ x: 80, y: 80 })
  const [editingCard, setEditingCard] = useState<WhiteboardCard | null>(null)
  const [editingRelation, setEditingRelation] = useState<WhiteboardRelation | null>(null)
  const [addingContext, setAddingContext] = useState(false)
  const [contextError, setContextError] = useState<string | null>(null)

  const viewportCommitter = useMemo(() => createViewportCommitter(
    viewport => submitOperations([{
      op: 'viewport.update',
      x: viewport.x,
      y: viewport.y,
      zoom: viewport.zoom,
    }], '保存白板视口'),
    500,
  ), [submitOperations])

  useEffect(() => () => viewportCommitter.dispose(), [viewportCommitter, whiteboardId])

  const persistResize = useCallback((cardId: string, bounds: { x: number; y: number; width: number; height: number }) => {
    void submitOperations([{
      op: 'card.move_resize',
      items: [{
        card_id: cardId,
        position: { x: bounds.x, y: bounds.y },
        size: { width: bounds.width, height: bounds.height },
      }],
    }], '调整卡片尺寸').catch(() => undefined)
  }, [submitOperations])

  const openEditCard = useCallback((cardId: string) => {
    const card = controller.snapshot?.cards.find(item => item.id === cardId)
    if (!card) return
    setEditingCard(card)
    setCardDialogOpen(true)
  }, [controller.snapshot])

  const openEditRelation = useCallback((relationId: string) => {
    const relation = controller.snapshot?.relations.find(item => item.id === relationId) || null
    setEditingRelation(relation)
  }, [controller.snapshot])

  const projected = useMemo(() => {
    if (!controller.snapshot) return { nodes: [], edges: [] }
    return projectWhiteboard(controller.snapshot, {
      selectedCardIds: new Set(controller.selectedCardIds),
      selectedRelationIds: new Set(controller.selectedRelationIds),
      activeCardId: controller.activeCardId,
    })
  }, [controller.activeCardId, controller.selectedCardIds, controller.selectedRelationIds, controller.snapshot])

  useEffect(() => {
    setNodes(projected.nodes.map(node => ({
      ...node,
      data: {
        ...node.data,
        onEdit: openEditCard,
        onOpenNested: onOpenNestedWhiteboard,
        onResizeEnd: persistResize,
      },
    })))
    setEdges(projected.edges.map(edge => ({
      ...edge,
      data: edge.data ? { ...edge.data, onEdit: openEditRelation } : edge.data,
    })))
  }, [onOpenNestedWhiteboard, openEditCard, openEditRelation, persistResize, projected.edges, projected.nodes, setEdges, setNodes])

  const openCreateDialog = useCallback((type: WhiteboardCardType, position?: WhiteboardPosition) => {
    let nextPosition = position
    if (!nextPosition && rootRef.current) {
      const rect = rootRef.current.getBoundingClientRect()
      nextPosition = screenToFlowPosition({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 })
    }
    setEditingCard(null)
    setCardDialogType(type)
    setCardDialogPosition(nextPosition || { x: 80, y: 80 })
    setCardDialogOpen(true)
  }, [screenToFlowPosition])

  const onPaneDoubleClick = useCallback((event: MouseEvent<HTMLDivElement>) => {
    if (!(event.target as HTMLElement).classList.contains('react-flow__pane')) return
    openCreateDialog('markdown', screenToFlowPosition({ x: event.clientX, y: event.clientY }))
  }, [openCreateDialog, screenToFlowPosition])

  const saveCard = useCallback(async (value: WhiteboardCardFormValue) => {
    if (editingCard) {
      await submitOperations([{
        op: 'card.update',
        card_id: editingCard.id,
        patch: value,
      }], '编辑卡片')
      return
    }
    const card: WhiteboardCard = {
      id: createId('card'),
      ...value,
      position: cardDialogPosition,
      size: { width: 300, height: 180 },
      z_index: Math.max(0, ...(controller.snapshot?.cards.map(item => item.z_index + 1) || [0])),
      collapsed: true,
    } as WhiteboardCard
    await submitOperations([{ op: 'card.create', card }], '创建卡片')
    setSelection([card.id], [])
    setActiveCardId(card.id)
  }, [cardDialogPosition, controller.snapshot, editingCard, setActiveCardId, setSelection, submitOperations])

  const saveRelation = useCallback(async (patch: Partial<WhiteboardRelation>) => {
    if (!editingRelation) throw new Error('关系不存在')
    await submitOperations([{
      op: 'relation.update',
      relation_id: editingRelation.id,
      patch,
    }], '编辑关系')
  }, [editingRelation, submitOperations])

  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target || connection.source === connection.target) return
    const relation: WhiteboardRelation = {
      id: createId('relation'),
      source_card_id: connection.source,
      target_card_id: connection.target,
      relation_type: 'related',
      label: '相关',
      description: '',
      line_type: 'bezier',
      direction: 'forward',
      source_refs: [],
      style: {},
    }
    void submitOperations([{ op: 'relation.create', relation }], '创建关系').catch(() => undefined)
  }, [submitOperations])

  const onReconnect = useCallback((oldEdge: Edge, connection: Connection) => {
    if (!connection.source || !connection.target || connection.source === connection.target) return
    void submitOperations([{
      op: 'relation.update',
      relation_id: oldEdge.id,
      patch: { source_card_id: connection.source, target_card_id: connection.target },
    }], '重新连接关系').catch(() => undefined)
  }, [submitOperations])

  const onSelectionChange = useCallback(({ nodes: selectedNodes, edges: selectedEdges }: OnSelectionChangeParams<InteractiveWhiteboardCardNode, WhiteboardFlowEdge>) => {
    const cardIds = new Set(selectedNodes.map(node => node.id))
    const relationIds = selectedEdges.map(edge => edge.id)
    for (const edge of selectedEdges) {
      cardIds.add(edge.source)
      cardIds.add(edge.target)
    }
    setSelection([...cardIds], relationIds)
  }, [setSelection])

  const copySelection = useCallback(() => {
    if (!controller.snapshot) return
    clipboardRef.current = copyWhiteboardSelection(
      controller.snapshot,
      controller.selectedCardIds,
      controller.selectedRelationIds,
    )
  }, [controller.selectedCardIds, controller.selectedRelationIds, controller.snapshot])

  const pasteSelection = useCallback(() => {
    const clipboard = clipboardRef.current
    if (!clipboard) return
    const operations = buildPasteOperations(clipboard, { offset: 32 })
    const createdCards = operations.flatMap(operation => operation.op === 'card.create' ? [operation.card.id] : [])
    void submitOperations(operations, '粘贴选区').then(() => {
      setSelection(createdCards, [])
    }).catch(() => undefined)
  }, [setSelection, submitOperations])

  const deleteSelection = useCallback(() => {
    const selectedCards = new Set(controller.selectedCardIds)
    const operations: WhiteboardOperation[] = [
      ...controller.selectedRelationIds
        .filter(relationId => {
          const relation = controller.snapshot?.relations.find(item => item.id === relationId)
          return relation && !selectedCards.has(relation.source_card_id) && !selectedCards.has(relation.target_card_id)
        })
        .map<WhiteboardOperation>(relationId => ({ op: 'relation.delete', relation_id: relationId })),
      ...controller.selectedCardIds.map<WhiteboardOperation>(cardId => ({ op: 'card.delete', card_id: cardId })),
    ]
    if (operations.length === 0) return
    void submitOperations(operations, '删除选区').then(() => {
      setSelection([], [])
      setActiveCardId(null)
    }).catch(() => undefined)
  }, [controller.selectedCardIds, controller.selectedRelationIds, controller.snapshot, setActiveCardId, setSelection, submitOperations])

  const addSelectionToConversation = useCallback(async () => {
    if (!controller.snapshot || controller.selectedCardIds.length + controller.selectedRelationIds.length === 0) return
    const initiatingTaskId = useTaskStore.getState().currentTaskId
    if (!initiatingTaskId || initiatingTaskId !== conversationId) return
    setAddingContext(true)
    setContextError(null)
    const result = await resolveContextForCurrentTask({
      initiatingTaskId,
      getCurrentTaskId: () => useTaskStore.getState().currentTaskId,
      request: () => createWhiteboardContext(conversationId, whiteboardId, {
        revision: controller.serverRevision,
        card_ids: controller.selectedCardIds,
        relation_ids: controller.selectedRelationIds,
        label: controller.selectedCardIds.length === 1
          ? controller.snapshot?.cards.find(card => card.id === controller.selectedCardIds[0])?.title || '白板选区'
          : `白板选区（${controller.selectedCardIds.length} 张卡片）`,
      }),
      accept: addContextRef,
    })
    if (result.status === 'error') setContextError(result.error)
    setAddingContext(false)
  }, [addContextRef, controller.selectedCardIds, controller.selectedRelationIds, controller.serverRevision, controller.snapshot, conversationId, whiteboardId])

  const handleKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>) => {
    if (isEditableTarget(event.target)) return
    const modifier = event.metaKey || event.ctrlKey
    if (modifier && event.key.toLowerCase() === 'c') {
      event.preventDefault()
      copySelection()
    } else if (modifier && event.key.toLowerCase() === 'v') {
      event.preventDefault()
      pasteSelection()
    } else if (modifier && event.key.toLowerCase() === 'z') {
      event.preventDefault()
      if (event.shiftKey) void redo()
      else void undo()
    } else if (modifier && event.key.toLowerCase() === 'y') {
      event.preventDefault()
      void redo()
    } else if (event.key === 'Delete' || event.key === 'Backspace') {
      event.preventDefault()
      deleteSelection()
    }
  }, [copySelection, deleteSelection, pasteSelection, redo, undo])

  if (controller.loading) {
    return <div className="flex h-full items-center justify-center gap-2 text-sm text-on-surface-variant"><Loader2 className="h-4 w-4 animate-spin" />白板加载中…</div>
  }
  if (!controller.snapshot || controller.loadError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-on-surface-variant">
        <AlertCircle className="h-5 w-5 text-destructive" />
        <span>{controller.loadError || '白板不存在'}</span>
        <Button type="button" size="sm" variant="outline" onClick={() => void controller.reload()}><RefreshCw className="h-4 w-4" />重试</Button>
      </div>
    )
  }

  return (
    <div
      ref={rootRef}
      role="application"
      aria-label="语义白板画布"
      className="relative h-full min-h-0 w-full overflow-hidden bg-[#f7f8fb] outline-none"
      tabIndex={0}
      onDoubleClick={onPaneDoubleClick}
      onKeyDown={handleKeyDown}
      onPointerDown={() => rootRef.current?.focus({ preventScroll: true })}
    >
      <ReactFlow<InteractiveWhiteboardCardNode, WhiteboardFlowEdge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onReconnect={onReconnect}
        onSelectionChange={onSelectionChange}
        onNodeClick={(_, node) => controller.setActiveCardId(node.id)}
        onNodeDoubleClick={(_, node) => openEditCard(node.id)}
        onPaneClick={() => controller.setActiveCardId(null)}
        onEdgeDoubleClick={(_, edge) => {
          openEditRelation(edge.id)
        }}
        onNodeDragStop={(_, node, draggedNodes) => {
          const changed = draggedNodes.length > 0 ? draggedNodes : [node]
          void controller.submitOperations([cardMoveResizeOperation(changed)], '移动卡片').catch(() => undefined)
        }}
        onMoveEnd={(_, viewport) => viewportCommitter.schedule(viewport)}
        defaultViewport={controller.snapshot.viewport}
        onlyRenderVisibleElements
        selectionOnDrag
        panOnDrag={[1, 2]}
        zoomOnDoubleClick={false}
        selectionMode={SelectionMode.Partial}
        multiSelectionKeyCode={["Meta", "Control", "Shift"]}
        deleteKeyCode={null}
        minZoom={0.1}
        maxZoom={2.5}
        fitView={controller.snapshot.cards.length > 0}
        fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color="#d7dce5" />
        <WhiteboardToolbar
          canUndo={controller.canUndo}
          canRedo={controller.canRedo}
          pending={controller.pending}
          onCreate={type => openCreateDialog(type)}
          onUndo={() => void controller.undo()}
          onRedo={() => void controller.redo()}
        />
        <WhiteboardSelectionToolbar
          cardCount={controller.selectedCardIds.length}
          relationCount={controller.selectedRelationIds.length}
          pending={controller.pending}
          addingContext={addingContext}
          onCopy={copySelection}
          onDelete={deleteSelection}
          onAddToConversation={() => void addSelectionToConversation()}
        />
        {controller.snapshot.cards.length === 0 ? (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className="rounded-2xl border border-dashed border-border-subtle bg-white/80 px-6 py-5 text-center shadow-sm">
              <div className="text-sm font-semibold text-on-surface">从一个想法开始</div>
              <div className="mt-1 text-xs text-on-surface-variant">双击画布，创建 Markdown、网页、文件或子白板卡片</div>
            </div>
          </div>
        ) : null}
      </ReactFlow>

      {controller.unsavedError ? (
        <div className="absolute right-3 top-3 z-30 flex max-w-sm items-center gap-2 rounded-lg border border-destructive/20 bg-white px-3 py-2 text-xs text-destructive shadow-md">
          {controller.unsavedError}
          <Button type="button" size="sm" variant="outline" className="h-7" onClick={() => void controller.retry()}>重试保存</Button>
        </div>
      ) : null}

      {contextError ? (
        <div className="absolute bottom-16 left-1/2 z-30 -translate-x-1/2 rounded-lg border border-destructive/20 bg-white px-3 py-2 text-xs text-destructive shadow-md" role="alert">
          {contextError}
        </div>
      ) : null}

      <WhiteboardCardDialog
        open={cardDialogOpen}
        conversationId={conversationId}
        whiteboardId={whiteboardId}
        initialType={cardDialogType}
        card={editingCard}
        onOpenChange={setCardDialogOpen}
        onSubmit={saveCard}
      />
      <WhiteboardRelationDialog
        open={Boolean(editingRelation)}
        relation={editingRelation}
        onOpenChange={open => { if (!open) setEditingRelation(null) }}
        onSubmit={saveRelation}
      />
    </div>
  )
}

export default function WhiteboardCanvas(props: WhiteboardCanvasProps) {
  return (
    <ReactFlowProvider>
      <WhiteboardCanvasInner {...props} />
    </ReactFlowProvider>
  )
}
