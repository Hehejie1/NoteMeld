import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getWhiteboard, mutateWhiteboard } from '@/services/whiteboard'
import { applyWhiteboardOperations, createWhiteboardCommand } from './whiteboardCommands'
import type {
  WhiteboardCommand,
  WhiteboardConflictState,
  WhiteboardMutationResult,
  WhiteboardOperation,
  WhiteboardSnapshot,
} from './types'

export const MAX_COMMAND_HISTORY = 100

type CommandMode = 'forward' | 'undo' | 'redo'

interface RetryEntry {
  command: WhiteboardCommand
  mode: CommandMode
  original?: WhiteboardCommand
}

interface WhiteboardApiError {
  code?: number
  msg?: string
  data?: { current_revision?: number } | null
}

export class WhiteboardRevisionConflict extends Error {
  readonly current_revision: number

  constructor(currentRevision: number) {
    super('白板已在其他窗口更新')
    this.name = 'WhiteboardRevisionConflict'
    this.current_revision = currentRevision
  }
}

export const boardMutationQueues = new Map<string, Promise<void>>()

function enqueueBoardMutation<T>(boardKey: string, run: () => Promise<T>): Promise<T> {
  const previous = boardMutationQueues.get(boardKey) ?? Promise.resolve()
  const current = previous.then(run, run)
  const tail = current.then(() => undefined, () => undefined)
  boardMutationQueues.set(boardKey, tail)
  void tail.then(() => {
    if (boardMutationQueues.get(boardKey) === tail) boardMutationQueues.delete(boardKey)
  })
  return current
}

function asConflict(error: unknown): WhiteboardRevisionConflict | null {
  if (error instanceof WhiteboardRevisionConflict) return error
  const candidate = error as WhiteboardApiError | undefined
  if (candidate?.code !== 409) return null
  const revision = candidate.data?.current_revision
  return typeof revision === 'number' ? new WhiteboardRevisionConflict(revision) : null
}

function errorMessage(error: unknown): string {
  const candidate = error as WhiteboardApiError | undefined
  return candidate?.msg || (error instanceof Error ? error.message : '白板保存失败，请重试')
}

export function mergeWhiteboardMutationResult(
  snapshot: WhiteboardSnapshot,
  result: WhiteboardMutationResult,
): WhiteboardSnapshot {
  const deletedCards = new Set(result.deleted_card_ids)
  const deletedRelations = new Set(result.deleted_relation_ids)
  const cards = new Map(
    snapshot.cards
      .filter(card => !deletedCards.has(card.id))
      .map(card => [card.id, card]),
  )
  const relations = new Map(
    snapshot.relations
      .filter(relation => !deletedRelations.has(relation.id))
      .map(relation => [relation.id, relation]),
  )
  for (const card of result.cards) cards.set(card.id, card)
  for (const relation of result.relations) relations.set(relation.id, relation)
  return {
    ...snapshot,
    revision: result.revision,
    cards: [...cards.values()],
    relations: [...relations.values()],
    viewport: result.viewport ?? snapshot.viewport,
  }
}

export interface UseWhiteboardControllerOptions {
  conversationId: string
  whiteboardId: string
}

export function useWhiteboardController({
  conversationId,
  whiteboardId,
}: UseWhiteboardControllerOptions) {
  const boardKey = JSON.stringify([conversationId, whiteboardId])
  const boardKeyRef = useRef(boardKey)
  const snapshotRef = useRef<WhiteboardSnapshot | null>(null)
  const revisionRef = useRef(0)
  const retryEntriesRef = useRef<RetryEntry[]>([])

  const [snapshot, setSnapshot] = useState<WhiteboardSnapshot | null>(null)
  const [serverRevision, setServerRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [pendingCount, setPendingCount] = useState(0)
  const [pendingCommand, setPendingCommand] = useState<WhiteboardCommand | null>(null)
  const [selectedCardIds, setSelectedCardIds] = useState<string[]>([])
  const [selectedRelationIds, setSelectedRelationIds] = useState<string[]>([])
  const [activeCardId, setActiveCardId] = useState<string | null>(null)
  const [undoStack, setUndoStack] = useState<WhiteboardCommand[]>([])
  const [redoStack, setRedoStack] = useState<WhiteboardCommand[]>([])
  const [unsavedError, setUnsavedError] = useState<string | null>(null)
  const [retryCommand, setRetryCommand] = useState<WhiteboardCommand | null>(null)
  const [conflict, setConflict] = useState<WhiteboardConflictState | null>(null)

  const replaceSnapshot = useCallback((next: WhiteboardSnapshot | null) => {
    snapshotRef.current = next
    revisionRef.current = next?.revision ?? 0
    setSnapshot(next)
    setServerRevision(next?.revision ?? 0)
    const cardIds = new Set(next?.cards.map(card => card.id) ?? [])
    const relationIds = new Set(next?.relations.map(relation => relation.id) ?? [])
    setSelectedCardIds(ids => ids.filter(id => cardIds.has(id)))
    setSelectedRelationIds(ids => ids.filter(id => relationIds.has(id)))
    setActiveCardId(id => id && cardIds.has(id) ? id : null)
  }, [])

  const reload = useCallback(async () => {
    const requestedKey = JSON.stringify([conversationId, whiteboardId])
    setLoading(true)
    setLoadError(null)
    try {
      const next = await getWhiteboard(conversationId, whiteboardId)
      if (boardKeyRef.current === requestedKey) replaceSnapshot(next)
      return next
    } catch (error) {
      if (boardKeyRef.current === requestedKey) setLoadError(errorMessage(error))
      throw error
    } finally {
      if (boardKeyRef.current === requestedKey) setLoading(false)
    }
  }, [conversationId, replaceSnapshot, whiteboardId])

  useEffect(() => {
    boardKeyRef.current = boardKey
    retryEntriesRef.current = []
    replaceSnapshot(null)
    setUndoStack([])
    setRedoStack([])
    setPendingCount(0)
    setPendingCommand(null)
    setSelectedCardIds([])
    setSelectedRelationIds([])
    setActiveCardId(null)
    setRetryCommand(null)
    setConflict(null)
    setUnsavedError(null)
    void reload().catch(() => undefined)
  }, [boardKey, reload, replaceSnapshot])

  const applyOptimistic = useCallback((operations: WhiteboardOperation[]) => {
    const current = snapshotRef.current
    if (!current) throw new Error('白板尚未加载')
    const next = applyWhiteboardOperations(current, operations)
    snapshotRef.current = next
    setSnapshot(next)
  }, [])

  const runCommand = useCallback(async (entry: RetryEntry) => {
    const { command, mode, original = command } = entry
    const commandBoardKey = boardKeyRef.current
    setPendingCount(count => count + 1)
    setPendingCommand(command)
    setUnsavedError(null)
    setConflict(null)

    try {
      return await enqueueBoardMutation(commandBoardKey, async () => {
        const revision = revisionRef.current
        try {
          const result = await mutateWhiteboard(conversationId, whiteboardId, {
            base_revision: revision,
            operations: command.forward,
          })
          if (boardKeyRef.current !== commandBoardKey) return result

          revisionRef.current = result.revision
          setServerRevision(result.revision)
          const current = snapshotRef.current
          if (current) {
            const merged = mergeWhiteboardMutationResult(current, result)
            snapshotRef.current = merged
            setSnapshot(merged)
          }
          retryEntriesRef.current = retryEntriesRef.current.filter(
            item => item.command.id !== command.id,
          )
          setRetryCommand(retryEntriesRef.current[0]?.command ?? null)

          if (mode === 'forward') {
            setUndoStack(stack => [...stack, original].slice(-MAX_COMMAND_HISTORY))
            setRedoStack([])
          } else if (mode === 'undo') {
            setUndoStack(stack => stack.filter(item => item.id !== original.id))
            setRedoStack(stack => [...stack, original].slice(-MAX_COMMAND_HISTORY))
          } else {
            setRedoStack(stack => stack.filter(item => item.id !== original.id))
            setUndoStack(stack => [...stack, original].slice(-MAX_COMMAND_HISTORY))
          }
          return result
        } catch (error) {
          if (boardKeyRef.current !== commandBoardKey) throw error
          retryEntriesRef.current = [
            ...retryEntriesRef.current.filter(item => item.command.id !== command.id),
            entry,
          ]
          setRetryCommand(command)
          const revisionConflict = asConflict(error)
          if (revisionConflict) {
            setConflict({
              kind: 'revision_conflict',
              currentRevision: revisionConflict.current_revision,
              command,
            })
            await reload().catch(() => undefined)
          } else {
            const current = snapshotRef.current
            if (current) {
              const reverted = applyWhiteboardOperations(current, command.inverse)
              snapshotRef.current = reverted
              setSnapshot(reverted)
            }
            setUnsavedError(errorMessage(error))
          }
          throw error
        }
      })
    } finally {
      if (boardKeyRef.current === commandBoardKey) {
        setPendingCount(count => Math.max(0, count - 1))
        setPendingCommand(current => current?.id === command.id ? null : current)
      }
    }
  }, [conversationId, reload, whiteboardId])

  const submitCommand = useCallback((command: WhiteboardCommand) => {
    applyOptimistic(command.forward)
    return runCommand({ command, mode: 'forward' })
  }, [applyOptimistic, runCommand])

  const submitOperations = useCallback((operations: WhiteboardOperation[], label?: string) => {
    const current = snapshotRef.current
    if (!current) return Promise.reject(new Error('白板尚未加载'))
    return submitCommand(createWhiteboardCommand(current, operations, label))
  }, [submitCommand])

  const undo = useCallback(() => {
    const original = undoStack[undoStack.length - 1]
    if (!original || pendingCount > 0) return Promise.resolve(null)
    const command: WhiteboardCommand = {
      id: `undo:${original.id}:${Date.now()}`,
      label: `撤销：${original.label}`,
      forward: original.inverse,
      inverse: original.forward,
    }
    applyOptimistic(command.forward)
    return runCommand({ command, mode: 'undo', original })
  }, [applyOptimistic, pendingCount, runCommand, undoStack])

  const redo = useCallback(() => {
    const original = redoStack[redoStack.length - 1]
    if (!original || pendingCount > 0) return Promise.resolve(null)
    const command: WhiteboardCommand = {
      id: `redo:${original.id}:${Date.now()}`,
      label: `重做：${original.label}`,
      forward: original.forward,
      inverse: original.inverse,
    }
    applyOptimistic(command.forward)
    return runCommand({ command, mode: 'redo', original })
  }, [applyOptimistic, pendingCount, redoStack, runCommand])

  const retry = useCallback(() => {
    const entry = retryEntriesRef.current[0]
    if (!entry || pendingCount > 0) return Promise.resolve(null)
    applyOptimistic(entry.command.forward)
    return runCommand(entry)
  }, [applyOptimistic, pendingCount, runCommand])

  const discardRetry = useCallback(() => {
    retryEntriesRef.current = retryEntriesRef.current.slice(1)
    setRetryCommand(retryEntriesRef.current[0]?.command ?? null)
    setConflict(null)
    setUnsavedError(null)
  }, [])

  const setSelection = useCallback((cardIds: readonly string[], relationIds: readonly string[]) => {
    setSelectedCardIds([...new Set(cardIds)])
    setSelectedRelationIds([...new Set(relationIds)])
  }, [])

  return useMemo(() => ({
    snapshot,
    serverRevision,
    loading,
    loadError,
    pending: pendingCount > 0,
    pendingCommand,
    selectedCardIds,
    selectedRelationIds,
    activeCardId,
    undoStack,
    redoStack,
    canUndo: undoStack.length > 0 && pendingCount === 0,
    canRedo: redoStack.length > 0 && pendingCount === 0,
    unsavedError,
    retryCommand,
    conflict,
    reload,
    submitCommand,
    submitOperations,
    undo,
    redo,
    retry,
    discardRetry,
    setSelection,
    setActiveCardId,
  }), [
    conflict,
    discardRetry,
    loadError,
    loading,
    pendingCommand,
    pendingCount,
    selectedCardIds,
    selectedRelationIds,
    activeCardId,
    redo,
    redoStack,
    reload,
    retry,
    retryCommand,
    serverRevision,
    snapshot,
    submitCommand,
    submitOperations,
    setSelection,
    undo,
    undoStack,
    unsavedError,
  ])
}
