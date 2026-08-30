import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const source = fs.readFileSync(new URL('../src/services/cloud.ts', import.meta.url), 'utf8')

test('cloud client exposes stateless cross-device control plane methods', () => {
  for (const method of ['login', 'rotateToken', 'revokeCurrentToken', 'listTokens', 'createToken', 'revokeToken', 'listUsers', 'createUser', 'updateUser', 'deleteUser', 'listAudits', 'capabilities', 'listModels', 'createModel', 'updateModel', 'deleteModel', 'listDevices', 'registerDevice', 'rotateDeviceKey', 'heartbeat', 'requestDeviceChallenge', 'verifyDeviceChallenge', 'createDeviceToken', 'startPairing', 'confirmPairing', 'listGrants', 'createShareToken', 'listShareTokens', 'revokeShareToken', 'sharedSnapshot', 'sharedEvents', 'sharedCommand', 'createSession', 'importSession', 'sendCommand', 'events', 'snapshot', 'archiveSession', 'restoreSession', 'copySession', 'deleteSession', 'recoverCommand', 'listApprovals', 'resolveApproval', 'listWorkspaceFiles', 'readWorkspaceFile', 'writeWorkspaceFile', 'deleteWorkspaceFile', 'workspaceStats', 'createWorkspaceBackup', 'listWorkspaceBackups', 'restoreWorkspaceBackup']) {
    assert.match(source, new RegExp(`\\b${method}\\s*\\(`), `missing ${method}`)
  }
  assert.match(source, /\bme\s*\(/)
  assert.match(source, /commandStatus/)
  assert.match(source, /listCommands/)
  assert.match(source, /Authorization: `Bearer \$\{this\.token\}`/)
  assert.match(source, /class CloudClient/)
  assert.match(source, /audience: 'device-api'/)
  assert.match(source, /expires_in_seconds/)
})

test('cloud client exposes injectable token storage without localStorage coupling', () => {
  assert.match(source, /CloudTokenStore/)
  assert.match(source, /hydrateToken/)
  assert.match(source, /persistToken/)
  assert.doesNotMatch(source, /localStorage/)
  assert.match(source, /validateCloudBaseUrl/)
})

test('web token store uses encrypted IndexedDB rather than plaintext browser storage', () => {
  const tokenStore = fs.readFileSync(new URL('../src/services/tokenStore.ts', import.meta.url), 'utf8')
  assert.match(tokenStore, /IndexedDbTokenStore/)
  assert.match(tokenStore, /indexedDB\.open/)
  assert.match(tokenStore, /AES-GCM/)
  assert.doesNotMatch(tokenStore, /localStorage/)
})

test('web device identity is stable, platform-prefixed, and non-secret', () => {
  const identity = fs.readFileSync(new URL('../src/services/deviceIdentity.ts', import.meta.url), 'utf8')
  assert.match(identity, /getOrCreateInstallId/)
  assert.match(identity, /makeDeviceId/)
  assert.match(identity, /notemeld\.install-id\.v1/)
  assert.match(identity, /crypto\.getRandomValues/)
})

test('web relay protocol validates canonical encrypted frame metadata', () => {
  const protocol = fs.readFileSync(new URL('../src/services/relayProtocol.ts', import.meta.url), 'utf8')
  assert.match(protocol, /RELAY_PROTOCOL_VERSION = 'notemeld\.sync\.v1'/)
  assert.match(protocol, /validateRemoteFrame/)
  assert.match(protocol, /Number\.isSafeInteger\(frame\.sequence\)/)
  assert.match(protocol, /invalid relay frame nonce/)
  assert.match(protocol, /relayAssociatedData/)
})

test('web relay frame crypto binds nonce and metadata into AEAD', () => {
  const cryptoSource = fs.readFileSync(new URL('../src/services/relayFrameCrypto.ts', import.meta.url), 'utf8')
  assert.match(cryptoSource, /encryptRemoteFrame/)
  assert.match(cryptoSource, /decryptRemoteFrame/)
  assert.match(cryptoSource, /relayAssociatedData\(frame\)/)
  assert.match(cryptoSource, /name: 'AES-GCM'/)
  assert.match(cryptoSource, /validateRemoteFrame\(frame\)/)
})

test('connection strategy orders LAN candidates before cloud relay fallback', () => {
  const source = fs.readFileSync(new URL('../src/services/connectionStrategy.ts', import.meta.url), 'utf8')
  assert.match(source, /transport: 'lan'/)
  assert.match(source, /transport: 'relay'/)
  assert.match(source, /candidates\.push\(\{ transport: 'relay'/)
  assert.match(source, /connectWithFallback/)
  assert.match(source, /AbortController/)
  assert.match(source, /isPrivateLanEndpoint/)
  assert.match(source, /invalid private LAN endpoint/)
  assert.match(source, /relayWebSocketProtocols/)
  assert.match(source, /candidate\.auth === 'bearer'/)
  assert.match(source, /LAN challenge handler is required/)
  assert.match(source, /v1\/lan\/connect/)
  assert.match(source, /notemeld\.lan\.v1/)
  assert.match(source, /openRelayWebSocket/)
  assert.match(source, /parsed\.search/)
  assert.match(source, /new WebSocket\(candidate\.url, protocols\)/)
  const crypto = fs.readFileSync(new URL('../src/services/relayCrypto.ts', import.meta.url), 'utf8')
  assert.match(crypto, /AES-GCM/)
  assert.match(crypto, /additionalData/)
  assert.match(crypto, /getRandomValues/)
})

test('cloud session controller owns snapshot and incremental event projection', () => {
  const source = fs.readFileSync(new URL('../src/services/cloudSessionController.ts', import.meta.url), 'utf8')
  assert.match(source, /class CloudSessionController/)
  assert.match(source, /list\(archived\?/)
  assert.match(source, /refreshEvents/)
  assert.match(source, /lastSequence/)
  assert.match(source, /recoverCommand/)
  assert.match(source, /archive\(\)/)
  assert.match(source, /copy\(\)/)
  assert.match(source, /delete\(\)/)
  assert.match(source, /event\.sequence > this\.state\.lastSequence/)
  assert.match(source, /sort\(\(left, right\) => left\.sequence - right\.sequence\)/)
})

test('react cloud session hook subscribes to the shared controller lifecycle', () => {
  const source = fs.readFileSync(new URL('../src/hooks/useCloudSession.ts', import.meta.url), 'utf8')
  assert.match(source, /useCloudSession/)
  assert.match(source, /controller\.subscribe/)
  assert.match(source, /controller\.open\(sessionId\)/)
  assert.match(source, /setInterval/)
  assert.match(source, /refreshEvents\(\)\.catch/)
})

test('cloud auth hook hydrates, logs in, and revokes through CloudClient', () => {
  const source = fs.readFileSync(new URL('../src/hooks/useCloudAuth.ts', import.meta.url), 'utf8')
  assert.match(source, /hydrateToken/)
  assert.match(source, /client\.login\(password, username\)/)
  assert.match(source, /revokeCurrentToken/)
  assert.match(source, /authenticated: Boolean\(token\)/)
  assert.match(source, /setRole/)
})
