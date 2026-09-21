import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import path from 'node:path'

const root = path.resolve(new URL('..', import.meta.url).pathname)

test('Cloud Web owns explicit authenticated and access routes', async () => {
  const entry = await readFile(path.join(root, 'apps/cloud-web/src/main.tsx'), 'utf8')
  for (const route of ['/cloud/login', '/cloud/access-request', '/cloud/workbench', '/cloud/sessions/:sessionId?', '/cloud/people', '/cloud/devices', '/cloud/settings/*']) {
    assert.match(entry, new RegExp(`path=["']${route.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}["']`), route)
  }
  assert.match(entry, /CloudNotFound/)
  assert.doesNotMatch(entry, /docs\/new-product/)
})

test('CloudPage derives the view from the browser pathname and supports access requests', async () => {
  const page = await readFile(path.join(root, 'src/pages/CloudPage/index.tsx'), 'utf8')
  const deviceIdentity = await readFile(path.join(root, 'src/services/desktopDeviceIdentity.ts'), 'utf8')
  const login = await readFile(path.join(root, 'src/components/CloudLoginPanel/CloudLoginPanel.tsx'), 'utf8')
  assert.match(page, /useLocation\(\)/)
  assert.match(page, /access-request/)
  assert.match(page, /initialMode=\{loginMode\}/)
  assert.match(page, /deepSessionId/)
  assert.match(page, /safeCloudReturnTarget/)
  assert.match(page, /returnTo=/)
  assert.match(page, /navigate\(returnTarget/)
  assert.match(page, /services\/desktopDeviceIdentity/)
  assert.doesNotMatch(page, /services\/desktopRuntime/)
  assert.doesNotMatch(deviceIdentity, /demo|deterministic/i)
  assert.match(login, /initialMode\?: 'login' \| 'request'/)
  assert.doesNotMatch(page, /if \(view === 'people'\) return <main[^\n]*<CloudSurfaceHeading/)
  assert.doesNotMatch(page, /if \(view === 'devices'\) return <main[^\n]*<CloudSurfaceHeading/)
  assert.doesNotMatch(page, /cloud-workbench-heading/)
})
