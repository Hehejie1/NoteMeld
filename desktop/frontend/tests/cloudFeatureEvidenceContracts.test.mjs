import { readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import assert from 'node:assert/strict'

const root = path.resolve(import.meta.dirname, '../../..')
const registryPath = path.join(root, 'docs/new-product/config/feature-registry.json')
const reportPath = path.join(root, 'docs/superpowers/tests/2026-09-18-cloud-acceptance-report.md')
const evidenceRoot = '/tmp/notemeld-acceptance/cloud-c01-c06/visual-matrix'

test('Cloud acceptance evidence covers every C01-C06 feature registry ID', async () => {
  const registry = JSON.parse(await readFile(registryPath, 'utf8'))
  const report = await readFile(reportPath, 'utf8')
  const featureIds = Object.keys(registry.features).filter(id => /^C0[1-6]\./.test(id))
  assert.ok(featureIds.length > 0)
  for (const id of featureIds) assert.match(report, new RegExp(`\\| ${id.replace('.', '\\.')}`), `missing report row for ${id}`)

  const [actual, reference, comparison] = await Promise.all([
    readFile(path.join(evidenceRoot, 'manifest.json'), 'utf8').then(JSON.parse),
    readFile(path.join(evidenceRoot, 'reference/manifest.json'), 'utf8').then(JSON.parse),
    readFile(path.join(evidenceRoot, 'comparison/manifest.json'), 'utf8').then(JSON.parse),
  ])
  assert.equal(actual.cases.length, 84)
  assert.equal(reference.cases.length, 84)
  assert.equal(comparison.cases.length, 84)
  for (const id of ['C01', 'C02', 'C03', 'C04', 'C05', 'C06']) {
    assert.ok(actual.cases.some(item => item.id.startsWith(`${id}-`)), `missing actual screenshots for ${id}`)
    assert.ok(reference.cases.some(item => item.id.startsWith(`${id}-`)), `missing reference screenshots for ${id}`)
    assert.ok(comparison.cases.some(item => item.id.startsWith(`${id}-`)), `missing diff screenshots for ${id}`)
  }
  assert.equal(comparison.actual_commit, actual.commit)
  assert.equal(comparison.actual_image_digest, actual.image_digest)
  assert.equal(comparison.comparison_status, 'PENDING_REVIEW')
})
