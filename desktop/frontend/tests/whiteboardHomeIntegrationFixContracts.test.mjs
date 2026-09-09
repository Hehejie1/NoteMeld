import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import path from 'node:path'
import ts from 'typescript'

const root = path.resolve(import.meta.dirname, '..')
const read = relativePath => readFile(path.join(root, relativePath), 'utf8')
const [home, panel, panelState, canvas, interactions, markdownViewer, taskStore] = await Promise.all([
  read('src/pages/HomePage/Home.tsx'),
  read('src/pages/HomePage/whiteboard/WhiteboardPanel.tsx'),
  read('src/pages/HomePage/whiteboard/whiteboardPanelState.ts'),
  read('src/pages/HomePage/whiteboard/WhiteboardCanvas.tsx'),
  read('src/pages/HomePage/whiteboard/whiteboardInteractions.ts'),
  read('src/pages/HomePage/components/MarkdownViewer.tsx'),
  read('src/store/taskStore/index.ts'),
])

const importTypescript = source => import(
  `data:text/javascript;base64,${Buffer.from(
    ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
    }).outputText,
  ).toString('base64')}`
)

const panelStateModule = await importTypescript(panelState)
const interactionsModule = await importTypescript(interactions)

test('legacy seed waits for backend readiness before claim and request', async () => {
  assert.equal(typeof panelStateModule.runLegacyWhiteboardSeed, 'function')
  let claims = 0
  let requests = 0
  const registry = {
    claim: () => {
      claims += 1
      return true
    },
  }
  const request = async () => {
    requests += 1
    return { id: 'wb_seeded' }
  }

  const waiting = await panelStateModule.runLegacyWhiteboardSeed({
    backendReady: false,
    conversationId: 'conv_a',
    messageId: 'message_a',
    canvasId: 'canvas_a',
    registry,
    request,
  })
  assert.deepEqual(waiting, { status: 'waiting' })
  assert.equal(claims, 0)
  assert.equal(requests, 0)

  const seeded = await panelStateModule.runLegacyWhiteboardSeed({
    backendReady: true,
    conversationId: 'conv_a',
    messageId: 'message_a',
    canvasId: 'canvas_a',
    registry,
    request,
  })
  assert.deepEqual(seeded, { status: 'seeded', value: { id: 'wb_seeded' } })
  assert.equal(claims, 1)
  assert.equal(requests, 1)
  assert.equal(typeof panelStateModule.resolveSeedError, 'function')
  assert.equal(panelStateModule.resolveSeedError('seed_a', { key: 'seed_a', message: 'failed A' }), 'failed A')
  assert.equal(panelStateModule.resolveSeedError('seed_b', { key: 'seed_a', message: 'failed A' }), '')
  assert.match(home, /useBackendInitContext/)
  assert.match(home, /runLegacyWhiteboardSeed/)
  assert.match(panel, /failureKind/)
  assert.match(panel, /checkNow/)
})

test('StrictMode seed setup cleanup setup keeps the only in-flight result', async () => {
  const registry = panelStateModule.createSeedAttemptRegistry()
  const requestKey = '["conv_a","message_a","canvas_a"]'
  let activeKey = requestKey
  let requestCalls = 0
  let resolveRequest
  const request = new Promise(resolve => { resolveRequest = resolve })
  const applied = []
  const setup = () => panelStateModule.runLegacyWhiteboardSeed({
    backendReady: true,
    conversationId: 'conv_a',
    messageId: 'message_a',
    canvasId: 'canvas_a',
    registry,
    request: () => {
      requestCalls += 1
      return request
    },
  }).then(result => {
    if (activeKey === requestKey && result.status === 'seeded') applied.push(result.value.id)
  })

  const firstSetup = setup()
  const cleanup = () => undefined
  cleanup()
  const secondSetup = setup()
  assert.equal(requestCalls, 1)
  resolveRequest({ id: 'wb_seeded' })
  await Promise.all([firstSetup, secondSetup])
  assert.deepEqual(applied, ['wb_seeded'])

  activeKey = '["conv_b","message_b","canvas_b"]'
  registry.release('conv_a', 'message_a')
  let resolveStale
  const staleRequest = new Promise(resolve => { resolveStale = resolve })
  const stale = panelStateModule.runLegacyWhiteboardSeed({
    backendReady: true,
    conversationId: 'conv_a',
    messageId: 'message_a',
    canvasId: 'canvas_a',
    registry,
    request: () => staleRequest,
  }).then(result => {
    if (activeKey === requestKey && result.status === 'seeded') applied.push(result.value.id)
  })
  resolveStale({ id: 'wb_stale' })
  await stale
  assert.deepEqual(applied, ['wb_seeded'])

  const seedEffectStart = home.indexOf('runLegacyWhiteboardSeed({')
  const seedEffectEnd = home.indexOf('const retryWhiteboardSeed', seedEffectStart)
  assert.notEqual(seedEffectStart, -1)
  assert.notEqual(seedEffectEnd, -1)
  const seedEffect = home.slice(seedEffectStart, seedEffectEnd)
  assert.doesNotMatch(seedEffect, /let active = true/)
  assert.match(seedEffect, /activeSeedKeyRef\.current !== seedRequestKey/)
})

test('Note view resolves only the current board linked document', () => {
  assert.equal(typeof panelStateModule.resolveWhiteboardNoteDocument, 'function')
  const documents = [
    { taskId: 'note_a', title: 'A', content: 'content A', status: 'SUCCESS' },
    { taskId: 'note_b', title: 'B', content: 'content B', status: 'SUCCESS' },
  ]
  const rootNote = panelStateModule.resolveWhiteboardNoteDocument(
    { note_task_id: 'note_a', published_revision: 2 },
    documents,
  )
  assert.equal(rootNote.taskId, 'note_a')
  assert.equal(rootNote.content, 'content A')
  assert.equal(rootNote.status, 'success')

  const childNote = panelStateModule.resolveWhiteboardNoteDocument(
    { note_task_id: 'note_b', published_revision: 1 },
    documents,
  )
  assert.equal(childNote.taskId, 'note_b')
  assert.equal(childNote.content, 'content B')

  assert.deepEqual(
    panelStateModule.resolveWhiteboardNoteDocument(null, documents),
    { taskId: '', content: '', status: 'idle', document: null },
  )
  assert.match(panel, /resolveWhiteboardNoteDocument/)
  assert.match(markdownViewer, /documentTaskId/)
})

test('panel snapshot selection follows the live view and confirms published override', () => {
  assert.equal(typeof panelStateModule.selectWhiteboardPanelSnapshot, 'function')
  assert.equal(typeof panelStateModule.isPublishedNoteOverrideConfirmed, 'function')
  const staleCanvas = { id: 'wb_a', revision: 4, note_link: null, source: 'canvas' }
  const freshNote = {
    id: 'wb_a',
    revision: 4,
    note_link: { note_task_id: 'note_a', published_revision: 4 },
    source: 'note',
  }
  const override = panelStateModule.createPublishedNoteOverride('conv_a:wb_a', {
    note_task_id: 'note_a',
    published_revision: 4,
  })

  const selectedNote = panelStateModule.selectWhiteboardPanelSnapshot(
    'note',
    freshNote,
    staleCanvas,
  )
  assert.equal(selectedNote.source, 'note')
  assert.equal(panelStateModule.isPublishedNoteOverrideConfirmed(selectedNote, override), true)
  const withoutOverride = panelStateModule.resolvePublishedWhiteboardSnapshot(
    selectedNote,
    'conv_a:wb_a',
    null,
  )
  assert.equal(panelStateModule.getWhiteboardPublishPresentation({
    revision: withoutOverride.revision,
    noteLink: withoutOverride.note_link,
  }).state, 'synced')

  const selectedWhiteboard = panelStateModule.selectWhiteboardPanelSnapshot(
    'whiteboard',
    freshNote,
    staleCanvas,
  )
  assert.equal(selectedWhiteboard.source, 'canvas')
  assert.match(panel, /selectWhiteboardPanelSnapshot/)
  assert.match(panel, /isPublishedNoteOverrideConfirmed/)
})

test('panel snapshot selection preserves the newest revision before merging note links', () => {
  const olderNote = {
    id: 'wb_a',
    revision: 4,
    note_link: { note_task_id: 'note_a', published_revision: 4 },
    source: 'note',
  }
  const newerCanvas = {
    id: 'wb_a',
    revision: 5,
    note_link: { note_task_id: 'note_a', published_revision: 4 },
    source: 'canvas',
  }

  const selectedNewer = panelStateModule.selectWhiteboardPanelSnapshot(
    'note',
    olderNote,
    newerCanvas,
  )
  assert.equal(selectedNewer.source, 'canvas')
  assert.equal(selectedNewer.revision, 5)
  assert.equal(panelStateModule.getWhiteboardPublishPresentation({
    revision: selectedNewer.revision,
    noteLink: selectedNewer.note_link,
  }).state, 'stale')

  const sameRevisionCanvas = {
    ...newerCanvas,
    revision: 4,
    note_link: null,
  }
  const selectedSameRevisionNote = panelStateModule.selectWhiteboardPanelSnapshot(
    'note',
    olderNote,
    sameRevisionCanvas,
  )
  assert.equal(selectedSameRevisionNote.source, 'note')
  assert.deepEqual(selectedSameRevisionNote.note_link, olderNote.note_link)

  const selectedSameRevisionCanvas = panelStateModule.selectWhiteboardPanelSnapshot(
    'whiteboard',
    olderNote,
    sameRevisionCanvas,
  )
  assert.equal(selectedSameRevisionCanvas.source, 'canvas')
  assert.deepEqual(selectedSameRevisionCanvas.note_link, olderNote.note_link)

  const lowerRevisionLinkMustNotLeak = panelStateModule.selectWhiteboardPanelSnapshot(
    'note',
    olderNote,
    { ...newerCanvas, note_link: null },
  )
  assert.equal(lowerRevisionLinkMustNotLeak.revision, 5)
  assert.equal(lowerRevisionLinkMustNotLeak.note_link, null)
})

test('publish completion cannot reactivate an old conversation', async () => {
  assert.equal(typeof panelStateModule.completePublishedConversationRefresh, 'function')
  let currentConversationId = 'conv_a'
  let rightView = 'whiteboard'
  let selectedNoteId = ''
  let resolveRefresh
  const refreshResult = new Promise(resolve => { resolveRefresh = resolve })
  let tasks = [
    { id: 'conv_a', documents: [] },
    { id: 'conv_b', documents: [{ taskId: 'note_b', content: 'keep B' }] },
  ]
  const completion = panelStateModule.completePublishedConversationRefresh({
    conversationId: 'conv_a',
    getCurrentConversationId: () => currentConversationId,
    refresh: async () => {
      const refreshed = await refreshResult
      tasks = tasks.map(task => task.id === refreshed.id ? refreshed : task)
      return refreshed
    },
    apply: () => {
      selectedNoteId = 'note_a'
      rightView = 'note'
    },
  })
  currentConversationId = 'conv_b'
  resolveRefresh({ id: 'conv_a', documents: [{ taskId: 'note_a', content: 'new A' }] })

  assert.deepEqual(await completion, { status: 'stale' })
  assert.equal(currentConversationId, 'conv_b')
  assert.equal(rightView, 'whiteboard')
  assert.equal(selectedNoteId, '')
  assert.deepEqual(tasks.find(task => task.id === 'conv_b').documents, [{ taskId: 'note_b', content: 'keep B' }])
  assert.match(home, /refreshConversation/)
  assert.doesNotMatch(home, /handleWhiteboardPublished[^]*?await loadConversation/)

  const refreshStart = taskStore.indexOf('refreshConversation: async')
  const refreshEnd = taskStore.indexOf('retryChat: async', refreshStart)
  assert.notEqual(refreshStart, -1)
  assert.notEqual(refreshEnd, -1)
  assert.doesNotMatch(taskStore.slice(refreshStart, refreshEnd), /currentTaskId\s*:/)
})

test('switching root and child boards remounts viewport ownership', () => {
  assert.equal(typeof interactionsModule.createWhiteboardCanvasKey, 'function')
  const rootKey = interactionsModule.createWhiteboardCanvasKey('conv_a', 'wb_root')
  const childKey = interactionsModule.createWhiteboardCanvasKey('conv_a', 'wb_child')
  assert.notEqual(rootKey, childKey)
  assert.match(canvas, /ReactFlowProvider key=\{createWhiteboardCanvasKey/)
  assert.doesNotMatch(canvas, /fitView=\{controller\.snapshot\.cards\.length > 0\}/)

  const commits = []
  const rootCommitter = interactionsModule.createViewportCommitter(
    viewport => commits.push({ boardId: 'wb_root', viewport }),
    500,
    { setTimeout: () => 1, clearTimeout: () => undefined },
  )
  rootCommitter.schedule({ x: 10, y: 20, zoom: 0.8 })
  rootCommitter.dispose()
  const childCommitter = interactionsModule.createViewportCommitter(
    viewport => commits.push({ boardId: 'wb_child', viewport }),
    500,
    { setTimeout: () => 2, clearTimeout: () => undefined },
  )
  childCommitter.schedule({ x: 30, y: 40, zoom: 1.2 })
  childCommitter.dispose()
  assert.deepEqual(commits.map(item => item.boardId), ['wb_root', 'wb_child'])
})

test('durable publish survives Note refresh rejection and retries delivery without republishing', async () => {
  assert.equal(typeof panelStateModule.runDurableWhiteboardPublish, 'function')
  assert.equal(typeof panelStateModule.deliverPublishedNoteRefresh, 'function')
  let publishCalls = 0
  let refreshCalls = 0
  const publishResult = { whiteboard_id: 'wb_a', note_task_id: 'note_a', published_revision: 4 }
  const first = await panelStateModule.runDurableWhiteboardPublish({
    publish: async () => {
      publishCalls += 1
      return publishResult
    },
    deliver: async () => {
      refreshCalls += 1
      throw new Error('conversation refresh failed')
    },
  })
  assert.equal(first.status, 'published')
  assert.equal(first.result, publishResult)
  assert.deepEqual(first.noteRefresh, {
    status: 'failed',
    message: '发布成功，笔记内容刷新失败：conversation refresh failed',
  })
  assert.equal(publishCalls, 1)

  const retried = await panelStateModule.deliverPublishedNoteRefresh(publishResult, async () => {
    refreshCalls += 1
    return { status: 'refreshed' }
  })
  assert.deepEqual(retried, { status: 'refreshed' })
  assert.equal(publishCalls, 1, '刷新重试不得再次发布 Note')
  assert.equal(refreshCalls, 2)
  assert.match(panel, /runDurableWhiteboardPublish/)
  assert.match(panel, /deliverPublishedNoteRefresh/)
  assert.match(panel, /发布成功，笔记内容刷新失败/)
  assert.match(panel, /重试刷新/)
})

test('published Note link survives board reload failure and reload retry never republishes', async () => {
  assert.equal(typeof panelStateModule.createPublishedNoteOverride, 'function')
  assert.equal(typeof panelStateModule.resolvePublishedWhiteboardSnapshot, 'function')
  assert.equal(typeof panelStateModule.runPublishedWhiteboardReload, 'function')
  let publishCalls = 0
  let reloadCalls = 0
  const result = await panelStateModule.runDurableWhiteboardPublish({
    publish: async () => {
      publishCalls += 1
      return { whiteboard_id: 'wb_a', note_task_id: 'note_a', published_revision: 4 }
    },
  })
  const snapshot = {
    id: 'wb_a',
    revision: 4,
    note_link: null,
  }
  const override = panelStateModule.createPublishedNoteOverride('conv_a:wb_a', result.result)
  const effective = panelStateModule.resolvePublishedWhiteboardSnapshot(
    snapshot,
    'conv_a:wb_a',
    override,
  )
  assert.deepEqual(effective.note_link, {
    note_task_id: 'note_a',
    published_revision: 4,
  })
  assert.equal(panelStateModule.getWhiteboardPublishPresentation({
    revision: effective.revision,
    noteLink: effective.note_link,
  }).state, 'synced')

  const failed = await panelStateModule.runPublishedWhiteboardReload(async () => {
    reloadCalls += 1
    throw new Error('reload failed')
  })
  assert.deepEqual(failed, {
    status: 'failed',
    message: '笔记已发布，白板状态刷新失败：reload failed',
  })
  const retried = await panelStateModule.runPublishedWhiteboardReload(async () => {
    reloadCalls += 1
  })
  assert.deepEqual(retried, { status: 'reloaded' })
  assert.equal(publishCalls, 1)
  assert.equal(reloadCalls, 2)
  assert.match(panel, /createPublishedNoteOverride/)
  assert.match(panel, /resolvePublishedWhiteboardSnapshot/)
  assert.match(panel, /const snapshot = useMemo\(\(\) => resolvePublishedWhiteboardSnapshot/)
  assert.match(panel, /publishBlocked = Boolean\([^]*?currentPublishedNoteOverride/)
  assert.match(panel, /currentPublishedReloadFailure/)
  assert.match(panel, /笔记已发布，白板状态刷新失败/)
  assert.match(panel, /重试白板刷新/)
})

test('publish failure cannot leak into a newly selected child board', () => {
  assert.equal(typeof panelStateModule.isWhiteboardTargetCurrent, 'function')
  let currentTargetKey = 'conv_a:wb_root'
  const capturedTargetKey = currentTargetKey
  currentTargetKey = 'conv_a:wb_child'
  assert.equal(panelStateModule.isWhiteboardTargetCurrent(
    capturedTargetKey,
    () => currentTargetKey,
  ), false)
  assert.equal(panelStateModule.isWhiteboardTargetCurrent(
    currentTargetKey,
    () => currentTargetKey,
  ), true)

  const publishStart = panel.indexOf('const publish = async')
  const publishEnd = panel.indexOf('\n  if (!backendReady)', publishStart)
  assert.notEqual(publishStart, -1)
  assert.notEqual(publishEnd, -1)
  const publishSection = panel.slice(publishStart, publishEnd)
  assert.match(publishSection, /const publishTargetKey = snapshotTargetKey/)
  assert.match(publishSection, /catch \(error\)[^]*?isWhiteboardTargetCurrent\(\s*publishTargetKey/)
  assert.doesNotMatch(publishSection, /catch \(error\) \{\s*const candidate/)
})

test('Note lifecycle reload ignores stale canvas controller and guards direct fetch', async () => {
  assert.equal(typeof panelStateModule.reloadWhiteboardForPanelView, 'function')
  let view = 'whiteboard'
  let currentTargetKey = 'conv_a:wb_a'
  let canvasReloads = 0
  let directLoads = 0
  const accepted = []
  const canvasReload = async () => { canvasReloads += 1 }
  const directLoad = async () => {
    directLoads += 1
    return { id: 'wb_a', note_link: { note_task_id: 'note_a', published_revision: 4 } }
  }

  view = 'note'
  const noteReload = await panelStateModule.reloadWhiteboardForPanelView({
    view,
    canvasReload,
    directLoad,
    targetKey: 'conv_a:wb_a',
    getCurrentTargetKey: () => currentTargetKey,
    accept: snapshot => accepted.push(snapshot.id),
  })
  assert.deepEqual(noteReload, { status: 'direct' })
  assert.equal(canvasReloads, 0, 'Note视图不得调用已卸载canvas controller')
  assert.equal(directLoads, 1)
  assert.deepEqual(accepted, ['wb_a'])

  let resolveStale
  const staleDirect = new Promise(resolve => { resolveStale = resolve })
  const staleReload = panelStateModule.reloadWhiteboardForPanelView({
    view: 'note',
    canvasReload,
    directLoad: () => staleDirect,
    targetKey: 'conv_a:wb_a',
    getCurrentTargetKey: () => currentTargetKey,
    accept: snapshot => accepted.push(snapshot.id),
  })
  currentTargetKey = 'conv_b:wb_b'
  resolveStale({ id: 'wb_stale', note_link: null })
  assert.deepEqual(await staleReload, { status: 'stale' })
  assert.deepEqual(accepted, ['wb_a'])

  assert.match(panel, /reloadWhiteboardForPanelView/)
  assert.match(panel, /view === 'whiteboard' && canvasStatus/)
  const reloadStart = panel.indexOf('const reloadPublishedWhiteboard')
  const reloadEnd = panel.indexOf('\n  const publish', reloadStart)
  const reloadSection = panel.slice(reloadStart, reloadEnd)
  assert.match(reloadSection, /const reloadView = currentViewRef\.current/)
  assert.match(reloadSection, /getWhiteboard\(conversationId, currentBoard\.id\)/)
  assert.match(reloadSection, /currentSnapshotTargetKeyRef\.current/)
})

test('Note-only snapshot load is single-flight, race guarded, and recoverable', async () => {
  assert.equal(typeof panelStateModule.createWhiteboardSnapshotLoader, 'function')
  assert.equal(typeof panelStateModule.loadWhiteboardSnapshotForTarget, 'function')
  const loader = panelStateModule.createWhiteboardSnapshotLoader()
  let requestCalls = 0
  let currentTargetKey = 'conv_a:wb_root'
  let resolveRoot
  const rootRequest = new Promise(resolve => { resolveRoot = resolve })
  const accepted = []
  const loadRoot = () => panelStateModule.loadWhiteboardSnapshotForTarget({
    targetKey: 'conv_a:wb_root',
    getCurrentTargetKey: () => currentTargetKey,
    load: () => loader.load('conv_a:wb_root', () => {
      requestCalls += 1
      return rootRequest
    }),
    accept: snapshot => accepted.push(snapshot.id),
  })
  const rootA = loadRoot()
  const rootB = loadRoot()
  assert.equal(requestCalls, 1, 'StrictMode/重复effect不得发起重复snapshot请求')
  currentTargetKey = 'conv_a:wb_child'
  resolveRoot({ id: 'wb_root', note_link: null })
  assert.deepEqual(await rootA, { status: 'stale' })
  assert.deepEqual(await rootB, { status: 'stale' })
  assert.deepEqual(accepted, [])

  const failed = await panelStateModule.loadWhiteboardSnapshotForTarget({
    targetKey: currentTargetKey,
    getCurrentTargetKey: () => currentTargetKey,
    load: () => loader.load(currentTargetKey, async () => {
      requestCalls += 1
      throw new Error('snapshot network failed')
    }),
    accept: () => assert.fail('failed snapshot must not be accepted'),
  })
  assert.deepEqual(failed, { status: 'error', message: 'snapshot network failed' })

  const recovered = await panelStateModule.loadWhiteboardSnapshotForTarget({
    targetKey: currentTargetKey,
    getCurrentTargetKey: () => currentTargetKey,
    load: () => loader.load(currentTargetKey, async () => {
      requestCalls += 1
      return { id: 'wb_child', note_link: { note_task_id: 'note_child' } }
    }),
    accept: snapshot => accepted.push(snapshot.id),
  })
  assert.deepEqual(recovered, { status: 'loaded' })
  assert.deepEqual(accepted, ['wb_child'])
  assert.equal(requestCalls, 3)
  assert.match(panel, /createWhiteboardSnapshotLoader/)
  assert.match(panel, /loadWhiteboardSnapshotForTarget/)
  assert.match(panel, /白板发布状态加载失败/)
  assert.match(panel, /重试加载/)
  assert.match(panel, /查看原研究图/)
  const workspaceStart = panel.indexOf('<div className="relative min-h-0 flex-1 overflow-hidden">')
  assert.notEqual(workspaceStart, -1)
  const workspace = panel.slice(workspaceStart)
  assert.ok(
    workspace.indexOf('showLegacyFallback && legacyCanvasId ?') < workspace.indexOf("view === 'note' ?"),
    '移动端受控 Note 视图也必须能优先进入 legacy fallback',
  )
  assert.match(panel, /const retryLegacyFallback/)
  const retryStart = panel.indexOf('const retryLegacyFallback')
  const retryEnd = panel.indexOf('\n  const ', retryStart + 10)
  assert.match(panel.slice(retryStart, retryEnd), /view === 'whiteboard' && canvasStatus/)
  assert.match(panel.slice(retryStart, retryEnd), /retryNoteSnapshotLoad/)
  assert.match(panel, /onRetryConversion=\{retryLegacyFallback\}/)
})
