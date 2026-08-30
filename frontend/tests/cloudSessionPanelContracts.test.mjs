import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const panel = fs.readFileSync(new URL('../src/components/CloudSessionPanel/CloudSessionPanel.tsx', import.meta.url), 'utf8')
const list = fs.readFileSync(new URL('../src/components/CloudSessionList/CloudSessionList.tsx', import.meta.url), 'utf8')

test('cloud session panel has loading, error, empty, and accessible event states', () => {
  assert.match(panel, /aria-busy/); assert.match(panel, /role="alert"/); assert.match(panel, /No events yet/); assert.match(panel, /role="log"/); assert.match(panel, /Copy branch/)
})

test('cloud session list supports archive filtering and keyboard selection', () => {
  assert.match(list, /listSessions\(archived\)/); assert.match(list, /aria-current/); assert.match(list, /role="list"/); assert.match(list, /No archived sessions/)
})
