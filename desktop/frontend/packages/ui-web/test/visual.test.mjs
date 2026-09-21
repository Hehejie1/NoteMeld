import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import path from 'node:path'

const root = path.resolve(new URL('..', import.meta.url).pathname)

test('token surface includes theme and reduced-motion contracts', async () => {
  const tokens = await readFile(path.join(root, 'src/tokens.css'), 'utf8')
  for (const token of [
    '--nm-color-bg',
    '--nm-color-surface',
    '--nm-color-text',
    '--nm-color-accent',
    '--nm-space-4',
    '--nm-radius-md',
    '--nm-focus-ring',
    '--nm-motion-normal',
  ]) {
    assert.match(tokens, new RegExp(`--${token.slice(2)}\\s*:`))
  }
  assert.match(tokens, /prefers-reduced-motion/)
  assert.match(tokens, /theme-dark/)
})
