import type {
  WhiteboardCard,
  WhiteboardCardPatch,
  WhiteboardCommand,
  WhiteboardOperation,
  WhiteboardRelation,
  WhiteboardRelationPatch,
  WhiteboardSnapshot,
} from './types'

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T

export function applyWhiteboardOperations(
  snapshot: WhiteboardSnapshot,
  operations: readonly WhiteboardOperation[],
): WhiteboardSnapshot {
  const next = clone(snapshot)

  for (const operation of operations) {
    switch (operation.op) {
      case 'card.create':
        next.cards.push(clone(operation.card))
        break
      case 'card.update':
        next.cards = next.cards.map(card =>
          card.id === operation.card_id
            ? ({ ...card, ...clone(operation.patch) } as WhiteboardCard)
            : card,
        )
        break
      case 'card.delete':
        next.cards = next.cards.filter(card => card.id !== operation.card_id)
        next.relations = next.relations.filter(
          relation => relation.source_card_id !== operation.card_id && relation.target_card_id !== operation.card_id,
        )
        break
      case 'card.move_resize': {
        const items = new Map(operation.items.map(item => [item.card_id, item]))
        next.cards = next.cards.map(card => {
          const item = items.get(card.id)
          if (!item) return card
          return {
            ...card,
            position: item.position ? clone(item.position) : card.position,
            size: item.size ? clone(item.size) : card.size,
          }
        })
        break
      }
      case 'relation.create':
        next.relations.push(clone(operation.relation))
        break
      case 'relation.update':
        next.relations = next.relations.map(relation =>
          relation.id === operation.relation_id
            ? { ...relation, ...clone(operation.patch) }
            : relation,
        )
        break
      case 'relation.delete':
        next.relations = next.relations.filter(relation => relation.id !== operation.relation_id)
        break
      case 'viewport.update':
        next.viewport = { x: operation.x, y: operation.y, zoom: operation.zoom }
        break
    }
  }

  return next
}

function inverseForOperation(
  snapshot: WhiteboardSnapshot,
  operation: WhiteboardOperation,
): WhiteboardOperation[] {
  switch (operation.op) {
    case 'card.create':
      return [{ op: 'card.delete', card_id: operation.card.id }]
    case 'card.update': {
      const card = snapshot.cards.find(item => item.id === operation.card_id)
      if (!card) throw new Error(`Card ${operation.card_id} does not exist`)
      const previous: Record<string, unknown> = {}
      for (const key of Object.keys(operation.patch)) {
        previous[key] = clone((card as unknown as Record<string, unknown>)[key])
      }
      if ('type' in operation.patch && !('content' in previous)) previous.content = clone(card.content)
      return [{ op: 'card.update', card_id: card.id, patch: previous as WhiteboardCardPatch }]
    }
    case 'card.delete': {
      const card = snapshot.cards.find(item => item.id === operation.card_id)
      if (!card) throw new Error(`Card ${operation.card_id} does not exist`)
      const relations = snapshot.relations.filter(
        relation => relation.source_card_id === card.id || relation.target_card_id === card.id,
      )
      return [
        { op: 'card.create', card: clone(card) },
        ...relations.map<WhiteboardOperation>(relation => ({ op: 'relation.create', relation: clone(relation) })),
      ]
    }
    case 'card.move_resize':
      return [{
        op: 'card.move_resize',
        items: operation.items.map(item => {
          const card = snapshot.cards.find(candidate => candidate.id === item.card_id)
          if (!card) throw new Error(`Card ${item.card_id} does not exist`)
          return {
            card_id: card.id,
            ...('position' in item ? { position: clone(card.position) } : {}),
            ...('size' in item ? { size: clone(card.size) } : {}),
          }
        }),
      }]
    case 'relation.create':
      return [{ op: 'relation.delete', relation_id: operation.relation.id }]
    case 'relation.update': {
      const relation = snapshot.relations.find(item => item.id === operation.relation_id)
      if (!relation) throw new Error(`Relation ${operation.relation_id} does not exist`)
      const previous: Record<string, unknown> = {}
      for (const key of Object.keys(operation.patch)) {
        previous[key] = clone((relation as unknown as Record<string, unknown>)[key])
      }
      return [{ op: 'relation.update', relation_id: relation.id, patch: previous as WhiteboardRelationPatch }]
    }
    case 'relation.delete': {
      const relation = snapshot.relations.find(item => item.id === operation.relation_id)
      if (!relation) throw new Error(`Relation ${operation.relation_id} does not exist`)
      return [{ op: 'relation.create', relation: clone(relation) }]
    }
    case 'viewport.update':
      return [{ op: 'viewport.update', ...clone(snapshot.viewport) }]
  }
}

export function createWhiteboardCommand(
  snapshot: WhiteboardSnapshot,
  forward: WhiteboardOperation[],
  label = '白板操作',
  id = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
): WhiteboardCommand {
  let working = snapshot
  const inverse: WhiteboardOperation[] = []
  for (const operation of forward) {
    inverse.unshift(...inverseForOperation(working, operation))
    working = applyWhiteboardOperations(working, [operation])
  }
  return { id, label, forward: clone(forward), inverse }
}

export interface WhiteboardClipboard {
  cards: WhiteboardCard[]
  relations: WhiteboardRelation[]
}

export function copyWhiteboardSelection(
  snapshot: WhiteboardSnapshot,
  cardIds: readonly string[],
  relationIds: readonly string[],
): WhiteboardClipboard {
  const selectedCards = new Set(cardIds)
  for (const relation of snapshot.relations) {
    if (relationIds.includes(relation.id)) {
      selectedCards.add(relation.source_card_id)
      selectedCards.add(relation.target_card_id)
    }
  }
  const cards = snapshot.cards.filter(card => selectedCards.has(card.id)).map(clone)
  const relations = snapshot.relations
    .filter(relation => selectedCards.has(relation.source_card_id) && selectedCards.has(relation.target_card_id))
    .map(clone)
  return { cards, relations }
}

export function buildPasteOperations(
  clipboard: WhiteboardClipboard,
  options: { offset?: number; createId?: (kind: 'card' | 'relation', oldId: string) => string } = {},
): WhiteboardOperation[] {
  const offset = options.offset ?? 32
  const createId = options.createId ?? ((kind: 'card' | 'relation') =>
    `${kind}_${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}_${Math.random()}`}`)
  const cardIds = new Map(clipboard.cards.map(card => [card.id, createId('card', card.id)]))
  return [
    ...clipboard.cards.map<WhiteboardOperation>(card => ({
      op: 'card.create',
      card: {
        ...clone(card),
        id: cardIds.get(card.id)!,
        position: { x: card.position.x + offset, y: card.position.y + offset },
      },
    })),
    ...clipboard.relations.map<WhiteboardOperation>(relation => ({
      op: 'relation.create',
      relation: {
        ...clone(relation),
        id: createId('relation', relation.id),
        source_card_id: cardIds.get(relation.source_card_id)!,
        target_card_id: cardIds.get(relation.target_card_id)!,
      },
    })),
  ]
}
