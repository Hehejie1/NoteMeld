import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const source = fs.readFileSync(new URL('../src/services/cloud.ts', import.meta.url), 'utf8')

test('cloud client exposes stateless cross-device control plane methods', () => {
  for (const method of ['login', 'rotateToken', 'revokeCurrentToken', 'listTokens', 'createToken', 'revokeToken', 'listUsers', 'createUser', 'updateUser', 'deleteUser', 'listAudits', 'capabilities', 'listDevices', 'registerDevice', 'rotateDeviceKey', 'heartbeat', 'requestDeviceChallenge', 'verifyDeviceChallenge', 'startPairing', 'confirmPairing', 'listGrants', 'createSession', 'sendCommand', 'events', 'snapshot', 'recoverCommand', 'listApprovals', 'resolveApproval', 'listWorkspaceFiles', 'readWorkspaceFile', 'writeWorkspaceFile', 'deleteWorkspaceFile']) {
    assert.match(source, new RegExp(`\\b${method}\\s*\\(`), `missing ${method}`)
  }
  assert.match(source, /Authorization: `Bearer \$\{this\.token\}`/)
  assert.match(source, /class CloudClient/)
})

test('cloud client exposes injectable token storage without localStorage coupling', () => {
  assert.match(source, /CloudTokenStore/)
  assert.match(source, /hydrateToken/)
  assert.match(source, /persistToken/)
  assert.doesNotMatch(source, /localStorage/)
})

test('web token store uses encrypted IndexedDB rather than plaintext browser storage', () => {
  const tokenStore = fs.readFileSync(new URL('../src/services/tokenStore.ts', import.meta.url), 'utf8')
  assert.match(tokenStore, /IndexedDbTokenStore/)
  assert.match(tokenStore, /indexedDB\.open/)
  assert.match(tokenStore, /AES-GCM/)
  assert.doesNotMatch(tokenStore, /localStorage/)
})
