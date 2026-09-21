import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { execFile } from 'node:child_process'
import { createHash } from 'node:crypto'
import { promisify } from 'node:util'
import test from 'node:test'
import assert from 'node:assert/strict'

const execFileAsync = promisify(execFile)
const root = path.resolve(import.meta.dirname, '../../..')
const comparator = path.join(root, 'scripts/acceptance/compare-visuals.mjs')

const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64',
)

test('visual comparator validates evidence and writes diff/comparison manifests', async () => {
  const temp = await mkdtemp(path.join(tmpdir(), 'notemeld-visual-'))
  const evidence = path.join(temp, 'visual', 'web', 'cloud', 'workbench-wide')
  await mkdir(evidence, { recursive: true })
  await writeFile(path.join(evidence, 'reference.png'), ONE_PIXEL_PNG)
  await writeFile(path.join(evidence, 'actual.png'), ONE_PIXEL_PNG)
  await writeFile(path.join(evidence, 'manifest.json'), JSON.stringify({
    rc: 'v-test', requirement_ids: ['C01'], feature_ids: ['C01'], page: 'cloud', state: 'ready', route: '/cloud/workbench',
    viewport: '1440x960', theme: 'light', fontScale: 1, reducedMotion: false, os: 'test', device: 'test',
    artifact_hash: 'sha256:test', image_digest: 'sha256:test', commit: 'a'.repeat(40), reference_hash: createHash('sha256').update(ONE_PIXEL_PNG).digest('hex'),
    diff_metric: null, missing_locator: [], reviewer: 'pending', timestamp: new Date().toISOString(), result: 'PENDING_REVIEW',
  }))
  const matrix = path.join(temp, 'matrix.json')
  await writeFile(matrix, JSON.stringify({ cases: [{ id: 'C01', platform: 'web', page: 'cloud', case: 'workbench-wide' }] }))
  await execFileAsync(process.execPath, [comparator, '--matrix', matrix, '--rc', 'v-test', '--root', path.join(temp, 'visual')], { cwd: root })
  assert.equal((await readFile(path.join(evidence, 'diff.png')).then((value) => value.subarray(0, 8).toString('hex'))), '89504e470d0a1a0a')
  assert.match(await readFile(path.join(temp, 'visual', 'comparison.json'), 'utf8'), /"result": "PASS"/)
})

test('visual acceptance matrix and locator contract are present and versioned', async () => {
  const matrix = JSON.parse(await readFile(path.join(root, 'tests/visual/page-state-matrix.json'), 'utf8'))
  const locators = JSON.parse(await readFile(path.join(root, 'tests/visual/locator-contract.json'), 'utf8'))
  const mobileSurface = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileSurface.kt'), 'utf8')
  assert.equal(matrix.schema, 'notemeld.visual-matrix.v1')
  assert.ok(matrix.cases.length >= 5)
  assert.equal(locators.schema, 'notemeld.visual-locator-contract.v1')
  assert.ok(locators.required.web.includes('cloud-workbench'))
  assert.ok(locators.required.android.includes('notemeld-mobile-root'))
  assert.ok(locators.android_cases['mobile/home'].includes('notemeld-start-chat'))
  assert.ok(locators.android_cases['mobile/settings'].includes('notemeld-screen-settings'))
  for (const item of matrix.cases.filter((candidate) => candidate.platform === 'android')) {
    assert.ok(locators.android_cases[`${item.page}/${item.case}`], `missing Android locator mapping for ${item.id}`)
  }
  assert.match(mobileSurface, /testTagsAsResourceId\s*=\s*true/)
})

test('native screenshot capture entry points are fail-closed', async () => {
  const android = await readFile(path.join(root, 'scripts/acceptance/capture-android.sh'), 'utf8')
  const macos = await readFile(path.join(root, 'scripts/acceptance/capture-macos.sh'), 'utf8')
  for (const source of [android, macos]) {
    assert.match(source, /reference image is required/)
    assert.match(source, /write-visual-manifest\.mjs/)
  }
  assert.match(android, /adb -s .*reverse --list/)
  assert.match(android, /exec-out screencap -p/)
  assert.match(android, /uiautomator dump/)
  assert.match(android, /required-locators/)
  assert.match(android, /Android locator contract is required/)
  assert.match(macos, /screencapture -x/)
})
