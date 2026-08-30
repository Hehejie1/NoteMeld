import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const source = fs.readFileSync(new URL('../src/components/CloudSessionPanel/CloudSessionPanel.tsx', import.meta.url), 'utf8')

test('cloud session panel has loading, error, empty, and accessible event states', () => {
  assert.match(source, /aria-busy/)
  assert.match(source, /role="alert"/)
  assert.match(source, /No events yet/)
  assert.match(source, /role="log"/)
  assert.match(source, /Copy branch/)
})
