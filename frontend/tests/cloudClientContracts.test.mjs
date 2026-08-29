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
