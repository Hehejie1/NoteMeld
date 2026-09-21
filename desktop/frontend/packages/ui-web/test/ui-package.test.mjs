import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import { test } from 'node:test'
import path from 'node:path'

const root = path.resolve(new URL('..', import.meta.url).pathname)

test('ui-web exposes canonical source and package-local primitive tests', async () => {
  const manifest = JSON.parse(await readFile(path.join(root, 'package.json'), 'utf8'))
  const sourceFiles = await readdir(path.join(root, 'src'))
  assert.equal(manifest.name, '@notemeld/ui-web')
  assert.equal(manifest.private, false)
  assert.equal(manifest.version, '0.1.0')
  assert.equal(manifest.publishConfig.access, 'public')
  assert.equal(manifest.scripts.build, 'tsc -p tsconfig.build.json && node scripts/copy-assets.mjs')
  assert.equal(manifest.scripts.lint, 'tsc -p tsconfig.json --noEmit')
  assert.equal(manifest.scripts['test:a11y'], 'node --test test/a11y.test.mjs')
  assert.equal(manifest.scripts['test:visual'], 'node --test test/visual.test.mjs')
  assert.ok(sourceFiles.includes('index.ts'))
  assert.ok(sourceFiles.includes('tokens.css'))
  assert.ok(sourceFiles.includes('catalog.ts'))
  for (const exportPath of ['./button', './feedback', './progress', './skeleton', './tokens.css', './theme-provider', './icon-button', './table', './list', './navigation', './popover', './sheet', './drawer']) {
    assert.ok(manifest.exports[exportPath], `missing export ${exportPath}`)
  }
  assert.equal(manifest.exports['./catalog'], './src/catalog.ts')
})
