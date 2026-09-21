import assert from 'node:assert/strict'

const { createDemoRuntime, DemoEndpointNotImplementedError } = await import('../src/demo/runtime.ts')
const { demoFixtureSeed } = await import('../src/demo/fixtures.ts')

const requiredStatuses = ['PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELED']
const serializedSeed = JSON.stringify(demoFixtureSeed)

for (const status of requiredStatuses) {
  assert.ok(serializedSeed.includes(`"${status}"`), `fixtures must cover ${status}`)
}
assert.ok(serializedSeed.includes('"partial"'), 'fixtures must cover Wiki partial')

for (const forbidden of [
  /sk-[a-z0-9_-]{12,}/i,
  /ghp_[a-z0-9]{12,}/i,
  /bearer\s+[a-z0-9._-]{12,}/i,
  /\/Users\//,
  /\/home\//,
  /[A-Z]:\\/,
]) {
  assert.doesNotMatch(serializedSeed, forbidden, `fixtures must not contain ${forbidden}`)
}

const runtime = createDemoRuntime()
const original = await runtime.request({ method: 'GET', path: '/conversations' })
assert.ok(Array.isArray(original) && original.length >= 5, 'demo must provide a useful conversation list')

await runtime.request({ method: 'DELETE', path: '/conversations/demo-note-success' })
const mutated = await runtime.request({ method: 'GET', path: '/conversations' })
assert.equal(mutated.some(item => item.id === 'demo-note-success'), false, 'supported mutations update demo memory')

runtime.reset()
const reset = await runtime.request({ method: 'GET', path: '/conversations' })
assert.equal(reset.some(item => item.id === 'demo-note-success'), true, 'reset restores deterministic fixtures')

await assert.rejects(
  runtime.request({ method: 'GET', path: '/not-registered' }),
  error => error instanceof DemoEndpointNotImplementedError && error.message.includes('GET /not-registered'),
  'unknown demo endpoints must fail closed with method and path',
)

const { startDemoNoteScenario } = await import('../src/demo/scenarios.ts').catch(() => ({}))
assert.equal(typeof startDemoNoteScenario, 'function', 'scenario engine must expose startDemoNoteScenario')

const scheduled = []
const observed = []
const scheduler = {
  schedule(callback) {
    scheduled.push(callback)
    return callback
  },
  cancel(handle) {
    const index = scheduled.indexOf(handle)
    if (index >= 0) scheduled.splice(index, 1)
  },
}
const scenario = startDemoNoteScenario('success', {
  scheduler,
  onStatus(status) { observed.push(status) },
})
while (scheduled.length) scheduled.shift()()
assert.deepEqual(
  observed,
  ['PENDING', 'PARSING', 'DOWNLOADING', 'TRANSCRIBING', 'SUMMARIZING', 'FORMATTING', 'SAVING', 'SUCCESS'],
  'success simulation must preserve production task order',
)

const disposedEvents = []
const disposedQueue = []
const disposable = startDemoNoteScenario('failed', {
  scheduler: { schedule(callback) { disposedQueue.push(callback); return callback }, cancel() {} },
  onStatus(status) { disposedEvents.push(status) },
})
disposable.dispose()
while (disposedQueue.length) disposedQueue.shift()()
assert.deepEqual(disposedEvents, ['PENDING'], 'dispose must prevent delayed status writes')

scenario.dispose()
