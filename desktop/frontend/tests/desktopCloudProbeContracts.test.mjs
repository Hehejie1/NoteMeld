import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const source = fs.readFileSync(new URL('../src/services/desktopRuntime.ts', import.meta.url), 'utf8')

test('desktop runtime exposes the cloud readiness probe bridge', () => {
  assert.match(source, /export interface CloudProbeResult/)
  assert.match(source, /export async function probe_cloud\(baseUrl: string\)/)
  assert.match(source, /invoke<CloudProbeResult>\('probe_cloud', \{ baseUrl \}\)/)
  assert.match(source, /get_desktop_device_id/)
  assert.match(source, /invoke<string>\('desktop_device_id'\)/)
})
