export type WhiteboardCardType = 'markdown' | 'web' | 'file' | 'whiteboard'
export type WhiteboardRelationType =
  | 'related'
  | 'supports'
  | 'challenges'
  | 'depends_on'
  | 'contains'
  | 'custom'
export type WhiteboardLineType = 'bezier' | 'straight' | 'smoothstep'
export type WhiteboardRelationDirection = 'none' | 'forward' | 'backward' | 'both'
export type WhiteboardRelationColor = 'default' | 'muted' | 'accent' | 'positive' | 'warning' | 'danger'
export type WhiteboardRelationWidth = 'thin' | 'medium' | 'thick'
export type WhiteboardRelationPattern = 'solid' | 'dashed' | 'dotted'

export interface WhiteboardSourceRef {
  source_id: string
  source_type: string
  title: string
  url?: string | null
  task_id?: string | null
}

export interface WhiteboardPosition {
  x: number
  y: number
}

export interface WhiteboardSize {
  width: number
  height: number
}

export interface WhiteboardViewport extends WhiteboardPosition {
  zoom: number
}

export interface MarkdownCardContent {
  markdown: string
}

export interface WebCardContent {
  url: string
  preview_title?: string
  preview_image?: string
  media_type?: string
}

export interface FileCardContent {
  upload_id: string
}

export interface NestedWhiteboardCardContent {
  child_whiteboard_id: string
}

interface WhiteboardCardBase {
  id: string
  title: string
  description: string
  source_refs: WhiteboardSourceRef[]
  position: WhiteboardPosition
  size: WhiteboardSize
  z_index: number
  collapsed: boolean
}

export type WhiteboardCard =
  | (WhiteboardCardBase & { type: 'markdown'; content: MarkdownCardContent })
  | (WhiteboardCardBase & { type: 'web'; content: WebCardContent })
  | (WhiteboardCardBase & { type: 'file'; content: FileCardContent })
  | (WhiteboardCardBase & { type: 'whiteboard'; content: NestedWhiteboardCardContent })

export interface WhiteboardRelationStyle {
  color?: WhiteboardRelationColor
  width?: WhiteboardRelationWidth
  pattern?: WhiteboardRelationPattern
}

export interface WhiteboardRelation {
  id: string
  source_card_id: string
  target_card_id: string
  relation_type: WhiteboardRelationType
  label: string
  description: string
  line_type: WhiteboardLineType
  direction: WhiteboardRelationDirection
  source_refs: WhiteboardSourceRef[]
  style: WhiteboardRelationStyle
}

export interface WhiteboardNoteLink {
  note_task_id: string
  published_revision: number
  published_at?: string | null
  updated_at?: string | null
}

export interface WhiteboardSummary {
  id: string
  conversation_id: string
  title: string
  description: string
  schema_version: number
  revision: number
  legacy_canvas_id?: string | null
  status: 'active' | 'archived'
  updated_at?: string | null
}

export interface WhiteboardSnapshot {
  id: string
  conversation_id: string
  title: string
  description: string
  schema_version: number
  revision: number
  viewport: WhiteboardViewport
  cards: WhiteboardCard[]
  relations: WhiteboardRelation[]
  note_link: WhiteboardNoteLink | null
  legacy_canvas_id: string | null
}

export type WhiteboardCardPatch = Partial<
  Pick<WhiteboardCard, 'type' | 'title' | 'description' | 'content' | 'source_refs' | 'z_index' | 'collapsed'>
>

export type WhiteboardRelationPatch = Partial<
  Pick<
    WhiteboardRelation,
    | 'source_card_id'
    | 'target_card_id'
    | 'relation_type'
    | 'label'
    | 'description'
    | 'line_type'
    | 'direction'
    | 'source_refs'
    | 'style'
  >
>

export interface CardMoveResizeItem {
  card_id: string
  position?: WhiteboardPosition
  size?: WhiteboardSize
}

export type WhiteboardOperation =
  | { op: 'card.create'; card: WhiteboardCard }
  | { op: 'card.update'; card_id: string; patch: WhiteboardCardPatch }
  | { op: 'card.delete'; card_id: string }
  | { op: 'card.move_resize'; items: CardMoveResizeItem[] }
  | { op: 'relation.create'; relation: WhiteboardRelation }
  | { op: 'relation.update'; relation_id: string; patch: WhiteboardRelationPatch }
  | { op: 'relation.delete'; relation_id: string }
  | { op: 'viewport.update'; x: number; y: number; zoom: number }

export interface MutateWhiteboardPayload {
  base_revision: number
  operations: WhiteboardOperation[]
}

export interface WhiteboardMutationResult {
  revision: number
  cards: WhiteboardCard[]
  relations: WhiteboardRelation[]
  deleted_card_ids: string[]
  deleted_relation_ids: string[]
  viewport?: WhiteboardViewport | null
}

export interface WhiteboardContextPayload {
  revision: number
  card_ids: string[]
  relation_ids: string[]
  label: string
}

export interface WhiteboardPublishPayload {
  base_revision: number
  scope: 'all' | 'selection'
  card_ids: string[]
  relation_ids: string[]
  provider_id?: string | null
  model_name?: string | null
}

export interface WhiteboardPublishResult {
  whiteboard_id: string
  note_task_id: string
  published_revision: number
  status: 'published' | 'partial'
  wiki_status: string
  diagnostics: string[]
  retry_actions: Array<Record<string, string>>
  message: string
}

export interface WhiteboardCommand {
  id: string
  label: string
  forward: WhiteboardOperation[]
  inverse: WhiteboardOperation[]
}

export interface WhiteboardConflictState {
  kind: 'revision_conflict'
  currentRevision: number
  command: WhiteboardCommand
}
