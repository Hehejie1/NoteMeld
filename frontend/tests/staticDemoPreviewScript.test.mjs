import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'

const repositoryRoot = resolve(import.meta.dirname, '../..')
const scriptPath = resolve(repositoryRoot, 'scripts/preview_static_demo.sh')
const packageJsonPath = resolve(repositoryRoot, 'frontend/package.json')

const help = spawnSync('bash', [scriptPath, '--help'], { encoding: 'utf8' })
assert.equal(help.status, 0, help.stderr)
assert.match(help.stdout, /--port PORT/)
assert.match(help.stdout, /--no-open/)

const invalidPort = spawnSync('bash', [scriptPath, '--port', 'not-a-port', '--no-open'], { encoding: 'utf8' })
assert.notEqual(invalidPort.status, 0)
assert.match(`${invalidPort.stdout}${invalidPort.stderr}`, /端口/)

const source = readFileSync(scriptPath, 'utf8')
assert.match(source, /set -Eeuo pipefail/)
assert.match(source, /127\.0\.0\.1/)
assert.match(source, /build:demo/)
assert.doesNotMatch(source, /backend|uvicorn|python/i)

const packageJson = JSON.parse(readFileSync(packageJsonPath, 'utf8'))
assert.match(packageJson.scripts['build:demo'], /VITE_NOTEMELD_DEMO=true/)
assert.ok(packageJson.scripts['preview:demo'])

const viteConfig = readFileSync(resolve(repositoryRoot, 'frontend/vite.config.ts'), 'utf8')
assert.match(viteConfig, /mode\s*===\s*['"]demo['"]\s*\?\s*['"]\/['"]\s*:\s*['"]\.\/['"]/, 'demo build must use root-relative assets so deep routes can boot')
