import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import path from 'node:path'

const root = path.resolve(new URL('..', import.meta.url).pathname)

test('interactive primitives expose keyboard and semantic hooks', async () => {
  const [button, input, checkbox, dialog, feedback] = await Promise.all([
    readFile(path.join(root, 'src/button.tsx'), 'utf8'),
    readFile(path.join(root, 'src/input.tsx'), 'utf8'),
    readFile(path.join(root, 'src/checkbox.tsx'), 'utf8'),
    readFile(path.join(root, 'src/dialog.tsx'), 'utf8'),
    readFile(path.join(root, 'src/feedback.tsx'), 'utf8'),
  ])
  assert.match(button, /data-slot="button"/)
  assert.match(button, /focus-visible:/)
  assert.match(input, /data-slot="input"/)
  assert.match(checkbox, /CheckboxPrimitive\.Root/)
  assert.match(dialog, /DialogPrimitive\.(Root|Content)/)
  assert.match(feedback, /aria-live=/)
})
