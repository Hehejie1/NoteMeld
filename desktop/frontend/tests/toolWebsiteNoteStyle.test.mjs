import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const noteConstantsPath = path.resolve(__dirname, '../src/constant/note.ts')
const source = readFileSync(noteConstantsPath, 'utf8')

assert.match(source, /label:\s*'工具网站'/)
assert.match(source, /value:\s*'tool_website'/)

console.log('toolWebsiteNoteStyle.test.mjs passed')
