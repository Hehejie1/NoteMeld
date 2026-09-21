import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const composer = fs.readFileSync(
  path.join(root, 'src/pages/HomePage/components/ChatComposer.tsx'),
  'utf8',
)
const service = fs.readFileSync(path.join(root, 'src/services/agent.ts'), 'utf8')
const inbox = fs.readFileSync(path.join(root, 'src/components/HostApprovalInbox.tsx'), 'utf8')
const layout = fs.readFileSync(path.join(root, 'src/layouts/AppLayout.tsx'), 'utf8')

assert.match(composer, /event\.type === 'approval\.required'/)
assert.match(composer, /resolveAgentApproval\(approvalId, approved \? 'approve' : 'deny'\)/)
assert.match(service, /\/agent\/v1\/approvals\/\$\{approvalId\}/)
assert.match(service, /\{ approved: decision \}/, 'boolean approval payload compatibility must remain')
assert.match(service, /listPendingAgentApprovals/)
assert.match(service, /\/agent\/v1\/approvals'/)
assert.match(service, /getRuntimeSessionToken/)
assert.match(service, /'X-NoteMeld-Session': sessionToken/)
assert.match(inbox, /notemeld-host-approval-inbox/)
assert.match(inbox, /notemeld-host-approval-deny:/)
assert.match(inbox, /notemeld-host-approval-approve:/)
assert.match(inbox, /window\.setInterval\(\(\) => void refresh\(\), 2_000\)/)
assert.match(layout, /<HostApprovalInbox backendReady=\{backendReady\}/)
