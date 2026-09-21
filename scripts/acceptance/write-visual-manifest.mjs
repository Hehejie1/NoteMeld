#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

const args = {}
for (let i = 2; i < process.argv.length; i += 1) {
  const key = process.argv[i].replace(/^--/, '')
  args[key] = process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[++i] : true
}
for (const key of ['output', 'reference', 'rc', 'commit', 'case', 'page', 'route', 'platform', 'requirement-ids', 'feature-ids']) {
  if (!args[key]) throw new Error(`missing --${key}`)
}
const actual = await readFile(args.output)
const reference = await readFile(args.reference)
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex')
const manifest = {
  rc: args.rc,
  case: args.case,
  requirement_ids: String(args['requirement-ids']).split(',').filter(Boolean),
  feature_ids: String(args['feature-ids']).split(',').filter(Boolean),
  page: args.page,
  state: args.state || 'captured',
  route: args.route,
  viewport: args.viewport || 'unknown',
  theme: args.theme || 'unknown',
  fontScale: Number(args['font-scale'] || 1),
  reducedMotion: String(args['reduced-motion'] || 'false') === 'true',
  os: args.os || process.platform,
  device: args.device || 'unknown',
  platform: args.platform,
  artifact_hash: args['artifact-hash'] || 'unknown',
  image_digest: args['image-digest'] || 'unknown',
  commit: args.commit,
  reference_hash: hash(reference),
  actual_hash: hash(actual),
  diff_metric: null,
  missing_locator: [],
  reviewer: 'pending',
  timestamp: new Date().toISOString(),
  result: 'PENDING_REVIEW',
}
await writeFile(path.join(path.dirname(args.output), 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n')
console.log(JSON.stringify({ output: args.output, manifest: path.join(path.dirname(args.output), 'manifest.json'), result: manifest.result }))
