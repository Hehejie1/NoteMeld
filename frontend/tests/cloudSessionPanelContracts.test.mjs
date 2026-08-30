import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const panel = fs.readFileSync(new URL('../src/components/CloudSessionPanel/CloudSessionPanel.tsx', import.meta.url), 'utf8')
const list = fs.readFileSync(new URL('../src/components/CloudSessionList/CloudSessionList.tsx', import.meta.url), 'utf8')
const devices = fs.readFileSync(new URL('../src/components/CloudDeviceList/CloudDeviceList.tsx', import.meta.url), 'utf8')
const login = fs.readFileSync(new URL('../src/components/CloudLoginPanel/CloudLoginPanel.tsx', import.meta.url), 'utf8')
const pairing = fs.readFileSync(new URL('../src/components/CloudPairingPanel/CloudPairingPanel.tsx', import.meta.url), 'utf8')
const grant = fs.readFileSync(new URL('../src/components/CloudGrantPanel/CloudGrantPanel.tsx', import.meta.url), 'utf8')
const approval = fs.readFileSync(new URL('../src/components/CloudApprovalList/CloudApprovalList.tsx', import.meta.url), 'utf8')
const workspace = fs.readFileSync(new URL('../src/components/CloudWorkspaceBrowser/CloudWorkspaceBrowser.tsx', import.meta.url), 'utf8')
const models = fs.readFileSync(new URL('../src/components/CloudModelList/CloudModelList.tsx', import.meta.url), 'utf8')
test('cloud session panel has loading, error, empty, and accessible event states', () => { assert.match(panel, /aria-busy/); assert.match(panel, /role="alert"/); assert.match(panel, /No events yet/); assert.match(panel, /role="log"/); assert.match(panel, /Copy branch/); assert.match(panel, /controller\.send/); assert.match(panel, /Message/) })
test('cloud session list supports archive filtering and keyboard selection', () => { assert.match(list, /listSessions\(archived\)/); assert.match(list, /aria-current/); assert.match(list, /role="list"/); assert.match(list, /No archived sessions/) })
test('device list exposes online status, LAN candidates, and revoke action', () => { assert.match(devices, /device\.online/); assert.match(devices, /lan_endpoints/); assert.match(devices, /revokeDevice/); assert.match(devices, /aria-label="Connected devices"/) })
test('cloud login panel uses username and password only', () => { assert.match(login, /autoComplete="username"/); assert.match(login, /autoComplete="current-password"/); assert.match(login, /client\.login\(password, username\)/); assert.doesNotMatch(login, /email|phone|手机号|邮箱/i) })
test('pairing panel uses short-lived cloud pairing flow', () => { assert.match(pairing, /startPairing/); assert.match(pairing, /confirmPairing/); assert.match(pairing, /aria-label="Pairing code"/); assert.match(pairing, /role="alert"/) })
test('grant panel defaults to standard non-dangerous scopes', () => { assert.match(grant, /createGrant/); assert.match(grant, /message\.send/); assert.match(grant, /Dangerous actions still require host approval/); assert.doesNotMatch(grant, /full_access/) })
test('approval list requires explicit approve or reject actions', () => { assert.match(approval, /listApprovals/); assert.match(approval, /resolveApproval/); assert.match(approval, /Approve/); assert.match(approval, /Reject/); assert.match(approval, /No pending approvals/) })
test('workspace browser is read-only and never exposes write or delete actions', () => { assert.match(workspace, /listWorkspaceFiles/); assert.match(workspace, /readWorkspaceFile/); assert.match(workspace, /Read-only preview/); assert.doesNotMatch(workspace, /writeWorkspaceFile|deleteWorkspaceFile/) })
test('model list displays only provider metadata and credential presence', () => { assert.match(models, /listModels/); assert.match(models, /has_api_key/); assert.doesNotMatch(models, /api_key_ciphertext|api_key["']?\s*:/) })
