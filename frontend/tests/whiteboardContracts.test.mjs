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
] = await Promise.all([
  read('src/services/chat.ts'),
  read('src/store/taskStore/index.ts'),
  read('src/services/whiteboard.ts'),
  read('src/pages/HomePage/whiteboard/types.ts'),
  read('src/pages/HomePage/whiteboard/whiteboardProjection.ts'),
  read('src/pages/HomePage/whiteboard/whiteboardCommands.ts'),
  read('src/pages/HomePage/whiteboard/useWhiteboardController.ts'),
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

console.log('whiteboard frontend contracts passed')
