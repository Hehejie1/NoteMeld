import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import test from 'node:test'

const app = await fs.readFile(new URL('../src/pages/Applications/NotesApp.tsx', import.meta.url), 'utf8')
const note = await fs.readFile(new URL('../src/services/note.ts', import.meta.url), 'utf8')
const wiki = await fs.readFile(new URL('../src/services/wiki.ts', import.meta.url), 'utf8')
const conversation = await fs.readFile(new URL('../src/services/conversation.ts', import.meta.url), 'utf8')

test('Notes application reads the bounded real note library and exposes empty/loading/error states', () => {
  assert.match(app, /listNoteLibrary\(\{ q: query, offset, limit: PAGE_SIZE, signal: controller\.signal \}\)/)
  assert.match(app, /正在读取笔记库/)
  assert.match(app, /还没有符合条件的笔记/)
  assert.match(app, /笔记库读取失败/)
  assert.match(app, /下一页/)
  assert.match(app, /上一页/)
  assert.match(note, /\/notes\/library/)
})

test('Notes application wires Markdown import, Wiki article detail, rebuild and cancellation to services', () => {
  assert.match(app, /importConversationMarkdown/)
  assert.match(app, /getWikiArticleDetail/)
  assert.match(app, /retryWikiExtraction/)
  assert.match(app, /cancelWikiExtraction/)
  assert.match(app, /getWikiExtractionStatus/)
  assert.match(conversation, /importConversationMarkdown|imported_notes/)
  assert.match(wiki, /retryWikiExtraction/)
  assert.match(wiki, /cancelWikiExtraction/)
})

test('Notes application never claims Wiki completion while a task is still running', () => {
  assert.match(app, /item\.wikiStatus === 'running'/)
  assert.match(app, /取消 Wiki/)
  assert.match(app, /重建 Wiki/)
  assert.match(app, /wikiStatus: status/)
})
