import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import ts from 'typescript'

const root = path.resolve(import.meta.dirname, '..')
const read = relativePath => readFile(path.join(root, relativePath), 'utf8')

const [
  chatService,
  taskStore,
  whiteboardService,
  types,
  projection,
  commands,
  controller,
  canvas,
  cardNode,
  cardContent,
  relationEdge,
  toolbar,
  selectionToolbar,
  cardDialog,
  relationDialog,
] = await Promise.all([
  read('src/services/chat.ts'),
  read('src/store/taskStore/index.ts'),
  read('src/services/whiteboard.ts'),
  read('src/pages/HomePage/whiteboard/types.ts'),
  read('src/pages/HomePage/whiteboard/whiteboardProjection.ts'),
  read('src/pages/HomePage/whiteboard/whiteboardCommands.ts'),
  read('src/pages/HomePage/whiteboard/useWhiteboardController.ts'),
  read('src/pages/HomePage/whiteboard/WhiteboardCanvas.tsx'),
  read('src/pages/HomePage/whiteboard/WhiteboardCardNode.tsx'),
  read('src/pages/HomePage/whiteboard/WhiteboardCardContent.tsx'),
  read('src/pages/HomePage/whiteboard/WhiteboardRelationEdge.tsx'),
  read('src/pages/HomePage/whiteboard/WhiteboardToolbar.tsx'),
  read('src/pages/HomePage/whiteboard/WhiteboardSelectionToolbar.tsx'),
  read('src/pages/HomePage/whiteboard/WhiteboardCardDialog.tsx'),
  read('src/pages/HomePage/whiteboard/WhiteboardRelationDialog.tsx'),
])

assert.match(chatService, /type:\s*'whiteboard_selection'/)
assert.match(chatService, /whiteboard_id:\s*string/)
assert.match(chatService, /revision:\s*number/)
assert.match(chatService, /card_ids:\s*string\[\]/)
assert.match(chatService, /relation_ids:\s*string\[\]/)
assert.match(chatService, /snapshot:\s*string/, '服务端 canonical snapshot 必须进入引用类型')

for (const segment of [
  '/whiteboards',
  '/mutations',
  '/context',
  '/publish-note',
  '/from-learning-canvas/',
]) {
  assert.ok(whiteboardService.includes(segment), `whiteboard API 必须包含 ${segment}`)
}
assert.match(whiteboardService, /encodeURIComponent\(conversationId\)/)
assert.match(whiteboardService, /encodeURIComponent\(whiteboardId\)/)
assert.match(whiteboardService, /encodeURIComponent\(canvasId\)/)
assert.match(
  whiteboardService,
  /publishWhiteboard[^]*?timeout:\s*0/,
  '发布请求必须禁用 Axios 默认 10 秒 timeout，等待后端 LLM 总预算',
)

assert.doesNotMatch(types, /@xyflow\/react|\bNode\b|\bEdge\b/, '领域类型不得依赖 React Flow')
assert.match(types, /base_revision:\s*number/)
assert.match(types, /op:\s*'card\.move_resize'/)
assert.doesNotMatch(types, /sourceHandle|targetHandle|dragging|measured/, '领域类型不得持久化渲染器字段')

assert.match(projection, /from '@xyflow\/react'/)
assert.match(projection, /projectWhiteboard/)
assert.match(projection, /cardMoveResizeOperation/)
assert.match(projection, /position:\s*\{\s*x:/)
assert.match(projection, /style:\s*\{\s*width:\s*card\.size\.width,\s*height:\s*card\.size\.height\s*\}/)
assert.match(projection, /source:\s*relation\.source_card_id/)
assert.match(projection, /target:\s*relation\.target_card_id/)

assert.match(commands, /inverse/)
assert.match(commands, /createWhiteboardCommand/)
assert.match(commands, /applyWhiteboardOperations/)
assert.match(commands, /copyWhiteboardSelection/)
assert.match(commands, /buildPasteOperations/)
assert.match(commands, /rebaseWhiteboardCommand/)

assert.match(controller, /base_revision:\s*revision/)
assert.match(controller, /WhiteboardRevisionConflict/)
assert.match(controller, /current_revision/)
assert.match(controller, /MAX_COMMAND_HISTORY\s*=\s*100/)
assert.match(controller, /boardMutationQueues/)
assert.match(controller, /JSON\.stringify\(\[conversationId, whiteboardId\]\)/)
assert.match(controller, /\.then\(run,\s*run\)/, '同一 controller 的 mutation 必须串行入队')
assert.match(controller, /setServerRevision\(result\.revision\)/)
assert.match(controller, /selectedCardIds/)
assert.match(controller, /selectedRelationIds/)
assert.match(controller, /activeCardId/)
assert.match(controller, /setSelection/)
assert.match(controller, /undoStack.*slice\(-MAX_COMMAND_HISTORY\)/s)
assert.match(controller, /setRetryCommand\(command\)/)
assert.match(controller, /retryEntriesRef/)
assert.match(controller, /filter\(item => item\.command\.id !== command\.id\)/)
assert.match(controller, /setPendingCount\(0\)/)
assert.match(controller, /setPendingCommand\(null\)/)
assert.match(controller, /await\s+reload\(\)/)
assert.match(controller, /applyWhiteboardOperations\([^]*command\.inverse/s)
assert.match(controller, /rebaseWhiteboardCommand\(current, entry\.command\)/)

assert.match(canvas, /ReactFlowProvider/)
assert.match(canvas, /onlyRenderVisibleElements/)
assert.match(canvas, /selectionOnDrag/)
assert.match(canvas, /panOnDrag=\{\[1,\s*2\]\}/)
assert.match(canvas, /zoomOnDoubleClick=\{false\}/, '画布双击创建卡片时不得同时触发默认缩放')
assert.match(canvas, /screenToFlowPosition/)
assert.match(canvas, /onPaneDoubleClick/)
assert.match(canvas, /onNodeDragStop/)
assert.match(canvas, /onEdgeDoubleClick/)
assert.match(canvas, /onReconnect/)
assert.match(canvas, /deleteKeyCode=\{null\}/)
assert.match(canvas, /copyWhiteboardSelection/)
assert.match(canvas, /buildPasteOperations/)
assert.match(canvas, /offset:\s*32/)
assert.match(canvas, /createWhiteboardContext/)
assert.match(canvas, /addContextRef/)
assert.match(canvas, /setActiveCardId/)
assert.match(canvas, /onSelectionChange/)

assert.match(cardNode, /NodeResizer/)
assert.match(cardNode, /isVisible=\{selected\}/)
assert.match(cardNode, /source_refs\.slice\(0,\s*3\)/)
assert.match(cardNode, /line-clamp-2/)
assert.match(cardNode, /<Handle/)
assert.match(cardNode, /nodrag/)
assert.match(cardNode, /nopan/)
assert.match(cardNode, /data\.active\s*&&\s*\(/)
assert.match(cardNode, /memo\(/)
assert.doesNotMatch(
  cardNode,
  /ReactMarkdown|<iframe|<video|<audio|<object|<embed/,
  '紧凑卡片 shell 不得挂载重型正文或媒体 renderer',
)

assert.match(cardContent, /lazy\(/, '网页和文件内容必须惰性创建')
assert.match(cardContent, /ChatMarkdown/, 'Markdown 必须复用现有安全 renderer')
assert.match(cardContent, /openExternalUrl/)
assert.match(cardContent, /child_whiteboard_id/)
assert.match(cardContent, /upload_id/)

assert.match(relationEdge, /getBezierPath/)
assert.match(relationEdge, /getStraightPath/)
assert.match(relationEdge, /getSmoothStepPath/)
assert.match(relationEdge, /EdgeLabelRenderer|EdgeToolbar/)
assert.match(relationEdge, /interactionWidth/)
assert.match(relationEdge, /memo\(/)

assert.match(toolbar, /fitView/)
assert.match(toolbar, /zoomIn/)
assert.match(toolbar, /zoomOut/)
assert.match(toolbar, /撤销/)
assert.match(toolbar, /重做/)
assert.match(selectionToolbar, /添加到对话/)
assert.match(selectionToolbar, /复制/)
assert.match(selectionToolbar, /删除/)

assert.match(cardDialog, /markdown/)
assert.match(cardDialog, /web/)
assert.match(cardDialog, /file/)
assert.match(cardDialog, /whiteboard/)
assert.match(cardDialog, /https?:/)
assert.match(cardDialog, /nodrag/)
assert.match(cardDialog, /nopan/)
assert.match(relationDialog, /bezier/)
assert.match(relationDialog, /straight/)
assert.match(relationDialog, /smoothstep/)
assert.match(relationDialog, /direction/)

assert.match(taskStore, /\.slice\(-8\)/, '引用 chip 数量必须继续限制为 8')
assert.match(taskStore, /reference\.type === 'whiteboard_selection' \? 12000 : 2000/)
assert.match(taskStore, /state\.currentTaskId === taskId \? state\.pendingContextRefs : \[\]/)
assert.match(taskStore, /clearContextRefs:\s*\(\)\s*=>\s*set\(\{\s*pendingContextRefs:\s*\[\]/)

const commandsModule = await import(
  `data:text/javascript;base64,${Buffer.from(
    ts.transpileModule(commands, {
      compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText,
  ).toString('base64')}`
)

const sampleBoard = {
  id: 'wb_1',
  conversation_id: 'conv_1',
  title: 'Argument map',
  description: '',
  schema_version: 1,
  revision: 3,
  viewport: { x: 0, y: 0, zoom: 1 },
  cards: [
    {
      id: 'card_a', type: 'markdown', title: 'A', description: '',
      content: { markdown: 'A body' }, source_refs: [], position: { x: 10, y: 20 },
      size: { width: 300, height: 170 }, z_index: 0, collapsed: true,
    },
    {
      id: 'card_b', type: 'markdown', title: 'B', description: '',
      content: { markdown: 'B body' }, source_refs: [], position: { x: 400, y: 20 },
      size: { width: 300, height: 170 }, z_index: 0, collapsed: true,
    },
  ],
  relations: [
    {
      id: 'rel_ab', source_card_id: 'card_a', target_card_id: 'card_b',
      relation_type: 'supports', label: 'supports', description: '', line_type: 'bezier',
      direction: 'forward', source_refs: [], style: {},
    },
  ],
  note_link: null,
  legacy_canvas_id: null,
}

const move = commandsModule.createWhiteboardCommand(sampleBoard, [{
  op: 'card.move_resize',
  items: [{ card_id: 'card_a', position: { x: 90, y: 80 } }],
}], 'move', 'move-1')
const moved = commandsModule.applyWhiteboardOperations(sampleBoard, move.forward)
const restored = commandsModule.applyWhiteboardOperations(moved, move.inverse)
assert.deepEqual(restored.cards[0].position, sampleBoard.cards[0].position)

const deletion = commandsModule.createWhiteboardCommand(
  sampleBoard,
  [{ op: 'card.delete', card_id: 'card_a' }],
  'delete',
  'delete-1',
)
const deleted = commandsModule.applyWhiteboardOperations(sampleBoard, deletion.forward)
const undeleted = commandsModule.applyWhiteboardOperations(deleted, deletion.inverse)
assert.equal(undeleted.cards.length, 2)
assert.equal(undeleted.relations.length, 1, '撤销卡片删除必须恢复同事务删除的关系')

const copied = commandsModule.copyWhiteboardSelection(sampleBoard, [], ['rel_ab'])
assert.deepEqual(copied.cards.map(card => card.id), ['card_a', 'card_b'])
const pasted = commandsModule.buildPasteOperations(copied, {
  offset: 40,
  createId: (kind, oldId) => `${kind}_copy_${oldId}`,
})
assert.equal(pasted.filter(operation => operation.op === 'card.create').length, 2)
assert.equal(pasted.filter(operation => operation.op === 'relation.create').length, 1)

const retryInitial = {
  ...sampleBoard,
  cards: sampleBoard.cards.map(card => card.id === 'card_a' ? { ...card, title: '0' } : card),
}
const failedA = commandsModule.createWhiteboardCommand(
  retryInitial,
  [{ op: 'card.update', card_id: 'card_a', patch: { title: '1' } }],
  'A',
  'A-1',
)
const afterAFailure = commandsModule.applyWhiteboardOperations(
  commandsModule.applyWhiteboardOperations(retryInitial, failedA.forward),
  failedA.inverse,
)
const successfulB = commandsModule.createWhiteboardCommand(
  afterAFailure,
  [{ op: 'card.update', card_id: 'card_a', patch: { title: '2' } }],
  'B',
  'B-1',
)
const afterBSuccess = commandsModule.applyWhiteboardOperations(afterAFailure, successfulB.forward)
const rebasedA = commandsModule.rebaseWhiteboardCommand(afterBSuccess, failedA)
const afterRetryFailure = commandsModule.applyWhiteboardOperations(
  commandsModule.applyWhiteboardOperations(afterBSuccess, rebasedA.forward),
  rebasedA.inverse,
)
assert.equal(afterRetryFailure.cards.find(card => card.id === 'card_a').title, '2')
assert.equal(afterRetryFailure.revision, retryInitial.revision)

console.log('whiteboard frontend contracts passed')
