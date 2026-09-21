#!/usr/bin/env node

import { createHash } from 'node:crypto'
import { deflateSync, inflateSync } from 'node:zlib'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'

const REQUIRED_MANIFEST_FIELDS = [
  'requirement_ids', 'feature_ids', 'page', 'state', 'route', 'viewport',
  'theme', 'fontScale', 'reducedMotion', 'os', 'device', 'artifact_hash',
  'image_digest', 'commit', 'reference_hash', 'diff_metric', 'missing_locator',
  'reviewer', 'timestamp', 'result',
]

function fail(message) {
  throw new Error(message)
}

function parseArgs(argv) {
  const args = {}
  for (let i = 0; i < argv.length; i += 1) {
    if (!argv[i].startsWith('--')) continue
    const key = argv[i].slice(2)
    args[key] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true
  }
  if (!args.matrix || !args.rc) fail('usage: compare-visuals.mjs --matrix <matrix.json> --rc <rc> [--root <evidence-root>]')
  return args
}

function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex')
}

function readPng(bytes, label) {
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])
  if (!bytes.subarray(0, 8).equals(signature)) fail(`${label}: not a PNG`) 
  let offset = 8
  let width
  let height
  let bitDepth
  let colorType
  let interlace
  const idat = []
  while (offset < bytes.length) {
    const length = bytes.readUInt32BE(offset)
    const type = bytes.toString('ascii', offset + 4, offset + 8)
    const data = bytes.subarray(offset + 8, offset + 8 + length)
    offset += 12 + length
    if (type === 'IHDR') {
      width = data.readUInt32BE(0); height = data.readUInt32BE(4)
      bitDepth = data[8]; colorType = data[9]; interlace = data[12]
    } else if (type === 'IDAT') idat.push(data)
    else if (type === 'IEND') break
  }
  if (!width || !height || bitDepth !== 8 || ![0, 2, 4, 6].includes(colorType) || interlace !== 0) {
    fail(`${label}: only non-interlaced 8-bit grayscale/RGB/RGBA PNGs are supported`)
  }
  const channels = ({ 0: 1, 2: 3, 4: 2, 6: 4 })[colorType]
  const stride = width * channels
  const raw = inflateSync(Buffer.concat(idat))
  const pixels = Buffer.alloc(width * height * 4)
  let source = 0
  let previous = Buffer.alloc(stride)
  const paeth = (a, b, c) => {
    const p = a + b - c
    const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c)
    return pa <= pb && pa <= pc ? a : pb <= pc ? b : c
  }
  for (let y = 0; y < height; y += 1) {
    const filter = raw[source++]
    const row = Buffer.from(raw.subarray(source, source + stride)); source += stride
    for (let x = 0; x < stride; x += 1) {
      const left = x >= channels ? row[x - channels] : 0
      const up = previous[x] ?? 0
      const upLeft = x >= channels ? previous[x - channels] ?? 0 : 0
      if (filter === 1) row[x] = (row[x] + left) & 255
      else if (filter === 2) row[x] = (row[x] + up) & 255
      else if (filter === 3) row[x] = (row[x] + Math.floor((left + up) / 2)) & 255
      else if (filter === 4) row[x] = (row[x] + paeth(left, up, upLeft)) & 255
      else if (filter !== 0) fail(`${label}: unsupported PNG filter ${filter}`)
    }
    for (let x = 0; x < width; x += 1) {
      const sourceIndex = x * channels
      const targetIndex = (y * width + x) * 4
      const gray = row[sourceIndex]
      pixels[targetIndex] = colorType === 0 || colorType === 4 ? gray : row[sourceIndex]
      pixels[targetIndex + 1] = colorType === 0 || colorType === 4 ? gray : row[sourceIndex + 1]
      pixels[targetIndex + 2] = colorType === 0 || colorType === 4 ? gray : row[sourceIndex + 2]
      pixels[targetIndex + 3] = colorType === 4 || colorType === 6 ? row[sourceIndex + channels - 1] : 255
    }
    previous = row
  }
  return { width, height, pixels }
}

function crc32(bytes) {
  let crc = 0xffffffff
  for (const byte of bytes) {
    crc ^= byte
    for (let i = 0; i < 8; i += 1) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1))
  }
  return (crc ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const name = Buffer.from(type)
  const body = Buffer.concat([name, data])
  const result = Buffer.alloc(12 + data.length)
  result.writeUInt32BE(data.length, 0)
  body.copy(result, 4)
  result.writeUInt32BE(crc32(body), 8 + data.length)
  return result
}

function encodePng(width, height, pixels) {
  const rows = Buffer.alloc(height * (1 + width * 4))
  for (let y = 0; y < height; y += 1) {
    rows[y * (1 + width * 4)] = 0
    pixels.copy(rows, y * (1 + width * 4) + 1, y * width * 4, (y + 1) * width * 4)
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(width, 0); ihdr.writeUInt32BE(height, 4)
  ihdr[8] = 8; ihdr[9] = 6
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', ihdr), chunk('IDAT', deflateSync(rows)), chunk('IEND', Buffer.alloc(0)),
  ])
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const matrixPath = path.resolve(args.matrix)
  const matrix = JSON.parse(await readFile(matrixPath, 'utf8'))
  if (!Array.isArray(matrix.cases) || matrix.cases.length === 0) fail('visual matrix must contain cases')
  const root = path.resolve(args.root || path.join(path.dirname(matrixPath), '..', '..', 'artifacts', 'acceptance', args.rc, 'visual'))
  const results = []
  for (const item of matrix.cases) {
    if (!item.id || !item.platform || !item.page || !item.case) fail('each visual case needs id/platform/page/case')
    const dir = path.join(root, item.platform, item.page, item.case)
    const [referenceBytes, actualBytes, manifestBytes] = await Promise.all([
      readFile(path.join(dir, 'reference.png')),
      readFile(path.join(dir, 'actual.png')),
      readFile(path.join(dir, 'manifest.json')),
    ])
    const reference = readPng(referenceBytes, `${item.id}/reference.png`)
    const actual = readPng(actualBytes, `${item.id}/actual.png`)
    if (reference.width !== actual.width || reference.height !== actual.height) fail(`${item.id}: reference/actual dimensions differ`)
    const manifest = JSON.parse(manifestBytes)
    for (const field of REQUIRED_MANIFEST_FIELDS) if (!(field in manifest)) fail(`${item.id}: manifest missing ${field}`)
    if (!['PENDING_REVIEW', 'PASS'].includes(manifest.result)) {
      fail(`${item.id}: manifest result must be PENDING_REVIEW or PASS before comparison`)
    }
    if (manifest.reference_hash !== sha256(referenceBytes)) fail(`${item.id}: reference hash mismatch`)
    if (manifest.rc !== args.rc && manifest.rc_id !== args.rc) fail(`${item.id}: manifest is not bound to RC ${args.rc}`)
    const diff = Buffer.alloc(actual.pixels.length)
    let changed = 0
    for (let i = 0; i < actual.pixels.length; i += 4) {
      const different = actual.pixels[i] !== reference.pixels[i] || actual.pixels[i + 1] !== reference.pixels[i + 1] || actual.pixels[i + 2] !== reference.pixels[i + 2] || actual.pixels[i + 3] !== reference.pixels[i + 3]
      if (different) changed += 1
      diff[i] = different ? 255 : 0; diff[i + 1] = different ? 0 : 255; diff[i + 2] = 0; diff[i + 3] = different ? 255 : 0
    }
    const ratio = changed / (actual.width * actual.height)
    const limit = Number(item.maxDiffPixelRatio ?? 0.01)
    if (!Number.isFinite(limit)) fail(`${item.id}: invalid maxDiffPixelRatio ${limit}`)
    const diffBytes = encodePng(actual.width, actual.height, diff)
    await writeFile(path.join(dir, 'diff.png'), diffBytes)
    const result = ratio <= limit ? 'PASS' : 'FAIL'
    manifest.diff_metric = ratio
    manifest.result = result
    if (manifest.reviewer === 'pending') manifest.reviewer = 'automated'
    await writeFile(path.join(dir, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n')
    results.push({ id: item.id, reference_sha256: sha256(referenceBytes), actual_sha256: sha256(actualBytes), diff_sha256: sha256(diffBytes), diff_pixel_ratio: ratio, result })
  }
  await mkdir(root, { recursive: true })
  await writeFile(path.join(root, 'comparison.json'), JSON.stringify({ schema: 'notemeld.visual-comparison.v1', rc: args.rc, results }, null, 2) + '\n')
  const failures = results.filter((item) => item.result !== 'PASS')
  if (failures.length > 0) fail(failures.map((item) => `${item.id}: diff ratio ${item.diff_pixel_ratio} exceeds ${matrix.cases.find((candidate) => candidate.id === item.id).maxDiffPixelRatio ?? 0.01}`).join('; '))
  console.log(JSON.stringify({ rc: args.rc, cases: results.length, result: 'PASS' }))
}

main().catch((error) => { console.error(`visual comparison failed: ${error.message}`); process.exitCode = 1 })
