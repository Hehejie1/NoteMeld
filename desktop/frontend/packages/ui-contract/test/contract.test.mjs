import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

test('ui contract is runtime-independent and versioned', async () => {
  const manifest = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'))
  const source = await readFile(new URL('../src/index.ts', import.meta.url), 'utf8')
  assert.equal(manifest.name, '@notemeld/ui-contract')
  assert.equal(manifest.version, '0.1.0')
  assert.match(source, /uiContractVersion/)
  assert.match(source, /loading.*empty.*error.*offline/)
  assert.doesNotMatch(source, /react|window\.|document\./i)
})
