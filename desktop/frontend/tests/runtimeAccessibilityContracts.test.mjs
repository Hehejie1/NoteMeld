import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import test from 'node:test'

const runtime = await fs.readFile(new URL('../src/pages/Applications/RuntimeApp.tsx', import.meta.url), 'utf8')
const notes = await fs.readFile(new URL('../src/pages/Applications/NotesApp.tsx', import.meta.url), 'utf8')

test('runtime application exposes an accessible tablist and selected panel relationship', () => {
  assert.match(runtime, /role="tablist" aria-label="系统运行分类"/)
  assert.match(runtime, /role="tab" aria-selected=\{active === id\}/)
  assert.match(runtime, /aria-controls=\{`runtime-panel-\$\{id\}`\}/)
  assert.match(runtime, /role="tabpanel" aria-labelledby=\{`runtime-tab-\$\{active\}`\}/)
})

test('runtime workspace controls have associated labels', () => {
  assert.match(runtime, /htmlFor="runtime-workspace-name"/)
  assert.match(runtime, /htmlFor="runtime-folder-reference"/)
  assert.match(runtime, /htmlFor="runtime-memory-draft"/)
})

test('note and Wiki detail dialogs identify their title and close action', () => {
  assert.match(notes, /aria-labelledby="note-detail-title"/)
  assert.match(notes, /id="note-detail-title"/)
  assert.match(notes, /aria-label="关闭笔记详情"/)
  assert.match(notes, /aria-labelledby="wiki-article-title"/)
  assert.match(notes, /aria-label="关闭 Wiki 文章"/)
})
