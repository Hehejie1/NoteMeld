import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const composer = await readFile(path.join(root, 'src/pages/HomePage/components/ChatComposer.tsx'), 'utf8')
const renderers = await readFile(path.join(root, 'src/pages/HomePage/messageRenderers.tsx'), 'utf8')
const layout = await readFile(path.join(root, 'src/layouts/AppLayout.tsx'), 'utf8')
const releaseWorkflow = await readFile(path.join(root, '../../.github/workflows/release.yml'), 'utf8')
const verifier = await readFile(path.join(root, '../../scripts/release/verify_first_batch_windows_local_agent.ps1'), 'utf8')

assert.match(layout, /VITE_NOTEMELD_BUILD_COMMIT/)
assert.match(layout, /notemeld-build-commit:/)
assert.match(releaseWorkflow, /VITE_NOTEMELD_BUILD_COMMIT:\s*\$\{\{ github\.sha \}\}/)
assert.match(releaseWorkflow, /VITE_NOTEMELD_BUILD_COMMIT must be the full release commit/)

for (const marker of [
  'notemeld-local-agent-input',
  'notemeld-local-agent-model:',
  'notemeld-local-agent-model-option:',
  'notemeld-local-agent-send-',
]) {
  assert.match(composer, new RegExp(marker), `Windows local Agent UI marker is missing: ${marker}`)
}
assert.match(renderers, /notemeld-local-agent-assistant:turn\.succeeded:1:/)
assert.match(composer, /terminalTypes\.length !== 1 \|\| terminalTypes\[0\] !== 'turn\.succeeded'/)

for (const requirement of [
  'WINDOWS-LOCAL-AGENT-RUNTIME',
  'Get-AuthenticodeSignature',
  '0x8664',
  'notemeld-local-agent-input',
  'notemeld-local-agent-model-option:',
  'notemeld-local-agent-assistant:turn.succeeded:1:',
  'runtime_evidence_sha256',
  'notemeld-build-commit:$ExpectedCommit',
  'ui_driven = $true',
]) {
  assert.match(verifier, new RegExp(requirement.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')), `Windows UI verifier is missing: ${requirement}`)
}
const output = verifier.split('$result = [ordered]@{', 2)[1]
assert.ok(output)
assert.doesNotMatch(output, /challenge\s*=/i)
assert.match(output, /challenge_sha256/)
assert.match(output, /release_checks = @\{ x_01 = "PASS"; x_02 = "PASS" \}/)
