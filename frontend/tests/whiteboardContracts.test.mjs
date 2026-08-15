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
  interactions,
  panel,
  panelState,
  home,
  composer,
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
  read('src/pages/HomePage/whiteboard/whiteboardInteractions.ts'),
  read('src/pages/HomePage/whiteboard/WhiteboardPanel.tsx'),
  read('src/pages/HomePage/whiteboard/whiteboardPanelState.ts'),
  read('src/pages/HomePage/Home.tsx'),
  read('src/pages/HomePage/components/ChatComposer.tsx'),
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
  '/assets',
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
assert.match(canvas, /onMoveEnd/)
assert.match(canvas, /createViewportCommitter/)
assert.match(canvas, /resolveContextForCurrentTask/)
assert.match(canvas, /deleteKeyCode=\{null\}/)
assert.match(canvas, /copyWhiteboardSelection/)
assert.match(canvas, /buildPasteOperations/)
assert.match(canvas, /offset:\s*32/)
assert.match(canvas, /createWhiteboardContext/)
assert.match(canvas, /addContextRef/)
assert.match(canvas, /setActiveCardId/)
assert.match(canvas, /onSelectionChange/)
assert.match(canvas, /minZoom=\{0\.1\}/)

assert.match(cardNode, /NodeResizer/)
assert.match(cardNode, /isVisible=\{selected\}/)
assert.match(cardNode, /minWidth=\{220\}/)
assert.match(cardNode, /minHeight=\{120\}/)
assert.match(cardNode, /maxWidth=\{960\}/)
assert.match(cardNode, /maxHeight=\{720\}/)
assert.match(cardNode, /role="group"/)
assert.match(cardNode, /tabIndex=\{0\}/)
assert.match(cardNode, /event\.key !== 'Enter'.*event\.key !== ' '/s)
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
assert.match(cardContent, /\/api\/uploads\//)
assert.match(cardContent, /资源不存在|文件加载失败/)

assert.match(relationEdge, /getBezierPath/)
assert.match(relationEdge, /getStraightPath/)
assert.match(relationEdge, /getSmoothStepPath/)
assert.match(relationEdge, /EdgeLabelRenderer|EdgeToolbar/)
assert.match(relationEdge, /interactionWidth/)
assert.match(relationEdge, /memo\(/)
assert.match(relationEdge, /aria-label=\{`编辑关系/)
assert.match(relationEdge, /onClick=\{\(\) => props\.data\?\.onEdit/)

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
assert.match(cardDialog, /type="file"/)
assert.match(cardDialog, /uploadFile/)
assert.match(cardDialog, /uploadFileForWhiteboardCard/)
assert.match(cardDialog, /registerWhiteboardAsset/)
assert.match(cardDialog, /conversationId/)
assert.match(cardDialog, /whiteboardId/)
assert.match(cardDialog, /fileRegistrationFailed/)
assert.match(cardDialog, /type === 'file' && fileRegistrationFailed/)
assert.match(relationDialog, /bezier/)
assert.match(relationDialog, /straight/)
assert.match(relationDialog, /smoothstep/)
assert.match(relationDialog, /direction/)
assert.match(interactions, /createViewportCommitter/)
assert.match(interactions, /uploadFileForWhiteboardCard/)
assert.match(interactions, /resolveContextForCurrentTask/)

assert.match(home, /WhiteboardPanel/, 'Home 必须优先挂载语义白板工作区')
assert.match(home, /resolveLatestLearningWorkspace/, 'Home 必须按最新 compact message 恢复白板')
assert.match(home, /seedLearningCanvasWhiteboard/, 'legacy canvas 必须幂等转换为语义白板')
assert.match(home, /LearningCanvasCard/, 'seed 或 feature flag 失败时必须保留 Sigma fallback')
const automaticSeedStart = home.indexOf('let active = true\n    runLegacyWhiteboardSeed')
const automaticSeedEnd = home.indexOf('const retryWhiteboardSeed')
assert.notEqual(
  automaticSeedStart,
  -1,
  'automatic seed contract 必须锚定真实 effect，不能 slice(-1) 空跑',
)
assert.notEqual(automaticSeedEnd, -1)
assert.ok(automaticSeedEnd > automaticSeedStart)
const automaticSeedSection = home.slice(automaticSeedStart, automaticSeedEnd)
assert.doesNotMatch(automaticSeedSection, /navigate\(/, 'legacy seed 不得通过导航重挂载 composer')
assert.match(panel, /useBackendInitContext/, '白板请求必须服从 backend ready gate')
assert.match(panel, /h-full[\s\S]*min-h-0/, 'WhiteboardPanel 必须占满右栏剩余高度')
assert.match(`${panel}\n${panelState}`, /尚未发布/)
assert.match(panelState, /有未发布变更/)
assert.match(panelState, /已同步到笔记/)
assert.match(panel, /发布为笔记/)
assert.match(panelState, /更新笔记/)
assert.match(panel, /publishWhiteboard/)
assert.match(panelState, /published_revision/)
assert.match(panel, /breadcrumb|面包屑/i, '子白板必须在同一个 panel 中保留 breadcrumb')
assert.match(panel, /重新加载/)
assert.match(panel, /重新应用/)
assert.match(panel, /LearningCanvasCard/, 'fatal load 必须能回退 legacy Sigma')
assert.match(composer, /card_ids\.length/)
assert.match(composer, /relation_ids\.length/)

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

const interactionsModule = await import(
  `data:text/javascript;base64,${Buffer.from(
    ts.transpileModule(interactions, {
      compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText,
  ).toString('base64')}`
)

const panelStateModule = await import(
  `data:text/javascript;base64,${Buffer.from(
    ts.transpileModule(panelState, {
      compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText,
  ).toString('base64')}`
)

const latestWorkspace = panelStateModule.resolveLatestLearningWorkspace([
  { id: 'legacy', message_type: 'learning_canvas', meta: { canvas_id: 'canvas_old', status: 'ready' } },
  { id: 'current', message_type: 'learning_canvas', meta: { canvas_id: 'canvas_new', whiteboard_id: 'wb_new', status: 'ready' } },
])
assert.deepEqual(latestWorkspace, {
  messageId: 'current',
  canvasId: 'canvas_new',
  whiteboardId: 'wb_new',
  status: 'ready',
})
assert.equal(
  panelStateModule.resolveLatestLearningWorkspace([
    { id: 'clarify', message_type: 'learning_canvas', meta: { canvas_id: 'canvas_clarify', status: 'clarifying' } },
  ]),
  null,
  '澄清消息不得生成空白板工作区',
)
assert.deepEqual(
  panelStateModule.getWhiteboardPublishPresentation({ revision: 3, noteLink: null }),
  { state: 'unpublished', label: '尚未发布', actionLabel: '发布为笔记' },
)
assert.deepEqual(
  panelStateModule.getWhiteboardPublishPresentation({ revision: 4, noteLink: { published_revision: 3 } }),
  { state: 'stale', label: '有未发布变更', actionLabel: '更新笔记' },
)
assert.deepEqual(
  panelStateModule.getWhiteboardPublishPresentation({ revision: 4, noteLink: { published_revision: 4 } }),
  { state: 'synced', label: '已同步到笔记', actionLabel: '更新笔记' },
)
const seedAttempts = panelStateModule.createSeedAttemptRegistry()
assert.equal(seedAttempts.claim('conv_1', 'message_1'), true)
assert.equal(seedAttempts.claim('conv_1', 'message_1'), false, '同一 compact message 自动 seed 只能执行一次')
seedAttempts.release('conv_1', 'message_1')
assert.equal(seedAttempts.claim('conv_1', 'message_1'), true, '用户重试必须能重新执行 seed')
const activeSeedKey = panelStateModule.createLearningSeedKey('conv_1', 'message_1', 'canvas_1')
assert.equal(
  panelStateModule.resolveWhiteboardId('', activeSeedKey, { key: activeSeedKey, id: 'seeded_board' }),
  'seeded_board',
)
assert.equal(
  panelStateModule.resolveWhiteboardId('', activeSeedKey, { key: 'previous_conversation', id: 'stale_board' }),
  '',
)
assert.equal(
  panelStateModule.resolveWhiteboardId('compact_board', activeSeedKey, { key: activeSeedKey, id: 'seeded_board' }),
  'compact_board',
)

const scheduled = new Map()
let nextTimerId = 1
const viewportCommits = []
const viewportCommitter = interactionsModule.createViewportCommitter(
  viewport => viewportCommits.push(viewport),
  500,
  {
    setTimeout: callback => {
      const id = nextTimerId++
      scheduled.set(id, () => {
        scheduled.delete(id)
        callback()
      })
      return id
    },
    clearTimeout: id => scheduled.delete(id),
  },
)
viewportCommitter.schedule({ x: 10, y: 20, zoom: 0.8 })
viewportCommitter.schedule({ x: 30, y: 40, zoom: 0.7 })
viewportCommitter.schedule({ x: 50, y: 60, zoom: 0.6 })
assert.equal(scheduled.size, 1, '视口移动必须合并为一个 500ms debounce')
assert.equal(viewportCommits.length, 0)
scheduled.values().next().value()
await Promise.resolve()
assert.deepEqual(viewportCommits, [{ x: 50, y: 60, zoom: 0.6 }], '只持久化最后一个视口')
viewportCommitter.schedule({ x: 70, y: 80, zoom: 0.5 })
viewportCommitter.dispose()
assert.equal(scheduled.size, 0, 'board 切换或 unmount 必须清理 timer')
assert.deepEqual(viewportCommits, [
  { x: 50, y: 60, zoom: 0.6 },
  { x: 70, y: 80, zoom: 0.5 },
], 'dispose 必须 flush 最后一份视口，不能在切板时丢失用户位置')

const uploaded = await interactionsModule.uploadFileForWhiteboardCard(
  new File(['pdf'], 'paper.pdf', { type: 'application/pdf' }),
  'existing_upload',
  async () => ({ upload_id: 'upload_new', file_name: 'paper.pdf', content_type: 'application/pdf', file_kind: 'document' }),
  async response => ({ upload_id: response.upload_id }),
)
assert.deepEqual(uploaded, {
  uploadId: 'upload_new',
  metadata: { fileName: 'paper.pdf', contentType: 'application/pdf', fileKind: 'document' },
  error: null,
})
const failedUpload = await interactionsModule.uploadFileForWhiteboardCard(
  new File(['pdf'], 'paper.pdf', { type: 'application/pdf' }),
  'existing_upload',
  async () => { throw new Error('network down') },
  async () => { throw new Error('must not register') },
)
assert.equal(failedUpload.uploadId, 'existing_upload', '上传失败必须保留原 upload id 输入')
assert.equal(failedUpload.metadata, null)
assert.match(failedUpload.error, /network down/)

const uploadOrder = []
const failedRegistration = await interactionsModule.uploadFileForWhiteboardCard(
  new File(['pdf'], 'paper.pdf', { type: 'application/pdf' }),
  'existing_upload',
  async () => {
    uploadOrder.push('upload')
    return { upload_id: 'upload_unowned', file_name: 'paper.pdf', content_type: 'application/pdf', file_kind: 'document' }
  },
  async () => {
    uploadOrder.push('register')
    throw new Error('registration failed')
  },
)
assert.deepEqual(uploadOrder, ['upload', 'register'])
assert.equal(failedRegistration.uploadId, 'existing_upload')
assert.equal(failedRegistration.metadata, null)
assert.match(failedRegistration.error, /registration failed/)

let currentTaskId = 'conv_a'
let resolveContext
const contextPromise = new Promise(resolve => { resolveContext = resolve })
const acceptedRefs = []
const guardedContext = interactionsModule.resolveContextForCurrentTask({
  initiatingTaskId: 'conv_a',
  getCurrentTaskId: () => currentTaskId,
  request: () => contextPromise,
  accept: reference => acceptedRefs.push(reference),
})
currentTaskId = 'conv_b'
resolveContext({ id: 'ref_a' })
assert.deepEqual(await guardedContext, { status: 'stale' })
assert.deepEqual(acceptedRefs, [], '旧会话完成的 context ref 不得写入新会话')

const contextFailure = await interactionsModule.resolveContextForCurrentTask({
  initiatingTaskId: 'conv_b',
  getCurrentTaskId: () => currentTaskId,
  request: async () => { throw new Error('context failed') },
  accept: () => { throw new Error('must not accept') },
})
assert.equal(contextFailure.status, 'error')
assert.match(contextFailure.error, /context failed/)

await import('./whiteboardHomeIntegrationFixContracts.test.mjs')

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
